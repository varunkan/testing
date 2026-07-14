(() => {
  const $ = (id) => document.getElementById(id);

  const dailyBudget = $("daily-budget");
  const monthlyTarget = $("monthly-target");
  const monthlyTargetLabel = $("monthly-target-label");
  const universe = $("universe");
  const targetHint = $("target-hint");
  const statusEl = $("status");
  const runDayBtn = $("run-day");
  const refreshMonthBtn = $("refresh-month");
  const recsList = $("recs-list");
  const recsDay = $("recs-day");
  const dialog = $("ticket-dialog");
  const approvedMsg = $("approved-msg");
  const approveBtn = $("approve-ticket");
  const testTradeTicketBtn = $("test-trade-ticket");

  let currentTicket = null;

  function directionBadgeClass(direction) {
    const d = String(direction).toLowerCase();
    return d === "buy" ? "" : d === "sell" ? "sell" : "";
  }

  function directionLabel(direction) {
    const d = String(direction).toUpperCase();
    return d === "BUY" ? "BUY" : d === "SELL" ? "SELL" : "HOLD";
  }

  // API base URL is injected at build time (or set manually for local backend testing).
  const API_BASE_URL = window.API_BASE_URL || "";
  function api(path) {
    return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
  }

  let apiKey = localStorage.getItem("forge_desk_api_key") || "";
  let currentUser = null;

  function authHeaders() {
    return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  }

  function apiFetch(url, options = {}) {
    const headers = { ...options.headers, ...authHeaders() };
    return fetch(api(url), { ...options, headers });
  }

  function setAuthStatus(msg, isError = false) {
    const el = $("auth-status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("error", Boolean(isError));
  }

  async function fetchUser() {
    if (!apiKey) return null;
    try {
      const res = await apiFetch("/portal/auth/me");
      if (!res.ok) {
        apiKey = "";
        localStorage.removeItem("forge_desk_api_key");
        return null;
      }
      currentUser = await res.json();
      return currentUser;
    } catch (err) {
      return null;
    }
  }

  function renderAuth() {
    const forms = $("auth-forms");
    const info = $("auth-info");
    const usernameEl = $("auth-user");
    const toggle = $("auto-invest-toggle");
    if (!forms || !info) return;
    if (currentUser) {
      forms.hidden = true;
      info.hidden = false;
      usernameEl.textContent = currentUser.username;
      toggle.checked = currentUser.auto_invest;
    } else {
      forms.hidden = false;
      info.hidden = true;
    }
  }

  async function login() {
    const username = $("auth-username").value.trim();
    const password = $("auth-password").value;
    if (!username || !password) return setAuthStatus("Enter username and password.", true);
    try {
      const res = await apiFetch("/portal/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Login failed");
      apiKey = body.api_key;
      localStorage.setItem("forge_desk_api_key", apiKey);
      currentUser = body;
      renderAuth();
      refreshPaperViews();
      startLivePolling();
      setAuthStatus("Logged in.");
    } catch (err) {
      setAuthStatus(err.message || String(err), true);
    }
  }

  async function signup() {
    const username = $("auth-username").value.trim();
    const password = $("auth-password").value;
    if (!username || !password) return setAuthStatus("Enter username and password.", true);
    try {
      const res = await apiFetch("/portal/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Signup failed");
      apiKey = body.api_key;
      localStorage.setItem("forge_desk_api_key", apiKey);
      currentUser = body;
      renderAuth();
      refreshPaperViews();
      startLivePolling();
      setAuthStatus("Account created.");
    } catch (err) {
      setAuthStatus(err.message || String(err), true);
    }
  }

  function logout() {
    apiKey = "";
    currentUser = null;
    localStorage.removeItem("forge_desk_api_key");
    if (liveTimer) clearInterval(liveTimer);
    renderAuth();
    setAuthStatus("Logged out.");
  }

  async function toggleAutoInvest() {
    if (!apiKey) return;
    const checked = $("auto-invest-toggle").checked;
    try {
      const res = await apiFetch("/portal/auth/auto-invest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_invest: checked }),
      });
      if (!res.ok) throw new Error("Failed to update");
      const body = await res.json();
      $("auto-invest-toggle").checked = body.auto_invest;
      setAuthStatus(`Auto-invest ${body.auto_invest ? "on" : "off"}.`);
    } catch (err) {
      setAuthStatus(err.message || String(err), true);
    }
  }

  function plannedDays() {
    return 21;
  }

  function targetPct() {
    return Number(monthlyTarget.value) / 100;
  }

  function money(n) {
    return Number(n || 0).toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    });
  }

  function goalLabel(pct) {
    // pct is the slider value as a percent integer (50..1000)
    if (pct >= 1000) return "10×";
    if (pct >= 500) return "5×";
    if (pct >= 200) return "2×";
    if (pct >= 100) return "1×";
    return `${pct}%`;
  }

  function updateTargetHint() {
    const budget = Number(dailyBudget.value) || 0;
    const capital = budget * plannedDays();
    const dollars = targetPct() * capital;
    const pct = Number(monthlyTarget.value);
    monthlyTargetLabel.textContent = goalLabel(pct);
    const label = goalLabel(pct);
    targetHint.textContent = `${label} goal: earn ≈ ${money(dollars)} profit on ${money(capital)} capital this month (aspirational).`;
    $("of-target").textContent = `of ${money(dollars)} to ${label}`;
  }

  function setStatus(msg, isError = false) {
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function parseUniverse() {
    return universe.value
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
  }

  function configPayload() {
    return {
      daily_budget: Number(dailyBudget.value) || 100,
      monthly_target_pct: targetPct(),
      take_profit_pct: 0.04,
      stop_loss_pct: 0.02,
      max_hold_days: 7,
      max_new_buys_per_day: 4,
      min_confidence_to_buy: 0.55,
      planned_trading_days_per_month: plannedDays(),
      lookback_days: 90,
      universe: parseUniverse(),
      rss_urls: [],
    };
  }
  function renderProgress(p) {
    if (!p) return;
    const realized = Number(p.realized_pnl) || 0;
    const target = Number(p.target_profit) || 1;
    const pct = Number(p.progress_pct) || 0;
    const roi = Number(p.roi_pct) || 0;
    const tp = Number(p.target_pct) || 1;
    const label = tp >= 10 ? "10×" : tp >= 5 ? "5×" : tp >= 2 ? "2×" : tp >= 1 ? "1×" : `${Math.round(tp * 100)}%`;
    $("realized").textContent = money(realized);
    $("of-target").textContent = `of ${money(target)} to ${label}`;
    $("bar-fill").style.width = `${Math.min(Math.max(pct, 0), 1) * 100}%`;
    $("progress-meta").textContent =
      `${Math.round(pct * 100)}% of ${label} goal · ROI ${(roi * 100).toFixed(1)}% · ${p.days_run} days run`;

    $("stat-capital").textContent = money(p.capital_invested || 0);
    $("stat-roi").textContent = `${(roi * 100).toFixed(1)}%`;
    $("stat-win").textContent =
      Number(p.trades_count) > 0 ? `${Math.round(Number(p.win_rate) * 100)}%` : "—";
    $("stat-trades").textContent = String(p.trades_count || 0);
    $("stat-equity").textContent = money(p.equity || 0);
    $("stat-cash").textContent = money(p.cash || 0);
  }

  function renderPortfolio(p) {
    if (!p) return;
    $("paper-cash").textContent = money(p.cash);
    $("paper-equity").textContent = money(p.equity);
    $("paper-realized").textContent = money(p.realized_pnl);
    const box = $("positions-list");
    const positions = p.positions || [];
    if (!positions.length) {
      box.innerHTML = `<p class="empty">No open paper positions.</p>`;
      return;
    }
    box.innerHTML = positions
      .map((pos) => {
        const mark = (p.marks && p.marks[pos.ticker]) || pos.avg_price;
        return `<div class="pos-row"><strong>${pos.ticker}</strong><span>${Number(pos.quantity).toFixed(4)} @ ${money(pos.avg_price)} · mark ${money(mark)}</span></div>`;
      })
      .join("");
  }

  function renderTrades(trades) {
    const box = $("trades-list");
    if (!trades || !trades.length) {
      box.innerHTML = `<p class="empty">No paper fills yet.</p>`;
      return;
    }
    const rows = [...trades].reverse().slice(0, 20);
    box.innerHTML = rows
      .map((t) => {
        const sideClass = String(t.side).toLowerCase() === "buy" ? "side-buy" : "side-sell";
        const pnl =
          t.pnl == null ? "" : ` · P&L ${Number(t.pnl) >= 0 ? "+" : ""}${money(t.pnl)}`;
        const ts = t.ts ? new Date(t.ts).toLocaleString() : "";
        return `<div class="trade-row"><span><span class="${sideClass}">${String(t.side).toUpperCase()}</span> <strong>${t.ticker}</strong></span><span>${Number(t.qty).toFixed(4)} @ ${money(t.px)}${pnl}</span><span style="font-size:0.8rem;color:var(--muted)">${ts}</span></div>`;
      })
      .join("");
  }

  function renderRecommendations(report) {
    recsList.innerHTML = "";
    if (!report || !report.recommendations || !report.recommendations.length) {
      recsDay.textContent = "No tickets yet — run a morning session.";
      recsList.innerHTML = `<p class="empty">No recommendations for this session.</p>`;
      return;
    }
    recsDay.textContent = `Budget $${Number(report.budget_added).toFixed(0)} · ${report.day} · ${report.recommendations.length} tickets`;
    report.recommendations.forEach((rec, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rec";
      btn.style.animationDelay = `${i * 0.05}s`;
      const isBuy = String(rec.action).toLowerCase() === "buy";
      btn.innerHTML = `
        <span class="badge ${isBuy ? "" : "sell"}">${String(rec.action).toUpperCase()}</span>
        <span class="rec-body">
          <strong>${rec.ticker}</strong>
          <span>${rec.reason || rec.rationale || ""}</span>
          <span>Qty ${Number(rec.quantity).toFixed(3)} · Edge ${(Number(rec.expected_edge) * 100).toFixed(1)}% · Fees $${Number(rec.estimated_fees).toFixed(2)}</span>
        </span>
        <span class="rec-meta">${Math.round(Number(rec.confidence) * 100)}%</span>
      `;
      btn.addEventListener("click", () => openTicket(rec));
      recsList.appendChild(btn);
    });
  }

  function openTicket(rec) {
    currentTicket = rec;
    approvedMsg.hidden = true;
    approveBtn.hidden = false;
    testTradeTicketBtn.hidden = false;
    const isBuy = String(rec.action).toLowerCase() === "buy";
    $("ticket-action").textContent = String(rec.action).toUpperCase();
    $("ticket-action").className = `badge ${isBuy ? "" : "sell"}`;
    $("ticket-ticker").textContent = rec.ticker;
    $("ticket-reason").textContent = rec.reason || "";
    $("ticket-rationale").textContent = rec.rationale || "";
    $("ticket-metrics").innerHTML = `
      <div><dt>Quantity</dt><dd>${Number(rec.quantity).toFixed(4)} shares</dd></div>
      <div><dt>Expected edge</dt><dd>${(Number(rec.expected_edge) * 100).toFixed(2)}%</dd></div>
      <div><dt>Estimated fees</dt><dd>$${Number(rec.estimated_fees).toFixed(2)}</dd></div>
      <div><dt>Confidence</dt><dd>${Math.round(Number(rec.confidence) * 100)}%</dd></div>
      <div><dt>Order type</dt><dd>${rec.limit_price != null ? `Limit $${Number(rec.limit_price).toFixed(2)}` : "Market / best effort"}</dd></div>
    `;

    // Render persona council opinions in the ticket dialog if available.
    const personaBox = $("ticket-personas");
    if (personaBox) {
      const ops = rec.persona_opinions || [];
      if (ops.length) {
        const rows = ops.map((op) => {
          const badgeClass = directionBadgeClass(op.direction);
          const badge = `<span class="badge ${badgeClass}">${directionLabel(op.direction)}</span>`;
          return `<div class="persona-opinion-row"><span>${badge} <strong>${op.persona}</strong></span><span>${(Number(op.score) * 100).toFixed(1)}% · ${Math.round(Number(op.confidence) * 100)}% conf</span></div>`;
        }).join("");
        personaBox.innerHTML = `<h4>Analyst & market-driver council</h4>${rows}`;
        personaBox.hidden = false;
      } else {
        personaBox.innerHTML = "";
        personaBox.hidden = true;
      }
    }
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    }
  }

  async function refreshPaperViews() {
    const [portfolioRes, tradesRes, perfRes] = await Promise.all([
      apiFetch("/portal/portfolio"),
      apiFetch("/portal/trades"),
      apiFetch(`/portal/performance/${new Date().toISOString().slice(0, 7)}?daily_budget=${encodeURIComponent(Number(dailyBudget.value) || 100)}&target_pct=${encodeURIComponent(targetPct())}`),
    ]);
    if (portfolioRes.ok) renderPortfolio(await portfolioRes.json());
    if (tradesRes.ok) renderTrades(await tradesRes.json());
    if (perfRes.ok) renderProgress(await perfRes.json());
  }

  async function executeTestTrade(payload) {
    const res = await apiFetch("/portal/test-trade", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.detail || JSON.stringify(body) || `HTTP ${res.status}`);
    }
    return body;
  }

  async function runMorningSession() {
    runDayBtn.disabled = true;
    setStatus("Researching morning ideas + paper fills…");
    try {
      const res = await apiFetch("/portal/daily", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ config: configPayload() }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const report = await res.json();
      renderRecommendations(report);
      renderProgress(report.monthly_progress);
      await refreshPaperViews();
      setStatus("Morning session complete — paper fills & performance updated.");
      $("desk").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setStatus(err.message || String(err), true);
    } finally {
      runDayBtn.disabled = false;
    }
  }

  async function refreshMonthly() {
    refreshMonthBtn.disabled = true;
    setStatus("Refreshing performance…");
    try {
      await refreshPaperViews();
      setStatus("Performance & paper portfolio updated.");
    } catch (err) {
      setStatus(err.message || String(err), true);
    } finally {
      refreshMonthBtn.disabled = false;
    }
  }

  $("scroll-to-desk").addEventListener("click", () => {
    $("desk").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  dailyBudget.addEventListener("input", updateTargetHint);
  monthlyTarget.addEventListener("input", updateTargetHint);
  runDayBtn.addEventListener("click", runMorningSession);
  refreshMonthBtn.addEventListener("click", refreshMonthly);

  approveBtn.addEventListener("click", (e) => {
    e.preventDefault();
    approvedMsg.hidden = false;
    approvedMsg.textContent = "Marked for manual placement.";
    if (currentTicket) {
      setStatus(`Marked ${String(currentTicket.action).toUpperCase()} ${currentTicket.ticker} for manual placement.`);
    }
  });

  testTradeTicketBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!currentTicket) return;
    testTradeTicketBtn.disabled = true;
    try {
      const result = await executeTestTrade({
        ticker: currentTicket.ticker,
        action: String(currentTicket.action).toLowerCase(),
        quantity: Number(currentTicket.quantity),
        fund_if_needed: true,
      });
      approvedMsg.hidden = false;
      approvedMsg.textContent = `Paper filled ${String(result.trade.side).toUpperCase()} ${result.trade.ticker}.`;
      setStatus(`Test trade filled: ${String(result.trade.side).toUpperCase()} ${result.trade.ticker} @ ${money(result.trade.px)}`);
      await refreshPaperViews();
    } catch (err) {
      setStatus(err.message || String(err), true);
      approvedMsg.hidden = false;
      approvedMsg.textContent = err.message || String(err);
    } finally {
      testTradeTicketBtn.disabled = false;
    }
  });

  $("manual-trade-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticker = $("tt-ticker").value.trim().toUpperCase();
    const action = $("tt-side").value;
    const quantity = Number($("tt-qty").value);
    const priceRaw = $("tt-price").value;
    const payload = {
      ticker,
      action,
      quantity,
      fund_if_needed: $("tt-fund").checked,
    };
    if (priceRaw) payload.price = Number(priceRaw);
    setStatus(`Submitting test ${action.toUpperCase()} ${ticker}…`);
    try {
      const result = await executeTestTrade(payload);
      setStatus(`Test trade filled: ${String(result.trade.side).toUpperCase()} ${result.trade.ticker} @ ${money(result.trade.px)}`);
      await refreshPaperViews();
    } catch (err) {
      setStatus(err.message || String(err), true);
    }
  });

  $("refresh-portfolio").addEventListener("click", async () => {
    try {
      await refreshPaperViews();
      setStatus("Paper portfolio refreshed.");
    } catch (err) {
      setStatus(err.message || String(err), true);
    }
  });

  $("reset-paper").addEventListener("click", async () => {
    const starting = Number(dailyBudget.value) || 1000;
    if (!window.confirm(`Reset paper account to $${starting.toFixed(0)} cash and clear positions?`)) return;
    try {
      const res = await apiFetch("/portal/paper/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ starting_cash: starting }),
      });
      if (!res.ok) throw new Error(await res.text());
      await refreshPaperViews();
      setStatus(`Paper account reset to ${money(starting)}.`);
    } catch (err) {
      setStatus(err.message || String(err), true);
    }
  });

  $("acc-run").addEventListener("click", async () => {
    const ticker = ($("acc-ticker").value || "AAPL").trim().toUpperCase();
    const horizon = Number($("acc-horizon").value) || 5;
    const box = $("acc-result");
    box.textContent = "Measuring…";
    try {
      const res = await apiFetch(
        `/portal/accuracy/${encodeURIComponent(ticker)}?horizon_days=${horizon}&threshold_pct=0.01&lookback_days=180`
      );
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      if (!d.samples) {
        box.innerHTML = `<p>${d.disclaimer || "Not enough history."}</p>`;
        return;
      }
      const pct = (Number(d.hit_rate) * 100).toFixed(1);
      const costPct = (Number(d.cost_adjusted_hit_rate) * 100).toFixed(1);
      const avg = (Number(d.avg_forward_return) * 100).toFixed(2);
      const avgSignal = (Number(d.avg_signal_return) * 100).toFixed(2);
      box.innerHTML = `
        <p><span class="big">${pct}%</span> hit-rate on ${d.samples} past signals (${d.correct} correct) over ${d.horizon_days}-day horizon.</p>
        <p>Cost-adjusted hit-rate: ${costPct}% · Avg forward return: ${avg}% · Avg signal return: ${avgSignal}% · Threshold ±${(Number(d.threshold_pct) * 100).toFixed(1)}%.</p>
        <p>${d.disclaimer}</p>
      `;
    } catch (err) {
      box.textContent = err.message || String(err);
    }
  });

  $("persona-run").addEventListener("click", async () => {
    const ticker = ($("persona-ticker").value || "AAPL").trim().toUpperCase();
    const resultBox = $("persona-result");
    const listBox = $("persona-list");
    resultBox.textContent = "Gathering analyst & market-driver opinions…";
    listBox.innerHTML = "";
    try {
      const res = await apiFetch(`/portal/personas/${encodeURIComponent(ticker)}?lookback_days=90`);
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      if (!d.opinions || !d.opinions.length) {
        resultBox.textContent = d.disclaimer || "No opinions available.";
        return;
      }
      const buyCount = d.opinions.filter((o) => String(o.direction).toLowerCase() === "buy").length;
      const sellCount = d.opinions.filter((o) => String(o.direction).toLowerCase() === "sell").length;
      const holdCount = d.opinions.length - buyCount - sellCount;
      resultBox.innerHTML = `
        <strong>${ticker}</strong> — ${buyCount} buy, ${sellCount} sell, ${holdCount} hold
        <br><span style="font-size:0.85rem">${d.disclaimer}</span>
      `;
      listBox.innerHTML = d.opinions.map((op) => {
        const badgeClass = directionBadgeClass(op.direction);
        return `
          <div class="persona-card">
            <span class="badge ${badgeClass}">${directionLabel(op.direction)}</span>
            <div class="persona-info">
              <strong>${op.persona}</strong>
              <span>${op.style}</span>
            </div>
            <span class="persona-score">${(Number(op.score) * 100).toFixed(1)}% · ${Math.round(Number(op.confidence) * 100)}% conf</span>
          </div>
          <p style="margin:0 0 0.5rem 0.2rem; color:var(--muted); font-size:0.85rem;">${op.rationale}</p>
        `;
      }).join("");
    } catch (err) {
      resultBox.textContent = err.message || String(err);
    }
  });

  // ---- Live desk (always-on engine, one-click trades) ----
  let liveTimer = null;

  function setLiveStatus(msg, isError = false) {
    const el = $("live-status");
    el.textContent = msg || "";
    el.classList.toggle("error", Boolean(isError));
  }

  function pct(x) {
    return x == null ? "—" : `${(Number(x) * 100).toFixed(2)}%`;
  }

  function renderLiveDesk(d) {
    const engine = d.engine || {};
    const marketLabel = d.market_open ? "Market open" : "Market closed";
    const lastScan = engine.last_success_at
      ? new Date(engine.last_success_at).toLocaleTimeString()
      : "never";
    $("live-engine-status").textContent =
      `${marketLabel} · engine ${engine.running ? "running" : "stopped"} · ` +
      `${engine.scans_completed || 0} scans · last scan ${lastScan}` +
      (engine.last_error ? ` · last error: ${engine.last_error}` : "") +
      (engine.self_heals ? ` · self-healed ${engine.self_heals}×` : "") +
      ` · cash ${money(d.cash)}`;

    const positions = d.positions || [];
    $("live-sell-title").hidden = !positions.length;
    $("live-positions").innerHTML = positions.length
      ? positions
          .map((p) => {
            const pnlClass = p.pnl_pct == null ? "" : Number(p.pnl_pct) >= 0 ? "side-buy" : "side-sell";
            const sellBtn =
              p.advice === "sell"
                ? `<button type="button" class="cta amber live-sell-btn" data-ticker="${p.ticker}">Sell now</button>`
                : `<button type="button" class="ghost live-sell-btn" data-ticker="${p.ticker}">Sell</button>`;
            return `<div class="trade-row">
              <span><strong>${p.ticker}</strong> ${Number(p.quantity).toFixed(4)} @ ${money(p.avg_price)}</span>
              <span>live ${p.live_price ? money(p.live_price) : "—"} · <span class="${pnlClass}">${pct(p.pnl_pct)}</span></span>
              <span style="font-size:0.82rem;color:var(--muted)">${p.reason}</span>
              <span>${sellBtn}</span>
            </div>`;
          })
          .join("")
      : "";

    const buys = d.buy_now || [];
    $("live-buy-title").hidden = false;
    $("live-buys").innerHTML = buys.length
      ? buys
          .map((o) => {
            const chg = o.change_pct == null ? "" : ` · today ${pct(o.change_pct)}`;
            return `<div class="trade-row">
              <span><span class="side-buy">BUY</span> <strong>${o.ticker}</strong> @ ${money(o.price)}${chg}</span>
              <span>${Math.round(Number(o.confidence) * 100)}% conf</span>
              <span style="font-size:0.82rem;color:var(--muted)">${o.rationale}</span>
              <span><button type="button" class="cta live-buy-btn" data-ticker="${o.ticker}">Buy now</button></span>
            </div>`;
          })
          .join("")
      : `<p class="empty">No buy signals clear the bar right now — the engine keeps scanning all day.</p>`;

    document.querySelectorAll(".live-buy-btn").forEach((btn) => {
      btn.addEventListener("click", () => liveTrade(btn.getAttribute("data-ticker"), "buy"));
    });
    document.querySelectorAll(".live-sell-btn").forEach((btn) => {
      btn.addEventListener("click", () => liveTrade(btn.getAttribute("data-ticker"), "sell"));
    });
  }

  async function refreshLiveDesk() {
    if (!apiKey) {
      $("live-engine-status").textContent = "Log in to see live signals for your account.";
      return;
    }
    try {
      const res = await apiFetch("/portal/live/opportunities");
      if (!res.ok) throw new Error(await res.text());
      renderLiveDesk(await res.json());
    } catch (err) {
      setLiveStatus(err.message || String(err), true);
    }
  }

  async function liveTrade(ticker, action) {
    const payload = { ticker, action };
    if (action === "buy") payload.notional = Number($("live-buy-amount").value) || 50;
    setLiveStatus(`Executing ${action.toUpperCase()} ${ticker} at live price…`);
    try {
      const res = await apiFetch("/portal/live/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setLiveStatus(
        `Filled ${String(body.trade.side).toUpperCase()} ${body.trade.ticker} ` +
          `${Number(body.trade.qty).toFixed(4)} @ ${money(body.trade.px)} (live).`
      );
      await Promise.all([refreshLiveDesk(), refreshPaperViews()]);
    } catch (err) {
      setLiveStatus(err.message || String(err), true);
    }
  }

  async function forceLiveScan() {
    $("live-force-scan").disabled = true;
    setLiveStatus("Running a full market rescan — this can take a minute…");
    try {
      const res = await apiFetch("/portal/live/scan", { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setLiveStatus(`Rescan complete — ${body.opportunities} live signals found.`);
      await refreshLiveDesk();
    } catch (err) {
      setLiveStatus(err.message || String(err), true);
    } finally {
      $("live-force-scan").disabled = false;
    }
  }

  function startLivePolling() {
    if (liveTimer) clearInterval(liveTimer);
    liveTimer = setInterval(refreshLiveDesk, 60_000);
    refreshLiveDesk();
  }

  $("live-refresh").addEventListener("click", refreshLiveDesk);
  $("live-force-scan").addEventListener("click", forceLiveScan);

  // ---- Morning briefing (deposit → approve → invest) ----
  let morningPlan = null;

  function setMorningStatus(msg, isError = false) {
    const el = $("morning-status");
    el.textContent = msg || "";
    el.classList.toggle("error", Boolean(isError));
  }

  function renderMorningPlan(plan) {
    morningPlan = plan;
    const box = $("morning-plan");
    const sells = plan.sells || [];
    const buys = plan.buys || [];

    $("morning-summary").textContent =
      `Deposited ${money(plan.deposit)} · cash now ${money(plan.cash_after_deposit)}` +
      (sells.length ? ` · selling frees ≈ ${money(plan.estimated_sell_proceeds)}` : "") +
      ` · investable if approved ≈ ${money(plan.investable_if_approved)}`;

    const itemRow = (item, idx, kind) => {
      const sideClass = kind === "buy" ? "side-buy" : "side-sell";
      return `<label class="trade-row" style="cursor:pointer">
        <span><input type="checkbox" class="morning-check" data-kind="${kind}" data-idx="${idx}" checked />
          <span class="${sideClass}">${kind.toUpperCase()}</span> <strong>${item.ticker}</strong></span>
        <span>${Number(item.quantity).toFixed(4)} @ ${money(item.price)} ≈ ${money(item.notional)} · ${Math.round(Number(item.confidence) * 100)}% conf</span>
        <span style="font-size:0.82rem;color:var(--muted)">${item.reason}</span>
      </label>`;
    };

    $("morning-sells-title").hidden = !sells.length;
    $("morning-sells").innerHTML = sells.length
      ? sells.map((s, i) => itemRow(s, i, "sell")).join("")
      : "";
    $("morning-buys-title").hidden = !buys.length;
    $("morning-buys").innerHTML = buys.length
      ? buys.map((b, i) => itemRow(b, i, "buy")).join("")
      : `<p class="empty">No buy candidates cleared the confidence bar today — cash stays safe until tomorrow.</p>`;

    $("morning-goal-note").textContent = plan.goal ? plan.goal.note : "";
    box.hidden = false;
  }

  async function requestMorningPlan() {
    if (!apiKey) return setMorningStatus("Log in first to get your morning plan.", true);
    const deposit = Number($("morning-deposit").value) || 0;
    $("morning-plan-btn").disabled = true;
    setMorningStatus("Depositing and researching today's strongest ideas…");
    try {
      const res = await apiFetch("/portal/morning/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deposit, universe: parseUniverse() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      renderMorningPlan(body);
      await refreshPaperViews();
      setMorningStatus(
        `Plan ready — ${(body.sells || []).length} sell(s), ${(body.buys || []).length} buy(s). Review and approve below.`
      );
    } catch (err) {
      setMorningStatus(err.message || String(err), true);
    } finally {
      $("morning-plan-btn").disabled = false;
    }
  }

  async function approveMorningPlan() {
    if (!morningPlan) return;
    const checks = document.querySelectorAll(".morning-check:checked");
    const items = [];
    checks.forEach((c) => {
      const kind = c.getAttribute("data-kind");
      const idx = Number(c.getAttribute("data-idx"));
      const src = kind === "buy" ? morningPlan.buys[idx] : morningPlan.sells[idx];
      if (src) {
        items.push({
          ticker: src.ticker,
          action: src.action,
          quantity: src.quantity,
          confidence: src.confidence,
          expected_edge: src.expected_edge,
          estimated_fees: src.estimated_fees,
        });
      }
    });
    if (!items.length) return setMorningStatus("Nothing selected to invest.", true);
    $("morning-approve").disabled = true;
    setMorningStatus("Executing your approved picks as paper fills…");
    try {
      const res = await apiFetch("/portal/morning/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      $("morning-plan").hidden = true;
      morningPlan = null;
      await refreshPaperViews();
      setMorningStatus(`Done — ${body.executed_count} fill(s) executed. Portfolio updated below.`);
    } catch (err) {
      setMorningStatus(err.message || String(err), true);
    } finally {
      $("morning-approve").disabled = false;
    }
  }

  $("morning-plan-btn").addEventListener("click", requestMorningPlan);
  $("morning-approve").addEventListener("click", approveMorningPlan);
  $("morning-dismiss").addEventListener("click", () => {
    $("morning-plan").hidden = true;
    morningPlan = null;
    setMorningStatus("Plan dismissed — your deposit stays in cash.");
  });

  $("auth-login").addEventListener("click", login);
  $("auth-signup").addEventListener("click", signup);
  $("auth-logout").addEventListener("click", logout);
  $("auto-invest-toggle").addEventListener("change", toggleAutoInvest);
  $("auto-run-day").addEventListener("click", async () => {
    runDayBtn.disabled = true;
    $("auto-run-day").disabled = true;
    setStatus("Auto-investing today on your behalf…");
    try {
      const res = await apiFetch("/portal/daily/auto", { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const report = await res.json();
      renderRecommendations(report);
      renderProgress(report.monthly_progress);
      await refreshPaperViews();
      setStatus("Auto-invest complete — paper fills & performance updated.");
    } catch (err) {
      setStatus(err.message || String(err), true);
    } finally {
      runDayBtn.disabled = false;
      $("auto-run-day").disabled = false;
    }
  });

  updateTargetHint();
  recsList.innerHTML = `<p class="empty">Run a morning session to generate tickets.</p>`;
  fetchUser().then((u) => {
    renderAuth();
    if (u) {
      refreshPaperViews().catch(() => {});
      startLivePolling();
    }
  });

  // Universe preset chips
  document.querySelectorAll(".chip[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = btn.getAttribute("data-preset");
      const cur = universe.value.split(",").map((s) => s.trim()).filter(Boolean);
      if (!cur.map((s) => s.toLowerCase()).includes(preset.toLowerCase())) {
        cur.push(preset);
      }
      universe.value = cur.join(", ");
    });
  });

  $("load-presets").addEventListener("click", async () => {
    const info = $("preset-info");
    info.hidden = false;
    info.textContent = "Loading…";
    try {
      const res = await apiFetch("/portal/universes");
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      const lines = Object.entries(d.presets || {})
        .map(([k, v]) => `@${k}: ${v} tickers`)
        .join(" · ");
      info.textContent = lines || "No presets.";
    } catch (err) {
      info.textContent = err.message || String(err);
    }
  });

  $("daily-report-run").addEventListener("click", async () => {
    const dayInput = $("daily-report-day").value;
    const day = dayInput || new Date().toISOString().slice(0, 10);
    const box = $("daily-report-result");
    box.textContent = "Loading…";
    try {
      const res = await apiFetch(`/portal/daily-report/${day}`);
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      const recs = (d.recommendations || []).map((r) => {
        const side = String(r.action).toUpperCase();
        return `<div class="persona-opinion-row"><span><strong>${side}</strong> ${r.ticker}</span><span>${money(r.quantity * 100)} notional · ${(Number(r.confidence) * 100).toFixed(0)}% conf</span></div>`;
      }).join("") || "<p>No recommendations.</p>";
      const trades = (d.trades || []).map((t) => {
        const pnl = t.pnl == null ? "" : ` · P&L ${Number(t.pnl) >= 0 ? "+" : ""}${money(t.pnl)}`;
        const ts = t.ts ? new Date(t.ts).toLocaleString() : "";
        return `<div class="persona-opinion-row"><span><strong>${String(t.side).toUpperCase()}</strong> ${t.ticker}</span><span>${Number(t.qty).toFixed(4)} @ ${money(t.px)}${pnl}</span><span style="font-size:0.8rem;color:var(--muted)">${ts}</span></div>`;
      }).join("") || "<p>No trades.</p>";
      box.innerHTML = `
        <p><strong>${d.day}</strong> — ${d.trade_count} trades — Realized P&L: ${money(d.realized_pnl_day)}</p>
        <p><strong>Recommendations</strong></p>
        ${recs}
        <p><strong>Trades</strong></p>
        ${trades}
        <p style="font-size:0.85rem">${d.disclaimer}</p>
      `;
    } catch (err) {
      box.textContent = err.message || String(err);
    }
  });
})();
