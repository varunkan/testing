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

  let currentTicket = null;

  function plannedDays() {
    return 21;
  }

  function targetPct() {
    return Number(monthlyTarget.value) / 100;
  }

  function updateTargetHint() {
    const budget = Number(dailyBudget.value) || 0;
    const dollars = targetPct() * budget * plannedDays();
    monthlyTargetLabel.textContent = `${monthlyTarget.value}%`;
    targetHint.textContent = `Target ≈ $${dollars.toFixed(0)} this month (aspirational).`;
    $("of-target").textContent = `of $${dollars.toFixed(0)}`;
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
      take_profit_pct: 0.03,
      stop_loss_pct: 0.02,
      max_hold_days: 5,
      max_new_buys_per_day: 3,
      min_confidence_to_buy: 0.6,
      planned_trading_days_per_month: plannedDays(),
      universe: parseUniverse(),
      rss_urls: [],
    };
  }

  function renderProgress(p) {
    if (!p) return;
    const realized = Number(p.realized_pnl) || 0;
    const target = Number(p.target_profit) || 1;
    const pct = Number(p.progress_pct) || 0;
    $("realized").textContent = `$${realized.toFixed(2)}`;
    $("of-target").textContent = `of $${Number(p.target_profit).toFixed(0)}`;
    $("bar-fill").style.width = `${Math.min(Math.max(pct, 0), 1) * 100}%`;
    $("progress-meta").textContent =
      `${Math.round(pct * 100)}% of ${Math.round(Number(p.target_pct) * 100)}% monthly target · ${p.days_run} days run`;
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

  async function runMorningSession() {
    runDayBtn.disabled = true;
    setStatus("Researching morning ideas…");
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
      setStatus("Morning session complete.");
      $("desk").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setStatus(err.message || String(err), true);
    } finally {
      runDayBtn.disabled = false;
    }
  }

  async function refreshMonthly() {
    refreshMonthBtn.disabled = true;
    setStatus("Refreshing monthly progress…");
    try {
      const ym = new Date().toISOString().slice(0, 7);
      const budget = Number(dailyBudget.value) || 100;
      const pct = targetPct();
      const res = await fetch(
        `/portal/monthly/${ym}?daily_budget=${encodeURIComponent(budget)}&target_pct=${encodeURIComponent(pct)}`
      );
      if (!res.ok) throw new Error(await res.text());
      const progress = await res.json();
      renderProgress(progress);
      setStatus("Progress updated.");
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

  dialog.addEventListener("close", () => {
    /* no-op: approve handled separately */
  });

  approveBtn.addEventListener("click", (e) => {
    e.preventDefault();
    approvedMsg.hidden = false;
    approveBtn.hidden = true;
    if (currentTicket) {
      setStatus(`Approved ${String(currentTicket.action).toUpperCase()} ${currentTicket.ticker} for manual placement.`);
    }
  });

  updateTargetHint();
  recsList.innerHTML = `<p class="empty">Run a morning session to generate tickets.</p>`;
})();
