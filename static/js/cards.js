// ── SHARED HELPERS ─────────────────────────────────────────────────────────

function signalBadge(d) {
  let badge = `<div class="signal-badge">${d.signal}</div>`;
  if (d.signal === "HOT" && d.signal_age > 10) {
    badge += `<div class="signal-age warn">&#x26A0; Extended (${d.signal_age}d)</div>`;
  } else if (d.signal_age != null) {
    badge += `<div class="signal-age">${d.signal_age}d</div>`;
  }
  // Star rating: signal tier + proximity to entry zone
  const stars = computeStars(d);
  if (stars > 0) {
    badge += `<div class="star-badge star-${stars}">${'\u2B50'.repeat(stars)}</div>`;
  } else if (stars === -1) {
    badge += `<div class="star-badge star-silver">\u2B50</div>`;
  }
  return badge;
}

function computeStars(d) {
  if (!d.institutional || d.signal === "AVOID") return 0;
  const price = d.price;
  const val = d.institutional.val;
  const poc = d.institutional.poc;
  if (!price || !val || !poc || poc <= 0) return 0;

  const inZone = price >= val * 0.97 && price <= poc * 1.01;
  const nearZone = price >= val * 0.94 && price <= poc * 1.04;
  const approachZone = price >= val * 0.90 && price <= poc * 1.08;

  if ((d.signal === "BUY" || d.signal === "HOT") && inZone) return 3;
  if ((d.signal === "BUY" || d.signal === "HOT") && nearZone) return 2;
  if (d.signal === "WATCH" && inZone) return 1;
  if ((d.signal === "BUY" || d.signal === "HOT" || d.signal === "WATCH") && approachZone) return -1; // silver
  return 0;
}

function cardGlowClass(d) {
  const stars = computeStars(d);
  if (stars === 3) return ' star-glow-3';
  if (stars === 2) return ' star-glow-2';
  return '';
}

function retClass(v) {
  return v > 0 ? "pos" : v < 0 ? "neg" : "neu";
}

function trendRow(label, bullish, days, justCrossed, tip) {
  const state = bullish ? '<span class="check">bullish</span>' : '<span class="cross">bearish</span>';
  const cross = justCrossed ? ' <span class="warn">&#x2191; just crossed</span>' : '';
  return `<div class="row" title="${tip || ''}">
    <span class="row-label">${label}</span>
    <span class="row-value">${state} <span class="days-tag">${days}d</span>${cross}</span>
  </div>`;
}

function adxRow(adx, confirmed, days, isStock) {
  const state = confirmed ? '<span class="check">trending</span>' : '<span class="cross">ranging</span>';
  const tip = isStock
    ? 'ADX ≤ 25 = consolidation setup (bullish for stocks). High ADX = move already happened.'
    : 'ADX > 25 = strong trend (bullish for ETFs). Low ADX = no trend.';
  return `<div class="row" title="${tip}">
    <span class="row-label">ADX</span>
    <span class="row-value">${adx} &mdash; ${state} <span class="days-tag">${days}d</span></span>
  </div>`;
}

function fvgTags(fvgs) {
  if (!fvgs || !fvgs.length) return '<span class="muted">&mdash;</span>';
  return fvgs.map(f =>
    `<span class="fvg-tag fvg-${f.type}">FVG ${f.type} ${f.level}</span>`
  ).join('');
}

function scoreBar(pct, unavailable, available) {
  const total = available + unavailable.length;
  const note = unavailable.length
    ? `Scoring on ${available}/${total} signals &mdash; excluded: ${unavailable.join(', ')}`
    : `Scoring on all ${total} signals`;
  return `
    <div class="score-bar-wrap">
      <div class="score-label"><span>Weighted Score</span><span>${pct}%</span></div>
      <div class="score-bar"><div class="score-fill" style="width:${pct}%"></div></div>
    </div>
    <div class="unavailable-note">${note}</div>`;
}

function trendSection(t) {
  const obvWarn = t.distribution_warning ? ' <span class="warn">&#x26A0; distribution</span>' : '';
  const deltaVal = t.delta_positive
    ? '<span class="check">buyers dominant</span>'
    : '<span class="cross">sellers dominant</span>';
  const rsiClass = t.rsi < 30 ? 'check' : t.rsi > 70 ? 'cross' : (50 <= t.rsi && t.rsi <= 70) ? 'check' : 'muted';
  const rsiLabel = t.rsi < 30 ? 'oversold' : t.rsi > 70 ? 'overbought' : (50 <= t.rsi && t.rsi <= 70) ? 'momentum' : 'neutral';
  const smaRegime = t.above_sma200
    ? '<span class="check">above SMA200</span>'
    : '<span class="cross">below SMA200</span>';
  const rsiTip = 'RSI 50-70 = momentum sweet spot (stocks). RSI < 30 = oversold mean reversion (ETFs). RSI > 70 = overbought.';
  const regimeTip = 'Price above 200-day moving average = long-term uptrend intact. Below = broken trend.';
  const obvTip = t.distribution_warning
    ? 'Price rising but volume falling — institutions may be selling into strength.'
    : t.obv_rising ? 'Volume confirms the price move — accumulation.' : 'Volume declining — distribution or lack of conviction.';
  const deltaTip = 'Approximates buying vs selling pressure from candle close position within the high-low range.';
  const adxDirTip = '+DI > -DI = bullish price direction. -DI > +DI = bearish direction.';
  const adxDir = t.adx_confirmed !== undefined
    ? (t.days_adx !== undefined ? `<span class="days-tag">${t.days_adx}d</span>` : '')
    : '';
  return `
    <div class="section-title">Scored Signals</div>
    <div class="row" title="${regimeTip}"><span class="row-label">Regime</span><span class="row-value">${smaRegime}</span></div>
    <div class="row" title="${adxDirTip}"><span class="row-label">ADX Direction</span><span class="row-value">${t.adx} &mdash; ${t.adx_confirmed ? '<span class="check">bullish</span>' : '<span class="cross">bearish</span>'} ${adxDir}</span></div>
    <div class="row" title="${deltaTip}"><span class="row-label">Delta Volume</span><span class="row-value">${deltaVal}</span></div>
    <div class="row" title="${obvTip}"><span class="row-label">OBV</span><span class="row-value">${t.obv_rising ? '<span class="check">rising</span>' : '<span class="cross">falling</span>'}${obvWarn}</span></div>
    <div class="row" title="MACD line above signal line = bullish momentum. Just crossed = fresh trigger."><span class="row-label">MACD</span><span class="row-value">${t.macd_bullish ? '<span class="check">bullish</span>' : '<span class="cross">bearish</span>'} <span class="days-tag">${t.days_macd}d</span>${t.macd_crossed ? ' <span class="warn">&#x2191; just crossed</span>' : ''}</span></div>
    <div class="section-title">Additional Context</div>
    <div class="row" title="${rsiTip}"><span class="row-label">RSI</span><span class="row-value"><span class="${rsiClass}">${t.rsi} &mdash; ${rsiLabel}</span></span></div>
    ${trendRow('Golden Cross (50/200)', t.golden_cross, t.days_golden, false, 'SMA50 above SMA200 = long-term bullish structure. Lagging but widely followed.')}
    ${trendRow('Fast Cross (20/50)',    t.fast_cross,   t.days_fast,   false, 'SMA20 above SMA50 = medium-term momentum aligned. Faster signal than golden cross.')}
    `;
}

function levelsSection(levels) {
  return `
    <div class="section-title">Key Levels</div>
    <div class="levels-grid">
      <div class="level-box" title="VAL to POC range. Where institutions are likely accumulating. Best risk/reward entry."><div class="lbl">Entry Zone</div><div class="val">${levels.entry_zone}</div></div>
      <div class="level-box" title="Value Area High. Where institutions are likely distributing. Take profit zone."><div class="lbl">Target</div><div class="val">${levels.target}</div></div>
      <div class="level-box" title="1% below VAL. If price closes here, the institutional thesis is broken. Exit."><div class="lbl">Invalidation</div><div class="val">${levels.invalidation}</div></div>
    </div>`;
}

function bottomWatch(b) {
  if (!b) return '';
  const rows = [
    ['Price at VAL',           b.signals.price_at_val],
    ['RSI Divergence',         b.signals.rsi_divergence],
    [`RSI Oversold (${b.rsi})`,b.signals.rsi_oversold],
    ['OBV Divergence',         b.signals.obv_divergence],
    ['ATR Exhaustion',         b.signals.atr_exhaustion],
    ['ADX Weakening',          b.signals.adx_weakening],
    ['COT Extreme',            b.signals.cot_extreme],
  ].map(([label, fired]) =>
    `<div class="bottom-row">
      <span class="bottom-row-label">${label}</span>
      <span class="${fired ? 'bottom-row-val-on' : 'bottom-row-val-off'}">${fired ? '&#9679; confirmed' : '&#9675; not yet'}</span>
    </div>`
  ).join('');
  return `
    <div class="bottom-box ${b.label_class}">
      <div class="bottom-summary">
        <span class="bottom-title">&#x2B07; Bottom Watch &mdash; ${b.label}</span>
        <span class="bottom-score">${b.score}</span>
      </div>
      <div class="bottom-hint">hover for details</div>
      <div class="bottom-detail">${rows}</div>
    </div>`;
}

function cardError(ticker, name, msg) {
  return `<div class="card-header"><div>
    <div class="ticker-name">${name} <span style="font-size:0.9rem;color:#4f8ef7;font-weight:500">(${ticker})</span></div>
  </div></div><div class="error-state">&#x26A0; ${msg}</div>`;
}

function exportPdf(panelId, title) {
  // Mark which panel to print
  document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('printing'));
  document.getElementById(panelId).classList.add('printing');
  // Add print header
  let header = document.getElementById('print-header');
  if (!header) {
    header = document.createElement('div');
    header.id = 'print-header';
    header.className = 'print-header';
    document.body.prepend(header);
  }
  header.innerHTML = `<h2>HEATSEEKER - ${title}</h2><div class="print-date">${new Date().toLocaleString()}</div>`;
  window.print();
}
