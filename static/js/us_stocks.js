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

  card.className = `card ${d.signal_class}${cardGlowClass(d)}`;
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="ticker-name">${d.name} <span style="font-size:0.9rem;color:#4f8ef7;font-weight:500">(${d.ticker})</span></div>
        <div class="ticker-price">$${d.price} <span class="${d.daily_change >= 0 ? 'check' : 'cross'}">${d.daily_change >= 0 ? '+' : ''}${d.daily_change}%</span></div>
      </div>
      ${signalBadge(d)}
    </div>
    ${scoreBar(d.score_pct, d.unavailable_signals, d.available_signals)}

    <div class="section-title">Scored Signals</div>
    <div class="row" title="Outperforming benchmark over 20 days. Strongest signal in the algo (0.28 weight)."><span class="row-label">Relative Strength (20d)</span><span class="row-value">${rsVal}</span></div>
    <div class="row" title="Earnings within 14 days = risk. Further away = safe."><span class="row-label">Earnings Proximity</span><span class="row-value">${epVal}</span></div>

    ${trendSection(d.trend)}
    ${levelsSection(d.levels)}

    <div class="row" title="2-week window before quarter end. Institutions window-dress portfolios."><span class="row-label">Quarter End Risk</span><span class="row-value">${inst.quarter_end_risk ? '<span class="warn">&#x26A0; Yes</span>' : '<span class="check">No</span>'}</span></div>
    <div class="row" title="Price gaps between candles that act as magnets."><span class="row-label">Fair Value Gaps</span><span class="row-value">${fvgTags(inst.fvgs)}</span></div>
    <div class="row" title="POC = highest volume price. VAH = distribution zone. VAL = accumulation zone."><span class="row-label">POC / VAH / VAL</span><span class="row-value">$${inst.poc} / $${inst.vah} / $${inst.val}</span></div>

    ${bottomWatch(d.bottom_watch)}`;
}

async function loadUsStocks() {
  const btn = document.getElementById("us-stock-refresh-btn");
  btn.disabled = true; btn.textContent = "Loading...";
  const grid = document.getElementById("us-stock-grid");
  grid.innerHTML = "";

  const results = [];
  const source = new EventSource("/api/stream/us-stocks?fresh=1");
  source.onmessage = function(e) {
    if (e.data === "[DONE]") {
      source.close();
      btn.disabled = false; btn.innerHTML = "&#x21BB; Refresh";
      document.getElementById("last-updated").textContent = "Last updated: " + new Date().toLocaleTimeString();
      return;
    }
    const d = JSON.parse(e.data);
    results.push(d);
    results.sort((a, b) => (b.score || 0) - (a.score || 0));
    grid.innerHTML = "";
    results.forEach(r => {
      const card = document.createElement("div");
      card.className = "card loading";
      card.id = "us-" + r.ticker;
      grid.appendChild(card);
      renderUsStockCard(r);
    });
  };
  source.onerror = function() {
    source.close();
    btn.disabled = false; btn.innerHTML = "&#x21BB; Refresh";
  };
}
