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
        return `<div class="trade-row"><span><span class="${sideClass}">${String(t.side).toUpperCase()}</span> <strong>${t.ticker}</strong></span><span>${Number(t.qty).toFixed(4)} @ ${money(t.px)}${pnl}</span></div>`;
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
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    }
  }

  async function refreshPaperViews() {
    const [portfolioRes, tradesRes, perfRes] = await Promise.all([
      fetch("/portal/portfolio"),
      fetch("/portal/trades"),
      fetch(
        `/portal/performance/${new Date().toISOString().slice(0, 7)}?daily_budget=${encodeURIComponent(Number(dailyBudget.value) || 100)}&target_pct=${encodeURIComponent(targetPct())}`
      ),
    ]);
    if (portfolioRes.ok) renderPortfolio(await portfolioRes.json());
    if (tradesRes.ok) renderTrades(await tradesRes.json());
    if (perfRes.ok) renderProgress(await perfRes.json());
  }

  async function executeTestTrade(payload) {
    const res = await fetch("/portal/test-trade", {
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
      const res = await fetch("/portal/daily", {
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
      const res = await fetch("/portal/paper/reset", {
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
      const res = await fetch(
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

  updateTargetHint();
  recsList.innerHTML = `<p class="empty">Run a morning session to generate tickets.</p>`;
  refreshPaperViews().catch(() => {});

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
      const res = await fetch("/portal/universes");
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
})();
