// ── ETF TAB ────────────────────────────────────────────────────────────────

const ETF_NAMES = {
  SPY: "S&P 500", QQQ: "Nasdaq 100", GLD: "Gold",
  SLV: "Silver",  TLT: "US Bonds",   USO: "Oil",
};

function renderEtfCard(d) {
  const card = document.getElementById("card-" + d.ticker);
  if (!card) return;

  if (d.error) {
    card.className = "card error";
    card.innerHTML = cardError(d.ticker, ETF_NAMES[d.ticker] || d.ticker, d.error);
    return;
  }

  const inst = d.institutional;
  const cotColor = inst.cot_bias === "bullish" ? "check" : inst.cot_bias === "bearish" ? "cross" : "warn";
  const cotIndex = inst.cot_index !== null ? ` (${inst.cot_index}/100)` : "";

  card.className = `card ${d.signal_class}`;
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="ticker-name">${ETF_NAMES[d.ticker] || d.ticker} <span style="font-size:0.9rem;color:#4f8ef7;font-weight:500">(${d.ticker})</span></div>
        <div class="ticker-price">$${d.price}</div>
      </div>
      <div class="signal-badge">${d.signal}</div>
    </div>
    ${scoreBar(d.score_pct, d.unavailable_signals, d.available_signals)}

    <div class="section-title">Institutional Layer</div>
    <div class="row"><span class="row-label">COT Bias</span><span class="row-value"><span class="${cotColor}">${inst.cot_bias}${cotIndex}</span></span></div>
    <div class="row"><span class="row-label">Quarter End Risk</span><span class="row-value">${inst.quarter_end_risk ? '<span class="warn">&#x26A0; Yes</span>' : '<span class="check">No</span>'}</span></div>
    <div class="row"><span class="row-label">Max Pain</span><span class="row-value">${inst.max_pain ? '$' + inst.max_pain : '<span class="muted">N/A</span>'}</span></div>
    <div class="row"><span class="row-label">Fair Value Gaps</span><span class="row-value">${fvgTags(inst.fvgs)}</span></div>
    <div class="row"><span class="row-label">POC / VAH / VAL</span><span class="row-value">$${inst.poc} / $${inst.vah} / $${inst.val}</span></div>

    ${trendSection(d.trend)}
    ${levelsSection(d.levels)}
    ${bottomWatch(d.bottom_watch)}`;
}

async function loadEtfs() {
  const btn = document.getElementById("etf-refresh-btn");
  btn.disabled = true; btn.textContent = "Loading...";
  document.querySelectorAll("#etf-grid .card").forEach(c => {
    c.className = "card loading";
    c.innerHTML = `<div class="loading-state"><div class="spinner"></div>Loading...</div>`;
  });
  try {
    const data = await fetch("/api/analyze/etf").then(r => r.json());
    data.forEach(renderEtfCard);
    document.getElementById("last-updated").textContent = "Last updated: " + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById("last-updated").textContent = "Error loading data";
  }
  btn.disabled = false; btn.innerHTML = "&#x21BB; Refresh";
}
