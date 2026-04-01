// ── US STOCKS TAB ──────────────────────────────────────────────────────────

function renderUsStockCard(d) {
  const id   = "us-" + d.ticker;
  const card = document.getElementById(id);
  if (!card) return;

  if (d.error) {
    card.className = "card error";
    card.innerHTML = cardError(d.ticker, d.name, d.error);
    return;
  }

  const inst = d.institutional;
  const rs   = inst.relative_strength;
  const ep   = inst.earnings_proximity;

  const rsVal = rs.outperforming === null
    ? '<span class="muted">unavailable</span>'
    : rs.outperforming
      ? `<span class="check">outperforming</span> <span class="muted">(${rs.stock_return > 0 ? '+' : ''}${rs.stock_return}% vs SPY ${rs.bench_return > 0 ? '+' : ''}${rs.bench_return}%)</span>`
      : `<span class="cross">underperforming</span> <span class="muted">(${rs.stock_return > 0 ? '+' : ''}${rs.stock_return}% vs SPY ${rs.bench_return > 0 ? '+' : ''}${rs.bench_return}%)</span>`;

  const epVal = ep.safe === null
    ? '<span class="muted">unavailable</span>'
    : ep.safe
      ? `<span class="check">safe</span> <span class="muted">(${ep.days_to_earnings}d away)</span>`
      : `<span class="warn">&#x26A0; ${ep.days_to_earnings}d to earnings</span>`;

  card.className = `card ${d.signal_class}`;
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="ticker-name">${d.name} <span style="font-size:0.9rem;color:#4f8ef7;font-weight:500">(${d.ticker})</span></div>
        <div class="ticker-price">$${d.price}</div>
      </div>
      <div class="signal-badge">${d.signal}</div>
    </div>
    ${scoreBar(d.score_pct, d.unavailable_signals, d.available_signals)}

    <div class="section-title">Institutional Layer</div>
    <div class="row"><span class="row-label">Relative Strength (20d)</span><span class="row-value">${rsVal}</span></div>
    <div class="row"><span class="row-label">Earnings Proximity</span><span class="row-value">${epVal}</span></div>
    <div class="row"><span class="row-label">Quarter End Risk</span><span class="row-value">${inst.quarter_end_risk ? '<span class="warn">&#x26A0; Yes</span>' : '<span class="check">No</span>'}</span></div>
    <div class="row"><span class="row-label">Fair Value Gaps</span><span class="row-value">${fvgTags(inst.fvgs)}</span></div>
    <div class="row"><span class="row-label">POC / VAH / VAL</span><span class="row-value">$${inst.poc} / $${inst.vah} / $${inst.val}</span></div>

    ${trendSection(d.trend)}
    ${levelsSection(d.levels)}
    ${bottomWatch(d.bottom_watch)}`;
}

async function loadUsStocks() {
  const btn = document.getElementById("us-stock-refresh-btn");
  btn.disabled = true; btn.textContent = "Loading...";
  document.querySelectorAll("#us-stock-grid .card").forEach(c => {
    c.className = "card loading";
    c.innerHTML = `<div class="loading-state"><div class="spinner"></div>Loading...</div>`;
  });
  try {
    const data = await fetch("/api/analyze/us-stocks").then(r => r.json());
    data.forEach(renderUsStockCard);
    document.getElementById("last-updated").textContent = "Last updated: " + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById("last-updated").textContent = "Error loading US stocks";
  }
  btn.disabled = false; btn.innerHTML = "&#x21BB; Refresh";
}
