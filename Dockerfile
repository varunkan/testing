# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY wealthsimple_agent ./wealthsimple_agent
COPY examples ./examples

# Expose the port Cloud Run expects
ENV PORT=8080
EXPOSE 8080

# Run the FastAPI app via uvicorn
CMD ["uvicorn", "wealthsimple_agent.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
