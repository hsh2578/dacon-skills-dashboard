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

// v6 (2026-11-24) — 원인 분류 · 기대 괴리 (app.js 와 같은 라벨)
const CAUSE_LABEL = {
  CYCLICAL_PEAK: '경기 정점', STRUCTURAL_DECLINE: '구조적 쇠퇴', TEMPORARY_SHOCK: '일시 충격',
  ONE_OFF_ACCOUNTING: '일회성 회계', GOVERNANCE_DISCOUNT: '지배구조 할인', NEGLECT: '소외',
  REGULATORY_MACRO: '규제·거시', BALANCE_SHEET_TRAP: '재무 함정',
};
const GAP_LABEL = {
  TOO_PESSIMISTIC: ['가격이 과도하게 비관적', 'uc-temporary'],
  FAIR: ['가격이 전망 반영', ''],
  NOT_PESSIMISTIC_ENOUGH: ['함정 경계', 'uc-structural'],
};


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
      `universe <b>${total}종목</b> 중 정량 <b>#${me.rank}위</b> · ` +
      `가치 <b>${fmtZ(me.value_score)}</b> · 전망 <b>${fmtZ(me.growth_score)}</b>` +
      (me.quality_pass === false ? ' · <b style="color:var(--warn)">퀄리티 하위 20% (Top 자격 없음)</b>' : '') +
      (me.cyclical_flag ? ' · <b style="color:var(--warn)">이익 정점 의심</b>' : '');

    const tierLabel = {
      HIDDEN_GEM: 'Hidden Gem', STRONG_BUY: 'Strong Buy', BUY: 'Buy',
      WATCH: 'Watch', WEAK: 'Weak', MISS: 'Miss',
    };
    const tierEl = document.getElementById('signal-tier');
    // v6: 전 종목 같은 티어라 정보가 없다 — 숨김 (순위·기대 괴리가 결론을 대신한다)
    tierEl.style.display = 'none';

    const factorList = [
      { lbl: 'PER 할인', sub: '5Y 중앙 대비', z: me.s1_per_z, raw: me.s1_per_raw },
      { lbl: 'PBR 할인', sub: '5Y 중앙 대비', z: me.s1_pbr_z, raw: me.s1_pbr_raw },
      { lbl: '전망 할인', sub: 'Fwd PER vs 5Y 중앙', z: me.s3_per_z, raw: me.s3_per_raw },
      { lbl: '가격 가정 이익', sub: '컨센서스 대비 배수', z: null, raw: null,
        txt: me.implied_fade == null ? '—' : '×' + me.implied_fade.toFixed(2),
        on: me.implied_fade != null && me.implied_fade < 1 },
    ];

    document.getElementById('signal-factors').innerHTML = factorList.map(f => {
      const on = f.on ?? (f.z != null && f.z > 0);
      const rawTxt = f.txt ?? (f.raw == null ? '—' : (f.raw >= 0 ? '+' : '') + (f.raw * 100).toFixed(1) + '%');
      return `
        <div class="factor-item ${on ? 'on' : ''}">
          <div class="factor-lbl">${f.lbl}</div>
          <div class="factor-sub">${f.sub}</div>
          <div class="factor-raw">${rawTxt}</div>
          <div class="factor-z">${f.z == null ? '' : 'z = ' + fmtZ(f.z)}</div>
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
        <span class="g-lbl">가치</span>
        ${groupBar(me.value_score)}
        <span class="g-val">${fmtZ(me.value_score)}</span>
      </div>
      <div class="g-row big">
        <span class="g-lbl">전망</span>
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
    const [r, scR] = await Promise.all([
      fetch(`data/daily/${code}.json?t=${Date.now()}`),
      fetch(`data/screens/triple_cross.json?t=${Date.now()}`),
    ]);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const sc = scR.ok ? ((await scR.json()).all_ranked || []).find(s => s.code === code) : null;
    const ymd = (x) => `${x.slice(0, 4)}-${x.slice(4, 6)}-${x.slice(6, 8)}`;
    dataset = {
      name: d.name || sc?.name || code, ticker: code, market: 'KR', frequency: 'daily',
      dates: d.dates.map(ymd), per: d.per, pbr: d.pbr,
      market_cap: d.mcap_억, market_cap_unit: '억원', close: d.close || d.dates.map(() => null), price_unit: '원',
      forward: { per_forward: sc?.forward_per, year_estimate: sc?.fwd_year },
      consensus: { summary: { avg_target_price: sc?.avg_target, broker_count: sc?.broker_count }, brokers: [] },
      updated_at: new Date().toISOString(),
      note: 'PER·PBR = (보통주+우선주 시가총액) ÷ DART 지배주주 TTM 순이익·자본, 공시 기한 이후 반영',
      _source: 'daily',
    };
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
    ? '월별 데이터 (60개월) — 일별 정밀 데이터는 Top 30 종목만 제공'
    : null;
  if (sourceNote) document.getElementById('note').innerHTML = sourceNote;
  else if (dataset.note) document.getElementById('note').textContent = dataset.note;

  bindControls();
  render();
  renderBriefPrice();
  loadTripleCrossSignal();
  loadAiNotes();
  renderFinChart(code);
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
    renderBriefing(ai.briefing, ai.info_grade || ai.resolution?.info_grade, ai.buy_check, item);

    document.getElementById('ai-detail-oneliner').textContent = ai.one_liner || '';

    const ucEl = document.getElementById('ai-detail-uc');
    const uc = ai.undervaluation_cause;
    if (ucEl && uc && uc.text) {
      ucEl.style.display = '';
      const natEl = document.getElementById('ai-detail-uc-nat');
      const gap = GAP_LABEL[ai.resolution?.expectation_gap];
      if (uc.cause_type) {
        natEl.textContent = `${CAUSE_LABEL[uc.cause_type] || uc.cause_type}${gap ? ' · ' + gap[0] : ''}`;
        natEl.className = `ai-uc-nat ${gap ? gap[1] : ''}`;
      } else {
        natEl.textContent = uc.nature === 'STRUCTURAL' ? '구조적 · 회복 지연' : '일시적 · 해소 가능';
        natEl.className = `ai-uc-nat uc-${(uc.nature || '').toLowerCase()}`;
      }
      document.getElementById('ai-detail-uc-text').textContent = uc.text;

      // 초기 진단이 증거로 뒤집혔으면 그게 이 종목의 핵심 서사다.
      const flipEl = document.getElementById('ai-detail-uc-flip');
      if (flipEl) {
        const flipped = !uc.cause_type && uc.nature_initial && uc.nature_initial !== uc.nature;
        flipEl.style.display = flipped ? '' : 'none';
        if (flipped) {
          flipEl.textContent = `초기 ${natLabel(uc.nature_initial)} → 검증 후 ${natLabel(uc.nature)}`;
        }
      }
      const basisEl = document.getElementById('ai-detail-uc-basis');
      if (basisEl) {
        const basis = [uc.implied_expectations, ai.resolution?.expectation_gap_basis].filter(Boolean).join('  /  ')
          || uc.nature_basis || '';
        basisEl.style.display = basis ? '' : 'none';
        basisEl.textContent = basis;
      }
    } else if (ucEl) {
      ucEl.style.display = 'none';
    }

    renderResolution(ai.resolution);

    const evCls = `ev-${(ai.evidence_strength || 'mod').toLowerCase()}`;
    const rkCls = `rk-${(ai.risk_level || 'low').toLowerCase()}`;
    document.getElementById('ai-detail-badges').innerHTML = `
      ${ai.resolution?.info_grade ? `<span class="ai-badge ev-moderate" title="증권사 리포트 수 기준 정보량 (A 6건 이상 · B 2~5 · C 0~1)">정보 ${ai.resolution.info_grade}</span>`
        : `<span class="ai-badge ${evCls}">근거 ${ai.evidence_strength || ''}</span>`}
      <span class="ai-badge ${rkCls}">리스크 ${ai.risk_level || ''}</span>
    `;

    const points = (ai.investment_points || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
    const risks = (ai.risks || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');
    document.getElementById('ai-detail-points').innerHTML = points;
    document.getElementById('ai-detail-risks').innerHTML = risks;

    const watchEl = document.getElementById('ai-detail-watch');
    const watch = ai.watch || [];
    if (watchEl && watch.length) {
      watchEl.style.display = '';
      document.getElementById('ai-detail-watch-list').innerHTML =
        watch.map(w => `<li>${escapeHtml(w)}</li>`).join('');
    } else if (watchEl) {
      watchEl.style.display = 'none';
    }

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

// ── 종목 브리핑 (briefer) — 처음 보는 사람이 2~3분에 이해하도록. 숫자 칸은 일별 데이터에서 직접 계산한다 ──
// 출처 태그는 본문에서 각주 번호로 — 문장 흐름을 끊지 않되, 같은 출처는 같은 번호로 끝에 모은다
let briefNotes = [];
function briefText(t) {
  return escapeHtml(t || '')
    .replace(/\s*\[확인 필요\]/g, ' <span class="brief-unk">확인 필요</span>')
    .replace(/\s*\[(출처:[^\]]+|정량)\]/g, (_, src) => {
      const label = src === '정량' ? '정량 — 일별 시총·DART 공시로 코드가 계산한 값' : src.replace(/^출처:\s*/, '');
      let n = briefNotes.indexOf(label) + 1;
      if (!n) n = briefNotes.push(label);
      return `<sup class="fn" title="${label}">${n}</sup>`;
    });
}

// 긴 문단은 두 문장씩 끊는다 — 에이전트가 쓴 4~5문장 덩어리가 벽처럼 읽힌다
function briefParas(t) {
  const sents = String(t || '').split(/(?<=[다요](?:\s*\[[^\]]+\])*\.(?:\s*\[[^\]]+\])*)\s+/);   // '…입니다 [출처]. 다음' 형태도
  // 마침표 뒤에 붙은 출처 태그('…습니다. [출처]')는 앞 문장 것 — 다음 조각 앞머리에서 떼어 앞으로 돌려보낸다
  for (let i = 1; i < sents.length; i++) {
    const m = sents[i].match(/^(\s*\[[^\]]+\])+/);
    if (m) { sents[i - 1] += m[0]; sents[i] = sents[i].slice(m[0].length).trim(); }
  }
  for (let i = sents.length - 1; i > 0; i--) if (!sents[i]) sents.splice(i, 1);
  const out = [];
  for (let i = 0; i < sents.length; i += 2) out.push(sents.slice(i, i + 2).join(' '));
  return out.map(x => `<p>${briefText(x)}</p>`).join('');
}

function renderBriefing(b, grade, bc, item) {
  bc = bc || {};
  const sec = document.getElementById('brief-section');
  const ai = document.getElementById('ai-section-detail');
  if (!b || !sec) return;
  sec.style.display = '';
  briefNotes = [];
  document.getElementById('brief-headline').textContent = b.headline || '';
  document.getElementById('brief-date').textContent = b.written_at ? `· ${b.written_at} 작성` : '';
  const warn = document.getElementById('brief-warn');
  const note = b.confidence_note || (grade === 'C' ? '자료가 적은 종목이라 이 해설의 신뢰도가 낮습니다. 출처를 직접 확인하세요.' : '');
  if (note) { warn.style.display = ''; warn.innerHTML = briefText(note); }

  const blk = (id, title, html, cls = '') => html ? `<section class="brief-blk ${cls}" id="bk-${id}"><h3>${title}</h3>${html}</section>` : '';
  const list = (arr, f) => (arr || []).map(f).join('');
  document.getElementById('brief-body').innerHTML = [
    blk('biz', '무슨 회사인가', b.business && briefParas(b.business)),
    blk('price', '주가는 어떻게 왔나', b.price_story && briefParas(b.price_story)),
    blk('bull', '매수 이유', list(bc.bull, (x, i) =>
      `<div class="brief-item bull"><h4><span class="num">${i + 1}</span>${escapeHtml(x.title || '')}</h4>${briefParas(x.body)}</div>`)),
    blk('why', '왜 싸졌나 — 반대 이유', list(b.why_cheap, (x, i) =>
      `<div class="brief-item"><h4><span class="num">${i + 1}</span>${escapeHtml(x.title || '')}</h4>${briefParas(x.body)}</div>`)),
    blk('mis', '시장이 틀렸을 수 있는 지점', bc.market_mispricing?.point ? `
      <div class="brief-mis dir-${(bc.market_mispricing.direction || 'NONE').toLowerCase()}">
        <span class="mis-dir">${{UNDER: '시장이 과소평가', OVER: '시장이 과대평가', NONE: '틀렸다고 볼 근거 없음'}[bc.market_mispricing.direction] || ''}</span>
        <p class="mis-point">${briefText(bc.market_mispricing.point)}</p>
        ${(bc.market_mispricing.evidence || []).map(e => `<p class="mis-ev">${briefText(e)}</p>`).join('')}
        ${bc.market_mispricing.if_right ? `<p class="mis-if"><b>맞다면</b> ${briefText(bc.market_mispricing.if_right)}</p>` : ''}
      </div>` : ''),
    blk('qa', '"그런데 ~ 아닌가요?"', list(b.qa, x =>
      `<div class="brief-qa"><p class="q">${escapeHtml(x.q || '')}</p><div class="a">${briefParas(x.a)}</div></div>`)),
    blk('priced', '지금 가격이 가정하는 것', b.priced_in && briefParas(b.priced_in)),
    blk('trap', '함정 점검 — 숫자로 안 잡히는 것', bc.trap?.level ? `
      <div class="brief-trap lv-${bc.trap.level.toLowerCase()}">
        <span class="trap-lv">${{SEVERE: '함정 확인 — 순위 크게 감점', WATCH: '주의 — 소폭 감점', NONE: '해당 없음'}[bc.trap.level]}</span>
        ${(bc.trap.flags || []).map(f => `<span class="trap-flag">${{ONE_OFF_EARNINGS: '일회성 이익', ACCOUNTING: '회계', STRUCTURAL_BREAK: '구조 변화', GOVERNANCE: '지배구조', BALANCE_SHEET: '재무 체력'}[f] || f}</span>`).join('')}
        ${briefParas(bc.trap.reason)}
      </div>` : ''),
    blk('watch', '다음에 볼 것', b.watch?.length ? `<div class="brief-watch">${list(b.watch, w => `
      <div class="w-row">
        <div class="w-head"><b>${briefText(w.what)}</b><span>${escapeHtml(w.when || '')}</span></div>
        <div class="w-sig good"><em>좋은 신호</em>${briefText(w.good)}</div>
        <div class="w-sig bad"><em>나쁜 신호</em>${briefText(w.bad)}</div>
      </div>`)}</div>` : ''),
    bc.sharp_question ? `<section class="brief-blk brief-sharp" id="bk-sharp"><h3>이 투자 논리를 흔드는 질문</h3><p>${briefText(bc.sharp_question)}</p></section>` : '',
  ].join('');

  // 옆 칸: 30초 요약 — 왜 싸졌나 제목 + 시장이 맞다면 (반론을 결론만큼 크게)
  document.getElementById('brief-aside').innerHTML = `
    ${item?.ai_rank ? `<div class="aside-box rank"><p class="aside-lbl">매수 매력 ${item.ai_rank}위 / 30</p>${rankDetail(item)}</div>` : ''}
    ${bc.bull?.length ? `<div class="aside-box"><p class="aside-lbl">매수 이유 — 요약</p><ol>${list(bc.bull, x => `<li><a href="#bk-bull">${escapeHtml(x.title || '')}</a></li>`)}</ol></div>` : ''}
    ${b.why_cheap?.length ? `<div class="aside-box"><p class="aside-lbl">반대 이유 — 요약</p><ol>${list(b.why_cheap, x => `<li><a href="#bk-why">${escapeHtml(x.title || '')}</a></li>`)}</ol></div>` : ''}
    ${b.if_market_right ? `<div class="aside-box bear"><p class="aside-lbl">시장이 맞다면</p>${briefParas(b.if_market_right)}</div>` : ''}`;

  const src = document.getElementById('brief-sources');
  src.innerHTML = briefNotes.length ? `<summary>출처 ${briefNotes.length}개</summary><ol>${briefNotes.map(n => `<li>${n}</li>`).join('')}</ol>` : '';

  // 기존 분석 원문은 접어 둔다 — 같은 이야기를 두 번 읽지 않게
  const btn = document.getElementById('brief-more');
  ai.classList.add('ai-collapsed');
  btn.onclick = () => {
    const open = !ai.classList.toggle('ai-collapsed');
    btn.setAttribute('aria-expanded', open);
    btn.textContent = open ? '근거 접기' : '근거 자세히 보기 — AI 분석 원문 · 출처 전체';
    if (open) ai.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
}

function renderBriefPrice() {
  const el = document.getElementById('brief-price');
  if (!el || !dataset || dataset._source !== 'daily') return;
  // 시총 비례 수정주가 — 원주가는 분할·무상증자 때 계단이 생겨 '고점 대비'가 부풀려진다
  const raw = dataset.dates.map((d, i) => [d, dataset.close[i], dataset.market_cap[i]]).filter(x => x[1] && x[2]);
  if (!raw.length) return;
  const [lastD, last, lastM] = raw[raw.length - 1];
  const pts = raw.map(([d, , m]) => [d, m * last / lastM]);
  const stat = (years) => {
    const cut = new Date(lastD); cut.setFullYear(cut.getFullYear() - years);
    const w = pts.filter(x => new Date(x[0]) >= cut);
    const hi = w.reduce((a, b) => (b[1] > a[1] ? b : a));
    return { hi, from: last / hi[1] - 1, chg: last / w[0][1] - 1 };
  };
  const pct = (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`;
  const won = (v) => `${Math.round(v).toLocaleString('ko-KR')}원`;
  const y1 = stat(1), y3 = stat(3);
  const per = lastNonNull(dataset.per)?.val, pbr = lastNonNull(dataset.pbr)?.val;
  el.innerHTML = [
    ['현재가', won(last), lastD],
    ['1년 고점 대비', pct(y1.from), `수정 고점 ${won(y1.hi[1])} · ${y1.hi[0]}`],
    ['1년 수익률', pct(y1.chg), '1년 전 종가 대비'],
    ['3년 고점 대비', pct(y3.from), `수정 고점 ${won(y3.hi[1])} · ${y3.hi[0]}`],
    ['PER · PBR', `${per != null ? per.toFixed(1) : '—'} · ${pbr != null ? pbr.toFixed(2) : '—'}`, 'TTM 지배주주 기준'],
  ].map(([k, v, s]) => `<div class="bp"><span class="bp-k">${k}</span><b class="bp-v${String(v).startsWith('-') ? ' neg' : ''}">${v}</b><span class="bp-s">${s}</span></div>`).join('');
}

// 순위 계산식을 그대로 보여준다 — (주주이익 수익률 + 재평가 수익) × 확실성, 좋은 사업 6관문
const RANK_CHECKS = ['ROE 평균 ≥8%', '현금흐름/순이익 ≥0.7', '이자보상 ≥2배', '순이익률 평균 ≥5%', 'FCF 적자 연도 ≤2 (5년)', '주식 수 증가 ≤20%'];
const PREM_TXT = { INTACT: '과거 프리미엄의 이유 유효 → 과거 배수로', WEAKENED: '이유 약해짐 → 과거와 시장의 중간(기하평균)', NO_HISTORY: '비교할 과거 이력 없음 → 시장 평균 배수', GONE: '이유 사라짐 → 시장 평균 배수로' };
function rankDetail(item) {
  const d = item.rank_detail;
  if (!d || d.er == null) return `<p>${briefText(item.rerank_reason || '')}</p>`;
  const pct = (v, s = false) => v == null ? '—' : `${s && v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;
  const fmt = [(v) => pct(v), (v) => v.toFixed(2), (v) => v >= 99 ? '이자 부담 없음' : `${v.toFixed(1)}배`, (v) => pct(v),
               (v) => `${v}개 해`, (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`];
  const rows = RANK_CHECKS.map((name, i) => {
    const ok = d.checks?.[i], v = d.check_vals?.[i];
    return `<li class="${ok === false ? 'no' : ok ? 'ok' : 'na'}"><span>${ok === false ? '✕' : ok ? '✓' : '–'}</span>${name}<em>${v == null ? '자료 없음' : fmt[i](v)}</em></li>`;
  }).join('');
  return `<p class="rank-formula">기대 수익 <b>연 ${pct(d.er, true)}</b> = 주주이익 수익률 <b>${pct(d.owner_yield)}</b> + 재평가 <b>${pct(d.rerate, true)}</b><br>× 확실성 <b>${d.certainty}</b></p>
    ${d.target_per ? `<p class="aside-sub">재평가</p><p class="rank-line">${PREM_TXT[d.premium] || ''}<br>목표 PER <b>${d.target_per}</b> · 지금 ${d.cur_per_reval ?? '—'} (정상화 이익 기준)</p>` : ''}
    <p class="aside-sub">이익률</p><p class="rank-line">${(d.margin_used * 100).toFixed(1)}% — ${escapeHtml(d.margin_note || '')}</p>
    <p class="aside-sub">좋은 사업 점검 ${d.good_business}${d.payout != null ? ` · 배당성향 ${(d.payout * 100).toFixed(0)}%` : ''}</p><ul class="rank-checks">${rows}</ul>`;
}

function natLabel(n) {
  return String(n || '').toUpperCase() === 'STRUCTURAL' ? '구조적' : '일시적';
}

const RES_VERDICT = {
  RESOLVING: ['해소 진행 중', 'res-resolving'],
  EARLY_SIGNS: ['초기 신호', 'res-early'],
  NO_EVIDENCE: ['근거 없음', 'res-none'],
  WORSENING: ['원인 심화 중', 'res-worse'],
};

// resolution-scout 산출 — "이 저평가가 풀릴까"에 대한 양방향 증거.
// evidence가 비어 있는 것은 결측이 아니라 결론이므로 그대로 보여준다.
function renderResolution(res) {
  const el = document.getElementById('ai-detail-res');
  if (!el) return;
  if (!res || !res.verdict) { el.style.display = 'none'; return; }
  el.style.display = '';

  const [txt, cls] = RES_VERDICT[String(res.verdict).toUpperCase()] || ['판정 없음', 'res-none'];
  const vEl = document.getElementById('ai-detail-res-verdict');
  vEl.textContent = txt;
  vEl.className = `ai-res-verdict ${cls}`;

  const wEl = document.getElementById('ai-detail-res-window');
  const showWindow = res.expected_window && res.expected_window !== '불명'
    && ['RESOLVING', 'EARLY_SIGNS'].includes(String(res.verdict).toUpperCase());
  wEl.style.display = showWindow ? '' : 'none';
  wEl.textContent = showWindow ? `${res.expected_window} 내 확인` : '';

  document.getElementById('ai-detail-res-summary').textContent = res.summary || '';

  const evUl = document.getElementById('ai-detail-res-ev');
  const ev = res.evidence || [];
  evUl.innerHTML = ev.length
    ? ev.map(e => `<li>${escapeHtml(e.text || '')}`
        + (e.verifiable_by ? `<span class="ai-res-when">${escapeHtml(e.verifiable_by)} 확인</span>` : '')
        + '</li>').join('')
    : '<li class="ai-res-empty">원인을 직접 겨냥하는 해소 근거를 찾지 못했습니다.</li>';

  const cUl = document.getElementById('ai-detail-res-counter');
  const ce = res.counter_evidence || [];
  cUl.innerHTML = ce.length
    ? ce.map(c => `<li>${escapeHtml(c.text || '')}</li>`).join('')
    : '<li class="ai-res-empty">확인된 심화 요인 없음</li>';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function renderFinChart(code) {
  const wrap = document.getElementById('fin-section');
  if (!wrap) return;
  try {
    const r = await fetch(`data/financials/${code}.json?t=${Date.now()}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const fin = await r.json();
    const annual = (fin.annual || []).filter(a => a.revenue != null || a.op_margin != null);
    if (annual.length < 2) { wrap.style.display = 'none'; return; }
    wrap.style.display = '';

    const css = getComputedStyle(document.documentElement);
    const accent = (css.getPropertyValue('--accent') || '#2b6cb0').trim();
    const muted = (css.getPropertyValue('--text-muted') || '#888').trim();
    const up = (css.getPropertyValue('--kr-up') || '#e31b1b').trim();

    const years = annual.map(a => String(a.year));
    const revenue = annual.map(a => a.revenue != null ? a.revenue / 1e8 : null);  // 억원
    const opm = annual.map(a => a.op_margin != null ? +(a.op_margin * 100).toFixed(1) : null);

    const traces = [
      {
        type: 'bar', name: '매출 (억원)', x: years, y: revenue,
        marker: { color: accent, opacity: 0.55 },
        hovertemplate: '%{x}<br>매출 %{y:,.0f}억<extra></extra>',
      },
      {
        type: 'scatter', mode: 'lines+markers', name: '영업이익률 (%)',
        x: years, y: opm, yaxis: 'y2',
        line: { color: up, width: 2.5 }, marker: { size: 6 },
        connectgaps: true,
        hovertemplate: '%{x}<br>OPM %{y:.1f}%<extra></extra>',
      },
    ];
    const layout = {
      height: 250,
      margin: { l: 56, r: 52, t: 10, b: 30 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'Pretendard, sans-serif', size: 11, color: muted },
      barmode: 'group', showlegend: true,
      legend: { orientation: 'h', y: 1.18, x: 0, font: { size: 11 } },
      xaxis: { showgrid: false },
      yaxis: { title: '', zeroline: false, gridcolor: 'rgba(128,128,128,0.12)' },
      yaxis2: {
        overlaying: 'y', side: 'right', ticksuffix: '%',
        zeroline: true, zerolinecolor: 'rgba(128,128,128,0.35)', showgrid: false,
      },
    };
    Plotly.react('fin-chart', traces, layout, { displayModeBar: false, responsive: true });
  } catch (e) {
    console.warn('[financials] 로드 실패:', e.message);
    wrap.style.display = 'none';
  }
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
              universe?.excluded?.no_data || [], universe?.excluded?.validation_adverse || [],
              universe?.excluded?.validation_short || [], universe?.excluded?.validation_nodata || [],
              universe?.excluded?.no_fy1_eps || [])
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
  const fwdYearShort = String(fwd.year_estimate || '').includes('E') ? fwd.year_estimate : ((fwd.year_estimate || '').split('/')[0] + 'E');

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
      ? `<span>Fwd ${fwdYearShort}</span><span style="color:#dc2626;font-weight:600">${fmt(fwdMap[m])}</span>`
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
        <div class="stat-label">증권사 목표가 (${cs.broker_count || brokers.length}곳 · 점수 미반영)</div>
        <div class="stat-val">${fmt(tgt)}원</div>
        <div class="stat-grid">
          <span>현재가 대비</span><span class="${upsideCls}">${upsideStr}</span>
          ${cs.avg_per_forward != null ? `<span>Fwd PER</span><span>${fmt(cs.avg_per_forward)}</span>` : ''}
          ${cs.avg_eps_forward != null ? `<span>Fwd EPS</span><span>${fmt(cs.avg_eps_forward)}</span>` : ''}
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
