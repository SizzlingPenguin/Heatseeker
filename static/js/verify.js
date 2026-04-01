// ── VERIFY TAB ─────────────────────────────────────────────────────────────

async function runVerify() {
  const input = document.getElementById("verify-input");
  const btn   = document.getElementById("verify-btn");
  const out   = document.getElementById("verify-results");
  const ticker = input.value.trim().toUpperCase();
  if (!ticker) return;

  btn.disabled = true; btn.textContent = "Running...";
  out.innerHTML = `<div class="loading-state"><div class="spinner"></div>Running backtest on ${ticker}... this may take a minute</div>`;

  try {
    const data = await fetch(`/api/verify?ticker=${encodeURIComponent(ticker)}`).then(r => r.json());
    if (data.error) {
      out.innerHTML = `<div class="error-state">&#x26A0; ${data.error}</div>`;
    } else {
      out.innerHTML = renderVerifyResults(data);
    }
  } catch(e) {
    out.innerHTML = `<div class="error-state">&#x26A0; Request failed</div>`;
  }
  btn.disabled = false; btn.textContent = "Run Backtest";
}

function renderVerifyResults(d) {
  const signals = ["STRONG BUY", "WATCH", "NO TRADE", "AVOID"];
  const fwds = [5, 10, 20];

  // Summary table
  let rows = "";
  for (const sig of signals) {
    const s = d.summary[sig];
    if (!s) continue;
    const cls = sig === "STRONG BUY" ? "check" : sig === "WATCH" ? "warn" : sig === "AVOID" ? "cross" : "muted";
    rows += `<tr>
      <td><span class="${cls}">${sig}</span></td>`;
    for (const fwd of fwds) {
      const p = s[fwd + "d"];
      rows += `<td>${p.count}</td>
        <td class="${p.avg_return > 0 ? 'check' : 'cross'}">${p.avg_return > 0 ? '+' : ''}${p.avg_return}%</td>
        <td>${p.win_rate}%</td>
        <td class="cross">${p.max_dd}%</td>`;
    }
    rows += `</tr>`;
  }

  // Ordering
  let orderHtml = "";
  if (d.ordering && d.ordering.length > 0) {
    const parts = d.ordering.map(o =>
      `<span class="${o.avg_20d > 0 ? 'check' : 'cross'}">${o.signal} ${o.avg_20d > 0 ? '+' : ''}${o.avg_20d}%</span> <span class="muted">(n=${o.count})</span>`
    );
    const correct = d.ordering.length <= 1 ||
      d.ordering.every((o, i) => i === 0 || o.avg_20d <= d.ordering[i-1].avg_20d);
    orderHtml = `
      <div class="verify-ordering ${correct ? 'order-correct' : 'order-wrong'}">
        <span class="order-label">${correct ? '&#x2705; Signal ordering correct' : '&#x26A0; Signal ordering inverted'}</span>
        <div class="order-chain">${parts.join(' &gt; ')}</div>
      </div>`;
  }

  // Bottom watch table
  let bwHtml = "";
  if (d.bottom_watch && Object.keys(d.bottom_watch).length > 0) {
    let bwRows = "";
    for (const label of ["HIGH PROBABILITY BOTTOM", "POSSIBLE BOTTOM", "NO BOTTOM SIGNAL"]) {
      const s = d.bottom_watch[label];
      if (!s) continue;
      const cls = label === "HIGH PROBABILITY BOTTOM" ? "check" : label === "POSSIBLE BOTTOM" ? "warn" : "muted";
      bwRows += `<tr><td><span class="${cls}">${label}</span></td>`;
      for (const fwd of fwds) {
        const p = s[fwd + "d"];
        bwRows += `<td>${p.count}</td>
          <td class="${p.avg_return > 0 ? 'check' : 'cross'}">${p.avg_return > 0 ? '+' : ''}${p.avg_return}%</td>
          <td>${p.win_rate}%</td>
          <td class="cross">${p.max_dd}%</td>`;
      }
      bwRows += `</tr>`;
    }
    bwHtml = `
      <div class="section-title" style="margin-top:20px">Bottom Watch Backtest</div>
      <table class="verify-table">
        <thead>
          <tr>
            <th>Label</th>
            <th colspan="4">5-Day Forward</th>
            <th colspan="4">10-Day Forward</th>
            <th colspan="4">20-Day Forward</th>
          </tr>
          <tr>
            <th></th>
            <th>N</th><th>Avg</th><th>Win%</th><th>MaxDD</th>
            <th>N</th><th>Avg</th><th>Win%</th><th>MaxDD</th>
            <th>N</th><th>Avg</th><th>Win%</th><th>MaxDD</th>
          </tr>
        </thead>
        <tbody>${bwRows}</tbody>
      </table>`;
  }

  return `
    <div class="verify-header">
      <div class="verify-ticker">${d.ticker}</div>
      <div class="verify-meta">
        <span class="verify-tag">${d.type.toUpperCase()}</span>
        <span class="muted">${d.backtest_bars} trading days &mdash; ${d.start_date} to ${d.end_date}</span>
      </div>
    </div>
    ${orderHtml}
    <table class="verify-table">
      <thead>
        <tr>
          <th>Signal</th>
          <th colspan="4">5-Day Forward</th>
          <th colspan="4">10-Day Forward</th>
          <th colspan="4">20-Day Forward</th>
        </tr>
        <tr>
          <th></th>
          <th>N</th><th>Avg</th><th>Win%</th><th>MaxDD</th>
          <th>N</th><th>Avg</th><th>Win%</th><th>MaxDD</th>
          <th>N</th><th>Avg</th><th>Win%</th><th>MaxDD</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${bwHtml}`;
}


// ── SIGNAL ANALYSIS ────────────────────────────────────────────────────────

async function runSignal() {
  const input = document.getElementById("verify-input");
  const btn   = document.getElementById("signal-btn");
  const out   = document.getElementById("signal-results");
  const ticker = input.value.trim().toUpperCase();
  if (!ticker) return;

  btn.disabled = true; btn.textContent = "Analyzing...";
  out.innerHTML = `<div class="loading-state"><div class="spinner"></div>Analyzing ${ticker}...</div>`;

  try {
    const d = await fetch(`/api/signal?ticker=${encodeURIComponent(ticker)}`).then(r => r.json());
    if (d.error) {
      out.innerHTML = `<div class="error-state">&#x26A0; ${d.error}</div>`;
    } else {
      out.innerHTML = `<div class="signal-card-wrap">${renderSignalCard(d)}</div>`;
    }
  } catch(e) {
    out.innerHTML = `<div class="error-state">&#x26A0; Request failed</div>`;
  }
  btn.disabled = false; btn.textContent = "Signal Analysis";
}

function renderSignalCard(d) {
  const isEtf = d.type === "etf";
  const inst = d.institutional;
  const name = d.name || d.ticker;
  const priceStr = (d.currency === "USD" || isEtf) ? `$${d.price}` : `${d.price} ${d.currency || ''}`;

  // Institutional layer — differs by type
  let instHtml = "";
  if (isEtf) {
    const cotColor = inst.cot_bias === "bullish" ? "check" : inst.cot_bias === "bearish" ? "cross" : "warn";
    const cotIndex = inst.cot_index !== null ? ` (${inst.cot_index}/100)` : "";
    instHtml = `
      <div class="row"><span class="row-label">COT Bias</span><span class="row-value"><span class="${cotColor}">${inst.cot_bias}${cotIndex}</span></span></div>
      <div class="row"><span class="row-label">Quarter End Risk</span><span class="row-value">${inst.quarter_end_risk ? '<span class="warn">&#x26A0; Yes</span>' : '<span class="check">No</span>'}</span></div>
      <div class="row"><span class="row-label">Max Pain</span><span class="row-value">${inst.max_pain ? '$' + inst.max_pain : '<span class="muted">N/A</span>'}</span></div>`;
  } else {
    const rs = inst.relative_strength;
    const ep = inst.earnings_proximity;
    const benchLabel = d.currency === "USD" ? "SPY" : "OMX";
    const rsVal = rs.outperforming === null
      ? '<span class="muted">unavailable</span>'
      : rs.outperforming
        ? `<span class="check">outperforming</span> <span class="muted">(${rs.stock_return > 0 ? '+' : ''}${rs.stock_return}% vs ${benchLabel} ${rs.bench_return > 0 ? '+' : ''}${rs.bench_return}%)</span>`
        : `<span class="cross">underperforming</span> <span class="muted">(${rs.stock_return > 0 ? '+' : ''}${rs.stock_return}% vs ${benchLabel} ${rs.bench_return > 0 ? '+' : ''}${rs.bench_return}%)</span>`;
    const epVal = ep.safe === null
      ? '<span class="muted">unavailable</span>'
      : ep.safe
        ? `<span class="check">safe</span> <span class="muted">(${ep.days_to_earnings}d away)</span>`
        : `<span class="warn">&#x26A0; ${ep.days_to_earnings}d to earnings</span>`;
    instHtml = `
      <div class="row"><span class="row-label">Relative Strength (20d)</span><span class="row-value">${rsVal}</span></div>
      <div class="row"><span class="row-label">Earnings Proximity</span><span class="row-value">${epVal}</span></div>
      <div class="row"><span class="row-label">Quarter End Risk</span><span class="row-value">${inst.quarter_end_risk ? '<span class="warn">&#x26A0; Yes</span>' : '<span class="check">No</span>'}</span></div>`;
  }

  return `
    <div class="card ${d.signal_class}">
      <div class="card-header">
        <div>
          <div class="ticker-name">${name} <span style="font-size:0.9rem;color:#4f8ef7;font-weight:500">(${d.ticker})</span></div>
          <div class="ticker-price">${priceStr} <span class="verify-tag">${d.type.toUpperCase()}</span></div>
        </div>
        <div class="signal-badge">${d.signal}</div>
      </div>
      ${scoreBar(d.score_pct, d.unavailable_signals, d.available_signals)}

      <div class="section-title">Institutional Layer</div>
      ${instHtml}
      <div class="row"><span class="row-label">Fair Value Gaps</span><span class="row-value">${fvgTags(inst.fvgs)}</span></div>
      <div class="row"><span class="row-label">POC / VAH / VAL</span><span class="row-value">${inst.poc} / ${inst.vah} / ${inst.val}</span></div>

      ${trendSection(d.trend)}
      ${levelsSection(d.levels)}
      ${bottomWatch(d.bottom_watch)}
    </div>`;
}
