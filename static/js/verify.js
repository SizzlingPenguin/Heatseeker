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
    </table>`;
}
