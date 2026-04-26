const params = new URLSearchParams(location.search);
const code = (params.get('code') || '005930').toUpperCase();
const COLOR = '#2563eb';
const METRICS = [
  { key: 'per',        chartId: 'chart-per',   label: 'PER' },
  { key: 'pbr',        chartId: 'chart-pbr',   label: 'PBR' },
  { key: 'market_cap', chartId: 'chart-cap',   label: '시가총액' },
  { key: 'close',      chartId: 'chart-close', label: '종가' },
];

let dataset = null;

function fmtZ(v) {
  return v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2);
}

async function loadTripleCrossSignal() {
  const sectionEl = document.getElementById('signal-section');
  if (!sectionEl) return;

  try {
    const r = await fetch(`data/screens/triple_cross.json?t=${Date.now()}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const payload = await r.json();
    const all = payload.all_ranked || [];
    const meta = payload.meta || {};
    const me = all.find(s => s.code === code);

    if (!me) {
      sectionEl.style.display = '';
      document.getElementById('signal-rank-line').textContent =
        `universe(${meta.universe_size || 0}종목)에 포함되지 않음 — 시총·흑자·컨센서스 조건 미충족`;
      const body = document.querySelector('.signal-body');
      if (body) body.style.display = 'none';
      return;
    }
    sectionEl.style.display = '';

    const total = all.length;
    document.getElementById('signal-rank-line').innerHTML =
      `universe <b>${total}종목</b> 중 <b>#${me.rank}위</b> · ` +
      `Value <b>${fmtZ(me.value_score)}</b> · Growth <b>${fmtZ(me.growth_score)}</b>`;

    const tierLabel = {
      HIDDEN_GEM: 'Hidden Gem', STRONG_BUY: 'Strong Buy', BUY: 'Buy',
      WATCH: 'Watch', WEAK: 'Weak', MISS: 'Miss',
    };
    const tierEl = document.getElementById('signal-tier');
    tierEl.textContent = tierLabel[me.tier] || me.tier;
    tierEl.className = `signal-tier-badge tier-${(me.tier || 'BUY').toLowerCase()}`;

    const factorList = [
      { lbl: 'PER 저평가', sub: '5Y avg 대비', z: me.s1_per_z, raw: me.s1_per_raw },
      { lbl: 'PBR 저평가', sub: '5Y avg 대비', z: me.s1_pbr_z, raw: me.s1_pbr_raw },
      { lbl: 'Forward 개선', sub: 'Cur → Fwd PER', z: me.s3_per_z, raw: me.s3_per_raw },
      { lbl: '목표가 상승여력', sub: '컨센서스', z: me.upside_z, raw: me.upside_raw },
    ];

    document.getElementById('signal-factors').innerHTML = factorList.map(f => {
      const on = f.z != null && f.z > 0;
      const rawTxt = f.raw == null ? '—' : (f.raw >= 0 ? '+' : '') + (f.raw * 100).toFixed(1) + '%';
      return `
        <div class="factor-item ${on ? 'on' : ''}">
          <div class="factor-lbl">${f.lbl}</div>
          <div class="factor-sub">${f.sub}</div>
          <div class="factor-raw">${rawTxt}</div>
          <div class="factor-z">z = ${fmtZ(f.z)}</div>
        </div>`;
    }).join('');

    const groupBar = (score) => {
      if (score == null) return '<div class="gbar empty"></div>';
      const pct = Math.max(0, Math.min(100, (score + 2) * 25));
      const cls = score >= 0 ? 'pos' : 'neg';
      return `<div class="gbar"><div class="gfill ${cls}" style="width:${pct}%"></div></div>`;
    };
    document.getElementById('signal-groups').innerHTML = `
      <div class="g-row big">
        <span class="g-lbl">Value</span>
        ${groupBar(me.value_score)}
        <span class="g-val">${fmtZ(me.value_score)}</span>
      </div>
      <div class="g-row big">
        <span class="g-lbl">Growth</span>
        ${groupBar(me.growth_score)}
        <span class="g-val">${fmtZ(me.growth_score)}</span>
      </div>`;

    const totalEl = document.getElementById('signal-total');
    totalEl.textContent = fmtZ(me.total_score);
    totalEl.className = 'total-val ' + (me.total_score >= 0 ? 'pos' : 'neg');
  } catch (e) {
    console.warn('[signal] 로드 실패:', e.message);
    sectionEl.style.display = 'none';
  }
}

async function load() {
  // 1차: 일별 풀 데이터 시도
  try {
    const r = await fetch(`data/stocks/${code}.json?t=${Date.now()}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    dataset = await r.json();
    dataset._source = 'daily';
  } catch (e) {
    // 2차: 매트릭스 fallback (월별)
    dataset = await loadFromMatrix(code);
    if (!dataset) {
      document.getElementById('stock-title').innerHTML =
        `❌ <code>${code}</code> 데이터를 찾을 수 없습니다.`;
      return;
    }
  }
  document.getElementById('stock-title').textContent =
    `${dataset.name} (${dataset.ticker}) · ${dataset.market === 'KR' ? '한국' : '미국'}`;
  document.getElementById('updated').textContent =
    new Date(dataset.updated_at).toLocaleString('ko-KR');
  document.getElementById('summary-title').textContent = `${dataset.name} 통계`;

  // 데이터 정밀도 안내
  const sourceNote = dataset._source === 'monthly'
    ? '월별 데이터 (60개월) — 일별 정밀 데이터는 Top 10 종목만 제공'
    : null;
  if (sourceNote) document.getElementById('note').innerHTML = sourceNote;
  else if (dataset.note) document.getElementById('note').textContent = dataset.note;

  bindControls();
  render();
  loadTripleCrossSignal();
  loadAiNotes();
}

async function loadAiNotes() {
  const sectionEl = document.getElementById('ai-section-detail');
  if (!sectionEl) return;
  try {
    const r = await fetch(`data/screens/ai_notes.json?t=${Date.now()}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const doc = await r.json();
    const item = (doc.items || []).find(it => it.code === code);
    if (!item || !item.ai_notes) {
      sectionEl.style.display = 'none';
      return;
    }
    const ai = item.ai_notes;
    sectionEl.style.display = '';

    document.getElementById('ai-detail-oneliner').textContent = ai.one_liner || '';

    const evCls = `ev-${(ai.evidence_strength || 'mod').toLowerCase()}`;
    const rkCls = `rk-${(ai.risk_level || 'low').toLowerCase()}`;
    document.getElementById('ai-detail-badges').innerHTML = `
      <span class="ai-badge ${evCls}">근거 ${ai.evidence_strength || ''}</span>
      <span class="ai-badge ${rkCls}">리스크 ${ai.risk_level || ''}</span>
    `;

    const points = (ai.investment_points || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
    const risks = (ai.risks || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');
    document.getElementById('ai-detail-points').innerHTML = points;
    document.getElementById('ai-detail-risks').innerHTML = risks;

    document.getElementById('ai-detail-verdict').textContent = ai.verdict || '';

    const metaParts = [];
    if (ai.model) metaParts.push(ai.model);
    if (ai.generated_at) metaParts.push(new Date(ai.generated_at).toLocaleString('ko-KR'));
    document.getElementById('ai-detail-meta').textContent = metaParts.join(' · ');
  } catch (e) {
    console.warn('[ai_notes] 로드 실패:', e.message);
    sectionEl.style.display = 'none';
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function loadFromMatrix(code) {
  try {
    const [perR, pbrR, uniR, screenR] = await Promise.all([
      fetch(`data/matrix/per_monthly.json?t=${Date.now()}`),
      fetch(`data/matrix/pbr_monthly.json?t=${Date.now()}`),
      fetch(`data/universe.json?t=${Date.now()}`),
      fetch(`data/screens/triple_cross.json?t=${Date.now()}`),
    ]);
    if (!perR.ok || !pbrR.ok) return null;

    const perDoc = await perR.json();
    const pbrDoc = await pbrR.json();
    const universe = uniR.ok ? await uniR.json() : null;
    const screen = screenR.ok ? await screenR.json() : null;

    const perSeries = perDoc.matrix?.[code];
    const pbrSeries = pbrDoc.matrix?.[code];
    if (!perSeries || Object.keys(perSeries).length === 0) return null;

    // 종목 메타 (universe 또는 screen에서)
    const uniStock = (universe?.passed || universe?.stocks || [])
      .find(s => s.code === code) || (universe?.excluded?.preferred || [])
      .concat(universe?.excluded?.reit || [], universe?.excluded?.spac || [],
              universe?.excluded?.no_forward_per || [], universe?.excluded?.no_target_price || [],
              universe?.excluded?.adverse || [], universe?.excluded?.short_history || [],
              universe?.excluded?.no_data || [])
      .find(s => s.code === code);
    const screenStock = (screen?.all_ranked || []).find(s => s.code === code);

    const name = uniStock?.name || screenStock?.name || code;
    const submarket = uniStock?.market || screenStock?.market;  // KOSPI/KOSDAQ
    const market = 'KR';  // 한국 시장 강제 (헤더 표시용)

    // 시계열 정렬 (월별 → YYYYMMDD)
    const sortedDates = Object.keys(perSeries).sort();
    const dates = sortedDates.map(d => `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`);
    const per = sortedDates.map(d => {
      const v = perSeries[d];
      return (v == null || v <= 0) ? null : v;
    });
    const pbr = sortedDates.map(d => {
      const v = pbrSeries?.[d];
      return (v == null || v <= 0) ? null : v;
    });

    // 매트릭스엔 종가/시총 없음 → null 채움 (차트 카드 자동 숨김)
    const close = sortedDates.map(() => null);
    const market_cap = sortedDates.map(() => null);

    return {
      name,
      ticker: code,
      market,
      frequency: 'monthly',
      dates,
      per,
      pbr,
      div_yield: sortedDates.map(() => null),
      close,
      market_cap,
      market_cap_unit: '억원',
      price_unit: '원',
      forward: {
        per_forward: uniStock?.forward_per ?? screenStock?.forward_per,
        pbr_forward: uniStock?.forward_pbr,
        year_estimate: uniStock?.fwd_year ?? screenStock?.fwd_year,
      },
      consensus: {
        summary: {
          avg_target_price: uniStock?.avg_target_price ?? screenStock?.avg_target,
          broker_count: uniStock?.broker_count ?? screenStock?.broker_count,
        },
        brokers: [],
      },
      updated_at: perDoc.meta?.fetched_at || new Date().toISOString(),
      _source: 'monthly',
    };
  } catch (e) {
    console.warn('[matrix fallback] 실패:', e.message);
    return null;
  }
}

function bindControls() {
  document.querySelectorAll('input[type=checkbox]').forEach(cb =>
    cb.addEventListener('change', render));
  document.getElementById('opt-period').addEventListener('change', render);
}

function getPeriodCutoff() {
  const yrs = parseInt(document.getElementById('opt-period').value, 10);
  const d = new Date();
  d.setFullYear(d.getFullYear() - yrs);
  return d;
}

function filterByPeriod(metricKey) {
  const cutoff = getPeriodCutoff();
  const xs = [], ys = [];
  for (let i = 0; i < dataset.dates.length; i++) {
    const dt = new Date(dataset.dates[i]);
    if (dt < cutoff) continue;
    xs.push(dataset.dates[i]);
    ys.push(dataset[metricKey]?.[i] ?? null);
  }
  return { xs, ys };
}

function statBand(values) {
  const v = values.filter(x => x !== null && Number.isFinite(x));
  if (v.length < 2) return null;
  const mean = v.reduce((a, b) => a + b, 0) / v.length;
  const variance = v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length;
  const sd = Math.sqrt(variance);
  return { mean, sd, n: v.length, min: Math.min(...v), max: Math.max(...v) };
}

function lastNonNull(arr) {
  for (let i = arr.length - 1; i >= 0; i--) if (arr[i] !== null) return { idx: i, val: arr[i] };
  return null;
}

function percentileRank(values, target) {
  const v = values.filter(x => x !== null && Number.isFinite(x));
  if (!v.length) return null;
  return (v.filter(x => x <= target).length / v.length) * 100;
}

function hasAnyData(metricKey) {
  const arr = dataset?.[metricKey];
  return !!(arr && arr.some(v => v !== null && Number.isFinite(v)));
}

function updateCardVisibility() {
  for (const m of METRICS) {
    const card = document.querySelector(`.chart-card[data-metric="${m.key}"]`);
    if (!card) continue;
    card.style.display = hasAnyData(m.key) ? '' : 'none';
  }
  const cards = document.querySelectorAll('.chart-card');
  const visibleCount = [...cards].filter(c => c.style.display !== 'none').length;
  document.querySelector('.charts').classList.toggle('charts-single', visibleCount === 1);
}

function buildTraces(metricKey) {
  let { xs, ys } = filterByPeriod(metricKey);
  if (!ys.length || ys.every(v => v === null)) return { traces: [], annotations: [] };

  const showBand = document.getElementById('opt-band').checked;
  const showMean = document.getElementById('opt-mean').checked;
  const useStat = !['close', 'market_cap'].includes(metricKey);
  const traces = [];
  const annotations = [];
  const stat = statBand(ys);

  if (useStat && showBand && stat && stat.sd > 0) {
    traces.push({
      x: xs, y: xs.map(() => +(stat.mean + stat.sd).toFixed(2)),
      type: 'scatter', mode: 'lines',
      line: { width: 0, color: COLOR }, showlegend: false, hoverinfo: 'skip',
    });
    traces.push({
      x: xs, y: xs.map(() => +(stat.mean - stat.sd).toFixed(2)),
      type: 'scatter', mode: 'lines',
      line: { width: 0, color: COLOR },
      fill: 'tonexty', fillcolor: hexToRgba(COLOR, 0.10),
      showlegend: false, hoverinfo: 'skip',
    });
  }
  if (showMean && stat) {
    traces.push({
      x: [xs[0], xs[xs.length - 1]], y: [stat.mean, stat.mean],
      type: 'scatter', mode: 'lines',
      line: { dash: 'dash', width: 1, color: hexToRgba(COLOR, 0.55) },
      hoverinfo: 'skip', showlegend: false,
    });
  }

  traces.push({
    x: xs, y: ys, type: 'scatter', mode: 'lines',
    name: dataset.name,
    line: { color: COLOR, width: 2, shape: 'spline', smoothing: 0.3 },
    connectgaps: true,
    hovertemplate: '%{x|%Y-%m-%d}<br>%{y:,.2f}<extra>' + dataset.name + '</extra>',
    showlegend: false,
  });

  const fwd = dataset.forward || {};
  const fwdMap = { per: fwd.per_forward, pbr: fwd.pbr_forward };
  const fwdVal = fwdMap[metricKey];
  if (fwdVal != null && Number.isFinite(fwdVal)) {
    traces.push({
      x: [xs[0], xs[xs.length - 1]], y: [fwdVal, fwdVal],
      type: 'scatter', mode: 'lines',
      line: { dash: 'dot', width: 2, color: '#dc2626' },
      hoverinfo: 'skip', showlegend: false,
    });
    annotations.push({
      x: xs[xs.length - 1], y: fwdVal,
      xref: 'x', yref: 'y',
      text: `<b>Fwd ${fwdVal.toFixed(2)}</b>`,
      showarrow: false,
      xanchor: 'right', yanchor: 'bottom',
      font: { color: '#dc2626', size: 11 },
      bgcolor: 'rgba(255,255,255,0.85)',
      bordercolor: '#dc2626',
      borderwidth: 0.5,
      borderpad: 2,
    });
  }
  return { traces, annotations };
}

function render() {
  if (!dataset) return;
  updateCardVisibility();
  for (const m of METRICS) {
    const { traces, annotations } = buildTraces(m.key);
    Plotly.react(m.chartId, traces, {
      margin: { l: 64, r: 16, t: 12, b: 36 },
      xaxis: { type: 'date', showgrid: false, color: '#6b7280' },
      yaxis: { gridcolor: '#eef2f7', color: '#6b7280', automargin: true },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      hovermode: 'x unified',
      font: { family: 'inherit', size: 11 },
      annotations: annotations || [],
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
  }
  renderSummary();
}

function renderSummary() {
  const fmt = (v) => v == null || !Number.isFinite(v) ? '—'
    : (v >= 1000 ? v.toLocaleString('en', { maximumFractionDigits: 0 }) : v.toFixed(2));
  const blocks = [];
  const labelMap = {
    per: 'PER',
    pbr: 'PBR',
    market_cap: `시가총액 (${dataset.market_cap_unit || ''})`,
    close: `주가 (${dataset.price_unit || ''})`,
  };
  const fwd = dataset.forward || {};
  const fwdMap = { per: fwd.per_forward, pbr: fwd.pbr_forward };
  const fwdYearShort = (fwd.year_estimate || '').split('/')[0] || '';

  for (const m of ['per', 'pbr', 'market_cap', 'close']) {
    if (!hasAnyData(m)) continue;
    const { ys } = filterByPeriod(m);
    const stat = statBand(ys);
    const last = lastNonNull(ys);
    if (!last || !stat) continue;
    const z = stat.sd > 0 ? (last.val - stat.mean) / stat.sd : 0;
    const pct = percentileRank(ys, last.val);
    const zCls = z >= 0 ? 'z-pos' : 'z-neg';
    const sign = z >= 0 ? '+' : '';
    const fwdRow = (m === 'per' || m === 'pbr') && fwdMap[m] != null
      ? `<span>Fwd ${fwdYearShort}E</span><span style="color:#dc2626;font-weight:600">${fmt(fwdMap[m])}</span>`
      : '';
    blocks.push(`
      <div class="stat-block">
        <div class="stat-label">${labelMap[m]}</div>
        <div class="stat-val">${fmt(last.val)}</div>
        <div class="stat-grid">
          <span>평균</span><span>${fmt(stat.mean)}</span>
          <span>z-score</span><span class="${zCls}">${sign}${z.toFixed(2)}σ</span>
          <span>최저</span><span>${fmt(stat.min)}</span>
          <span>최고</span><span>${fmt(stat.max)}</span>
          <span>백분위</span><span>${pct.toFixed(0)}%</span>
          ${fwdRow}
        </div>
      </div>`);
  }

  const cs = (dataset.consensus || {}).summary || {};
  const brokers = (dataset.consensus || {}).brokers || [];
  if (cs.broker_count || brokers.length) {
    const lastClose = lastNonNull(dataset.close)?.val;
    const tgt = cs.avg_target_price;
    const upside = (tgt && lastClose) ? ((tgt - lastClose) / lastClose * 100) : null;
    const upsideCls = upside == null ? '' : (upside >= 0 ? 'z-pos' : 'z-neg');
    const upsideStr = upside == null ? '—' : `${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`;
    blocks.push(`
      <div class="stat-block">
        <div class="stat-label">증권사 컨센서스 (${cs.broker_count || brokers.length}곳)</div>
        <div class="stat-val">${fmt(tgt)}원</div>
        <div class="stat-grid">
          <span>현재가 대비</span><span class="${upsideCls}">${upsideStr}</span>
          <span>Fwd PER</span><span>${fmt(cs.avg_per_forward)}</span>
          <span>Fwd EPS</span><span>${fmt(cs.avg_eps_forward)}</span>
          <span>점수</span><span>${cs.consensus_score ?? '—'}</span>
        </div>
      </div>`);
  }

  document.getElementById('summary').innerHTML = blocks.join('');
}

function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '');
  return `rgba(${parseInt(h.slice(0,2),16)},${parseInt(h.slice(2,4),16)},${parseInt(h.slice(4,6),16)},${alpha})`;
}

load();
