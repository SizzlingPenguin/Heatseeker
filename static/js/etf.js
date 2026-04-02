// ── ETF TAB ────────────────────────────────────────────────────────────────

const ETF_NAMES = {
  SPY: "S&P 500", QQQ: "Nasdaq 100", GLD: "Gold",
  SLV: "Silver",  TLT: "US Bonds",   USO: "Oil",
  XLK: "Technology", XLF: "Financials", XLE: "Energy",
  XLV: "Healthcare", XLI: "Industrials", XLP: "Consumer Staples",
  XLY: "Consumer Disc.", XLC: "Communications", XLB: "Materials",
  XLU: "Utilities", XLRE: "Real Estate", SMH: "Semiconductors",
  XRT: "Retail", IGV: "Software", IBIT: "Bitcoin",
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

  card.className = `card ${d.signal_class}${cardGlowClass(d)}`;
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="ticker-name">${ETF_NAMES[d.ticker] || d.ticker} <span style="font-size:0.9rem;color:#4f8ef7;font-weight:500">(${d.ticker})</span></div>
        <div class="ticker-price">$${d.price} <span class="${d.daily_change >= 0 ? 'check' : 'cross'}">${d.daily_change >= 0 ? '+' : ''}${d.daily_change}%</span></div>
      </div>
      ${signalBadge(d)}
    </div>
    ${scoreBar(d.score_pct, d.unavailable_signals, d.available_signals)}

    <div class="section-title">Scored Signals</div>
    <div class="row" title="CFTC Commitment of Traders report. Net long index > 60 = institutions are bullish. Weekly data."><span class="row-label">COT Bias</span><span class="row-value"><span class="${cotColor}">${inst.cot_bias}${cotIndex}</span></span></div>
    <div class="row" title="Strike price where most options expire worthless. Market makers hedge toward this price near expiry. Within 5% = bullish."><span class="row-label">Max Pain</span><span class="row-value">${inst.max_pain ? '$' + inst.max_pain : '<span class="muted">N/A</span>'}</span></div>
    <div class="row" title="Outperforming SPY over 20 days."><span class="row-label">Relative Strength (20d)</span><span class="row-value">${d.fired && d.fired.relative_strength === true ? '<span class="check">outperforming</span>' : d.fired && d.fired.relative_strength === false ? '<span class="cross">underperforming</span>' : '<span class="muted">N/A</span>'}</span></div>

    ${trendSection(d.trend)}
    ${levelsSection(d.levels)}

    <div class="row" title="2-week window before quarter end. Institutions window-dress portfolios, creating distribution risk."><span class="row-label">Quarter End Risk</span><span class="row-value">${inst.quarter_end_risk ? '<span class="warn">&#x26A0; Yes</span>' : '<span class="check">No</span>'}</span></div>
    <div class="row" title="Price gaps between candles that act as magnets. Institutions often return to fill them."><span class="row-label">Fair Value Gaps</span><span class="row-value">${fvgTags(inst.fvgs)}</span></div>
    <div class="row" title="POC = highest volume price (institutional cost basis). VAH = distribution zone. VAL = accumulation zone."><span class="row-label">POC / VAH / VAL</span><span class="row-value">$${inst.poc} / $${inst.vah} / $${inst.val}</span></div>

    ${bottomWatch(d.bottom_watch)}`;
}

async function loadEtfs() {
  const btn = document.getElementById("etf-refresh-btn");
  btn.disabled = true; btn.textContent = "Loading...";
  const grid = document.getElementById("etf-grid");
  grid.innerHTML = "";

  const results = [];
  const source = new EventSource("/api/stream/etf");
  source.onmessage = function(e) {
    if (e.data === "[DONE]") {
      source.close();
      btn.disabled = false; btn.innerHTML = "&#x21BB; Refresh";
      document.getElementById("last-updated").textContent = "Last updated: " + new Date().toLocaleTimeString();
      return;
    }
    const d = JSON.parse(e.data);
    results.push(d);
    // Re-sort and rebuild grid
    results.sort((a, b) => (b.score || 0) - (a.score || 0));
    grid.innerHTML = "";
    results.forEach(r => {
      const card = document.createElement("div");
      card.className = "card loading";
      card.id = "card-" + r.ticker;
      grid.appendChild(card);
      renderEtfCard(r);
    });
  };
  source.onerror = function() {
    source.close();
    btn.disabled = false; btn.innerHTML = "&#x21BB; Refresh";
  };
}
