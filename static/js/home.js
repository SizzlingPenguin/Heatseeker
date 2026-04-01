// ── HOME TAB ───────────────────────────────────────────────────────────────

async function loadHome() {
  const out = document.getElementById("home-market");
  try {
    const data = await fetch("/api/market").then(r => r.json());
    out.innerHTML = renderMarket(data);
  } catch(e) {
    out.innerHTML = `<div class="muted" style="text-align:center">Could not load market data</div>`;
  }
}

function renderMarket(items) {
  const cards = items.map(d => {
    const chgClass = d.change_pct > 0 ? "check" : d.change_pct < 0 ? "cross" : "muted";
    const arrow = d.change_pct > 0 ? "&#x25B2;" : d.change_pct < 0 ? "&#x25BC;" : "";
    return `
      <div class="market-card">
        <div class="market-label">${d.name}</div>
        <div class="market-price">${d.price}</div>
        <div class="market-change ${chgClass}">${arrow} ${d.change_pct > 0 ? '+' : ''}${d.change_pct}%</div>
      </div>`;
  }).join("");
  return `<div class="market-grid">${cards}</div>`;
}
