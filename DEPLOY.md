# Deploy Forge Desk to Vercel + Google Cloud

This guide splits the app into two parts:

- **Frontend**: Vercel hosts the static HTML/CSS/JS from `wealthsimple_agent/web`.
- **Backend**: Google Cloud Run hosts the Dockerized FastAPI app.
- **Database**: SQLite is used by default, but Cloud Run is stateless. For production, migrate to **Cloud SQL (PostgreSQL)** or accept ephemeral SQLite data (reset on redeploy).

---

## 1. Backend: Google Cloud Run

### 1.1 Create a Google Cloud project

- Go to https://console.cloud.google.com
- Create a project and note the **Project ID**.
- Enable the Cloud Run API and Artifact Registry API.

### 1.2 Create an Artifact Registry repository

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud artifacts repositories create forge-desk \
  --repository-format=docker \
  --location=us-central1 \
  --description="Forge Desk backend images"
```

### 1.3 Create a service account for GitHub Actions

1. In GCP Console, go to **IAM & Admin > Service Accounts**.
2. Create a service account named `github-actions-deployer`.
3. Grant it these roles:
   - `Cloud Run Admin`
   - `Artifact Registry Writer`
   - `Service Account User`
4. Create a JSON key, download it, and save it as `GCP_SA_KEY` in your GitHub repo secrets.
5. Add these GitHub secrets:
   - `GCP_PROJECT_ID`: your GCP project ID
   - `GCP_REGION`: e.g. `us-central1`
   - `GCP_SERVICE_NAME`: e.g. `forge-desk-backend`
   - `GCP_ARTIFACT_REPO`: e.g. `forge-desk`
   - `GCP_SA_KEY`: the full JSON key contents

### 1.4 Deploy the backend manually (optional)

```bash
# Build
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/forge-desk/forge-desk-backend:latest .

# Push
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/forge-desk/forge-desk-backend:latest

# Deploy
gcloud run deploy forge-desk-backend \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/forge-desk/forge-desk-backend:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --max-instances 1
```

Cloud Run will print a URL like:

```
https://forge-desk-backend-xxxxxxxx-uc.a.run.app
```

Save this URL for the Vercel step.

> **Warning about SQLite**: Cloud Run containers are stateless. The default SQLite database (`portal.db`) lives inside the container and is lost on every redeploy. For a demo or short-lived tests this is fine. For production, use Cloud SQL (PostgreSQL) — see section 4.

---

## 2. Frontend: Vercel

### 2.1 Prepare Vercel project

1. Go to https://vercel.com and import your GitHub repo.
2. In the project settings, add an environment variable:
   - `WS_AGENT_API_BASE_URL`: your Cloud Run backend URL (e.g. `https://forge-desk-backend-xxxxxxxx-uc.a.run.app`)
3. Vercel will read `vercel.json` in the repo root and run `scripts/prepare_web.py` at build time, which injects the API URL into `wealthsimple_agent/web/config.js`.

### 2.2 Vercel configuration

The repo already contains `vercel.json`:

```json
{
  "buildCommand": "python scripts/prepare_web.py",
  "outputDirectory": "wealthsimple_agent/web",
  "installCommand": "pip install -r requirements.txt"
}
```

This tells Vercel to:
1. Install Python dependencies (needed for the build script).
2. Run `prepare_web.py` to inject `WS_AGENT_API_BASE_URL` into `config.js`.
3. Deploy the contents of `wealthsimple_agent/web` as a static site.

### 2.3 CORS

The backend reads `WS_AGENT_CORS_ORIGINS` as a JSON list. After you know your Vercel URL, update the Cloud Run deployment:

```bash
gcloud run services update forge-desk-backend \
  --region us-central1 \
  --update-env-vars WS_AGENT_CORS_ORIGINS='["https://your-vercel-app.vercel.app"]'
```

For local development, the default `cors_origins = ["*"]` allows all origins.

---

## 3. Local development with the split setup

To test the frontend against a local backend:

```bash
# Terminal 1: backend
uvicorn wealthsimple_agent.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: frontend
# Edit wealthsimple_agent/web/config.js to point at the local backend:
# window.API_BASE_URL = "http://localhost:8000";
# Then serve the static files, e.g.:
python -m http.server 3000 --directory wealthsimple_agent/web
```

Open http://localhost:3000 and the frontend will call http://localhost:8000.

---

## 4. Production database: Cloud SQL (PostgreSQL)

For a real production deployment, replace SQLite with PostgreSQL:

### 4.1 Create a Cloud SQL instance

```bash
gcloud sql instances create forge-desk-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1

gcloud sql databases create forge_desk --instance=forge-desk-db
```

### 4.2 Update the backend to use PostgreSQL

1. Add `psycopg2-binary` or `asyncpg` to `requirements.txt`.
2. Modify `wealthsimple_agent/portal/store.py` to accept a PostgreSQL connection string.
3. Pass the connection string via a new environment variable, e.g. `WS_AGENT_DATABASE_URL`.

Example `WS_AGENT_DATABASE_URL`:

```
postgresql://user:password@/forge_desk?host=/cloudsql/YOUR_PROJECT_ID:us-central1:forge-desk-db
```

### 4.3 Connect Cloud Run to Cloud SQL

When deploying, add the Cloud SQL connection:

```bash
gcloud run deploy forge-desk-backend \
  --image ... \
  --add-cloudsql-instances YOUR_PROJECT_ID:us-central1:forge-desk-db \
  --update-env-vars WS_AGENT_DATABASE_URL='postgresql://...' \
  ...
```

> Note: this is not yet implemented in the current codebase. SQLite is the default storage.

---

## 5. Cost expectations

- **Vercel static hosting**: free tier available.
- **Google Cloud Run**: free tier includes 2 million requests/month and 360,000 vCPU-seconds/month. After that, pay-per-use.
- **Cloud SQL**: ~$7-15/month minimum for a `db-f1-micro` instance.
- **yfinance data**: no direct cost, but frequent requests can hit rate limits.

---

## 6. Security checklist

- [ ] Do **not** expose live brokerage credentials in the app.
- [ ] Keep the app in **paper trading** mode unless you have proper licensing.
- [ ] Add disclaimers everywhere: "Not financial advice. Past performance does not predict future results."
- [ ] Do not promise guaranteed returns or 99.99% accuracy in marketing.
- [ ] Use HTTPS only (Vercel and Cloud Run both provide this).
- [ ] Restrict `WS_AGENT_CORS_ORIGINS` to your actual frontend domain.
- [ ] Store secrets in GitHub / Vercel / GCP secret managers, never in code.
