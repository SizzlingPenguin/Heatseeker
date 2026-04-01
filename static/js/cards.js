// ── SHARED HELPERS ─────────────────────────────────────────────────────────

function retClass(v) {
  return v > 0 ? "pos" : v < 0 ? "neg" : "neu";
}

function trendRow(label, bullish, days, justCrossed) {
  const state = bullish ? '<span class="check">bullish</span>' : '<span class="cross">bearish</span>';
  const cross = justCrossed ? ' <span class="warn">&#x2191; just crossed</span>' : '';
  return `<div class="row">
    <span class="row-label">${label}</span>
    <span class="row-value">${state} <span class="days-tag">${days}d</span>${cross}</span>
  </div>`;
}

function adxRow(adx, confirmed, days) {
  const state = confirmed ? '<span class="check">trending</span>' : '<span class="cross">ranging</span>';
  return `<div class="row">
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
  return `
    <div class="section-title">Trend Layer</div>
    ${adxRow(t.adx, t.adx_confirmed, t.days_adx)}
    ${trendRow('Golden Cross (50/200)', t.golden_cross, t.days_golden, false)}
    ${trendRow('Fast Cross (20/50)',    t.fast_cross,   t.days_fast,   false)}
    ${trendRow('MACD', t.macd_bullish, t.days_macd, t.macd_crossed)}
    <div class="row"><span class="row-label">RSI</span><span class="row-value"><span class="${rsiClass}">${t.rsi} &mdash; ${rsiLabel}</span></span></div>
    <div class="row"><span class="row-label">Regime</span><span class="row-value">${smaRegime}</span></div>
    <div class="row"><span class="row-label">OBV</span><span class="row-value">${t.obv_rising ? '<span class="check">rising</span>' : '<span class="cross">falling</span>'}${obvWarn}</span></div>
    <div class="row"><span class="row-label">Delta Volume</span><span class="row-value">${deltaVal}</span></div>`;
}

function levelsSection(levels) {
  return `
    <div class="section-title">Key Levels</div>
    <div class="levels-grid">
      <div class="level-box"><div class="lbl">Entry Zone</div><div class="val">${levels.entry_zone}</div></div>
      <div class="level-box"><div class="lbl">Target</div><div class="val">${levels.target}</div></div>
      <div class="level-box"><div class="lbl">Invalidation</div><div class="val">${levels.invalidation}</div></div>
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
