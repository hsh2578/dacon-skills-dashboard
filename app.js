const KEYS = ['kospi', 'kosdaq', 'sp500'];
const COLORS = {
  kospi:     '#2563eb',
  kosdaq:    '#059669',
  sp500:     '#dc2626',
};
const METRICS = [
  { key: 'per',       chartId: 'chart-per',   label: 'PER' },
  { key: 'pbr',       chartId: 'chart-pbr',   label: 'PBR' },
  { key: 'div_yield', chartId: 'chart-div',   label: '배당수익률' },
  { key: 'close',     chartId: 'chart-close', label: '종가' },
];

const datasets = {};
let currentMode = 'compare';

// ============================================================
// AI 분석 카드 영역 (서브에이전트 결과 — 점수 영향 X)
// ============================================================
function natLabel(n) {
  return String(n || '').toUpperCase() === 'STRUCTURAL' ? '구조적' : '일시적';
}

// v6 (2026-11-24): "일시적/구조적" 이분법 대신 원인 분류 + 기대 괴리(가격 가정 vs 증거)
const CAUSE_LABEL = {
  CYCLICAL_PEAK: '경기 정점', STRUCTURAL_DECLINE: '구조적 쇠퇴', TEMPORARY_SHOCK: '일시 충격',
  ONE_OFF_ACCOUNTING: '일회성 회계', GOVERNANCE_DISCOUNT: '지배구조 할인', NEGLECT: '소외',
  REGULATORY_MACRO: '규제·거시', BALANCE_SHEET_TRAP: '재무 함정',
};
const GAP = {
  TOO_PESSIMISTIC:        { txt: '가격이 과도하게 비관적', short: '과도 비관', cls: 'nat-temporary',  uc: 'uc-temporary' },
  FAIR:                   { txt: '가격이 전망 반영',       short: '전망 반영', cls: 'nat-unknown',    uc: '' },
  NOT_PESSIMISTIC_ENOUGH: { txt: '함정 경계',              short: '함정 경계', cls: 'nat-structural', uc: 'uc-structural' },
};
const gapOf = (ai) => GAP[ai?.resolution?.expectation_gap] || null;

function renderAiBlock(code, ai) {
  const evCls = `ev-${(ai.evidence_strength || 'mod').toLowerCase()}`;
  const rkCls = `rk-${(ai.risk_level || 'low').toLowerCase()}`;
  // 카드는 압축형: 투자 포인트 3개, 리스크 2개만. 전체는 상세페이지에서.
  const fullPoints = ai.investment_points || [];
  const fullRisks = ai.risks || [];
  const cardPoints = fullPoints.slice(0, 3);
  const cardRisks = fullRisks.slice(0, 2);
  const moreP = fullPoints.length - cardPoints.length;
  const moreR = fullRisks.length - cardRisks.length;
  const points = cardPoints.map(p => `<li>${p}</li>`).join('');
  const risks = cardRisks.map(r => `<li>${r}</li>`).join('');
  const moreNote = (moreP > 0 || moreR > 0)
    ? `<div class="ai-more-note">+${moreP + moreR}개 항목은 상세페이지에서 확인</div>` : '';

  const uc = ai.undervaluation_cause;
  // 초기 진단이 증거로 뒤집혔으면 그 자체가 핵심 서사다 — 숨기지 않고 드러낸다.
  const flipped = uc && uc.nature_initial && uc.nature_initial !== uc.nature;
  const flipTxt = flipped
    ? `<span class="ai-uc-flip">초기 ${natLabel(uc.nature_initial)} → 검증 후 ${natLabel(uc.nature)}</span>` : '';
  const ucBlock = (uc && uc.text) ? `
        <div class="ai-uc">
          <div class="ai-uc-head">
            <span class="ai-uc-lbl">왜 저평가인가</span>
            ${uc.cause_type ? `<span class="ai-uc-nat ${gapOf(ai)?.uc || ''}">${CAUSE_LABEL[uc.cause_type] || uc.cause_type}</span>`
              : `<span class="ai-uc-nat uc-${(uc.nature || '').toLowerCase()}">${uc.nature === 'STRUCTURAL' ? '구조적 · 회복 지연' : '일시적 · 해소 가능'}</span>`}
            ${uc.cause_type ? '' : flipTxt}
          </div>
          <div class="ai-uc-text">${uc.text}</div>
          ${uc.implied_expectations ? `<div class="ai-uc-basis">${uc.implied_expectations}</div>` : ''}
          ${ai.resolution?.expectation_gap_basis ? `<div class="ai-uc-basis"><b>${gapOf(ai)?.txt || ''}</b> — ${ai.resolution.expectation_gap_basis}</div>`
            : (uc.nature_basis ? `<div class="ai-uc-basis">${uc.nature_basis}</div>` : '')}
        </div>` : '';

  return `
    <div class="ai-block">
      <button class="ai-toggle" type="button" data-code="${code}" aria-expanded="false">
        <span class="ai-toggle-lbl">AI 분석 보기</span>
        <span class="ai-toggle-chev">▾</span>
      </button>
      <div class="ai-panel" id="ai-panel-${code}" hidden>
        <div class="ai-oneliner">${ai.one_liner || ''}</div>
${ucBlock}
        <div class="ai-section">
          <div class="ai-section-lbl">투자 포인트</div>
          <ul class="ai-points">${points}</ul>
        </div>

        ${risks ? `
        <div class="ai-section">
          <div class="ai-section-lbl">리스크</div>
          <ul class="ai-risks">${risks}</ul>
        </div>` : ''}

        ${moreNote}

        <div class="ai-verdict-row">
          <div class="ai-verdict">${ai.verdict || ''}</div>
          <div class="ai-badges">
            ${(ai.resolution?.info_grade || ai.info_grade) ? `<span class="ai-badge ev-moderate" title="증권사 리포트 수 기준 정보량 (A 6건 이상 · B 2~5 · C 0~1)">정보 ${ai.resolution?.info_grade || ai.info_grade}</span>` : `<span class="ai-badge ${evCls}">근거 ${ai.evidence_strength || ''}</span>`}
            <span class="ai-badge ${rkCls}">리스크 ${ai.risk_level || ''}</span>
          </div>
        </div>

        <div class="ai-meta">
          ${ai.model || ''} · ${ai.generated_at ? new Date(ai.generated_at).toLocaleDateString('ko-KR') : ''}
        </div>
      </div>
    </div>`;
}

function bindAiToggles() {
  document.querySelectorAll('.ai-toggle').forEach(btn => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const code = btn.getAttribute('data-code');
      const panel = document.getElementById(`ai-panel-${code}`);
      if (!panel) return;
      const open = !panel.hasAttribute('hidden');
      if (open) {
        panel.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', 'false');
        btn.querySelector('.ai-toggle-lbl').textContent = 'AI 분석 보기';
        btn.querySelector('.ai-toggle-chev').textContent = '▾';
      } else {
        panel.removeAttribute('hidden');
        btn.setAttribute('aria-expanded', 'true');
        btn.querySelector('.ai-toggle-lbl').textContent = 'AI 분석 닫기';
        btn.querySelector('.ai-toggle-chev').textContent = '▴';
      }
    });
  });
}

// 카드 순서: 'ai' = ranker 재순위(저평가 해소 가능성) · 'quant' = 팩터 점수 순위 (2026-11-24 전환 버튼)
let screenOrder = 'ai';
let screenTopN = 0;   // Section 2 카드 수 — 검색 목록은 그 다음 순위부터

function bindOrderToggle() {
  document.querySelectorAll('.order-btn').forEach(btn => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', () => {
      screenOrder = btn.dataset.order;
      document.querySelectorAll('.order-btn').forEach(b => b.classList.toggle('is-active', b === btn));
      loadTripleCross();
    });
  });
}

async function loadTripleCross() {
  const cardsEl = document.getElementById('screen-cards');
  const metaEl = document.getElementById('screen-meta');
  const emptyEl = document.getElementById('screen-empty');
  if (!cardsEl) return;

  try {
    const [r, aiR] = await Promise.all([
      fetch(`data/screens/triple_cross.json?t=${Date.now()}`),
      fetch(`data/screens/ai_notes.json?t=${Date.now()}`),
    ]);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const payload = await r.json();
    const top = payload.top || [];
    const meta = payload.meta || {};

    // AI 분석 노트 (서브에이전트 결과) — code → ai_notes / 재순위 매핑
    const aiMap = {};
    const aiRankMap = {};
    if (aiR.ok) {
      const aiDoc = await aiR.json();
      for (const item of (aiDoc.items || [])) {
        aiMap[item.code] = item.ai_notes;
        aiRankMap[item.code] = {
          ai_rank: item.ai_rank,
          quant_rank: item.quant_rank,
          rerank_reason: item.rerank_reason,
        };
      }
    }

    // ranker가 부여한 ai_rank가 있으면 그 순서로 카드 재정렬 (저평가 해소 가능성 순)
    const hasAiRank = top.some(c => aiRankMap[c.code]?.ai_rank);
    screenTopN = top.length;
    bindOrderToggle();
    if (screenOrder === 'quant') {
      top.sort((a, b) => a.rank - b.rank);
    } else if (hasAiRank) {
      top.sort((a, b) =>
        (aiRankMap[a.code]?.ai_rank ?? 99) - (aiRankMap[b.code]?.ai_rank ?? 99));
    }

    const qFail = (payload.all_ranked || []).filter(r => r.quality_pass === false).length;
    const cyc = top.filter(r => r.cyclical_flag).length;
    metaEl.textContent =
      `유니버스 ${meta.universe_size ?? '-'} · 퀄리티 탈락 ${qFail} · Top ${top.length} 중 이익 정점 의심 ${cyc}` +
      (meta.updated_at ? ` · ${new Date(meta.updated_at).toLocaleString('ko-KR')}` : '');

    if (!top.length) {
      cardsEl.innerHTML = '';
      emptyEl.style.display = '';
      return;
    }
    emptyEl.style.display = 'none';

    const fmtPrice = (v) => v == null ? '—' : v.toLocaleString('ko-KR') + '원';
    const fmtPer = (v) => v == null ? '—' : v.toFixed(2);
    const tierLabel = {
      HIDDEN_GEM: 'Hidden Gem', STRONG_BUY: 'Strong Buy', BUY: 'Buy',
      WATCH: 'Watch', WEAK: 'Weak', MISS: 'Miss',
    };

    const fmtPct = (v) => v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
    const fmtZ = (v) => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2);

    cardsEl.innerHTML = top.map((c, i) => {
      const tierClass = `tier-${(c.tier || 'BUY').toLowerCase()}`;
      const tierTxt = tierLabel[c.tier] || c.tier;

      // 4팩터 시그널 배지 (z > 0 = universe 평균보다 좋음)
      const factor = (label, z) => {
        const on = z != null && z > 0;
        return `<div class="factor ${on ? 'on' : ''}" title="z=${fmtZ(z)}">${label}</div>`;
      };

      // 그룹 점수 막대 (-2 ~ +2 → 0~100% mapping)
      const groupBar = (score) => {
        if (score == null) return '<div class="gbar empty"></div>';
        const pct = Math.max(0, Math.min(100, (score + 2) * 25));  // -2→0%, 0→50%, +2→100%
        const cls = score >= 0 ? 'pos' : 'neg';
        return `<div class="gbar"><div class="gfill ${cls}" style="width:${pct}%"></div></div>`;
      };

      // AI 분석 영역 (서브에이전트 결과 — 점수 영향 X, 부가 정보)
      const ai = aiMap[c.code];
      const aiBlock = ai ? renderAiBlock(c.code, ai) : '';

      // ── 카드 헤드 ──────────────────────────────────────────────
      // 옛 구조는 티어 배지(전 종목 STRONG_BUY = 정보량 0)가 가장 강한 시각 요소였고,
      // 정작 이 시스템의 결론인 "왜 싼가 / 회복하는가"는 AI 블록 안에 접혀 있었다.
      // 결론을 카드 표면으로 끌어올리고 티어 배지는 걷어낸다.
      const rk = aiRankMap[c.code] || {};
      // 카드 색 = 기대 괴리 (초록: 가격이 증거보다 비관적 · 회색: 전망 반영 · 빨강: 함정 경계)
      const gap = gapOf(ai);
      const natCls = gap ? gap.cls : 'nat-unknown';
      const cause = ai?.undervaluation_cause?.cause_type;
      const natTxt = gap ? `${CAUSE_LABEL[cause] || '원인 미분류'} · ${gap.short}` : '판정 없음';

      // 정량 후보 순위 → AI 재순위 이동. 이 대비가 2단계 랭킹 구조의 핵심 서사다.
      const move = (rk.quant_rank != null && rk.ai_rank != null)
        ? rk.quant_rank - rk.ai_rank : null;
      const moveCls = move == null ? '' : move > 0 ? 'mv-up' : move < 0 ? 'mv-down' : 'mv-flat';
      const moveTxt = move == null ? ''
        : screenOrder === 'quant' ? `AI ${rk.ai_rank}위`
        : move === 0 ? '정량과 동일'
        : `정량 ${rk.quant_rank}위 ${move > 0 ? '▲' : '▼'} ${Math.abs(move)}`;

      const ucText = ai?.undervaluation_cause?.text || '';
      const rankTier = i < 3 ? 'rk-top' : i < 10 ? 'rk-mid' : 'rk-low';

      return `
        <a class="screen-card ${tierClass} ${natCls} ${rankTier}" href="stock.html?code=${c.code}">
          <div class="card-rank-row">
            <span class="card-rank">#${i + 1}</span>
            ${move != null ? `<span class="card-move ${moveCls}">${moveTxt}</span>` : ''}
            <span class="card-nat">${natTxt}</span>
          </div>
          ${c.cyclical_flag ? `<div class="card-cyc" title="최근 20분기 영업이익률이 크게 출렁였거나 지금이 평소의 2배 이상 — 낮은 PER이 이익 정점 때문일 수 있음">이익 정점 의심</div>` : ''}
          <div class="card-name">${c.name}</div>
          <div class="card-code">${c.code} · ${c.market || 'KR'}</div>
          <div class="card-price">${fmtPrice(c.current_price)}</div>

          ${ucText ? `<div class="card-uc"><span class="card-uc-lbl">왜 저평가인가</span><p>${ucText}</p></div>` : ''}

          <div class="card-factor-grid">
            ${factor('PER↓', c.s1_per_z)}
            ${factor('PBR↓', c.s1_pbr_z)}
            ${factor('전망↓', c.s3_per_z)}
            <div class="factor ${c.quality_pass ? 'on' : ''}" title="퀄리티 필터 (이익률 추세·이익의 질·이자보상) — 하위 20%면 Top 자격 없음">퀄리티</div>
          </div>

          <div class="card-per-row">
            <div><div class="lbl">PER</div><div class="val">${fmtPer(c.current_per)}</div></div>
            <div><div class="lbl">5Y 중앙</div><div class="val muted">${fmtPer(c.avg_5y_per)}</div></div>
            <div><div class="lbl">PBR</div><div class="val">${fmtPer(c.cur_pbr)}</div></div>
            <div><div class="lbl">5Y 중앙</div><div class="val muted">${fmtPer(c.avg_5y_pbr)}</div></div>
          </div>

          <div class="card-fwd-row">
            <div><div class="lbl">Fwd PER</div><div class="val fwd">${fmtPer(c.forward_per)}</div></div>
            <div title="평소(5년 중앙) PER을 받으려면 필요한 이익 ÷ 컨센서스 이익. 0.2면 시장은 이익이 컨센서스의 1/5로 준다고 가격을 매김"><div class="lbl">가격 가정 이익</div><div class="val">${c.implied_fade == null ? '—' : '×' + c.implied_fade.toFixed(2)}</div></div>
            <div><div class="lbl">컨센 목표가</div><div class="val muted">${fmtPrice(c.avg_target)}</div></div>
          </div>

          <div class="card-group-row">
            <div class="g-row">
              <span class="g-lbl">가치</span>
              ${groupBar(c.value_score)}
              <span class="g-val">${fmtZ(c.value_score)}</span>
            </div>
            <div class="g-row">
              <span class="g-lbl">전망</span>
              ${groupBar(c.growth_score)}
              <span class="g-val">${fmtZ(c.growth_score)}</span>
            </div>
          </div>

          <div class="card-score">
            <span class="lbl">정량 종합 (PER·PBR·전망 각 ⅓)</span>
            <span class="val">${fmtZ(c.total_score)}</span>
          </div>

          ${aiBlock}
        </a>`;
    }).join('');

    bindAiToggles();
  } catch (e) {
    console.warn('[triple_cross] 로드 실패:', e.message);
    metaEl.textContent = '데이터 미생성 (apply_triple_cross.py 실행 필요)';
    emptyEl.style.display = '';
  }
}

// ============================================================
// 종목 검색 (Section 3)
// ============================================================
let searchPool = [];   // 검색 가능한 모든 종목 (universe + 추가 페치된 종목)
let searchPage = 1;
const SEARCH_PAGE_SIZE = 30;
let scoreMap = {};     // code → triple_cross 점수 정보

async function loadSearchPool() {
  const resultsEl = document.getElementById('search-results');
  const countEl = document.getElementById('search-count');
  if (!resultsEl) return;

  try {
    // 검색 대상 = 시총 2,000억+ 보통주 전체 (apply_triple_cross 가 만든 search_index.json).
    // universe 밖 종목도 현재 PER·5년 중앙값·일별 차트·재무를 볼 수 있다 — 점수·AI 만 universe 안.
    const [idxR, screenR] = await Promise.all([
      fetch(`data/screens/search_index.json?t=${Date.now()}`),
      fetch(`data/screens/triple_cross.json?t=${Date.now()}`),
    ]);
    const idx = idxR.ok ? await idxR.json() : { items: [] };
    const screen = screenR.ok ? await screenR.json() : null;
    if (screen?.all_ranked) {
      for (const r of screen.all_ranked) scoreMap[r.code] = r;
    }
    searchPool = (idx.items || []).map(s => ({
      code: s.code, name: s.name, market: s.market,
      market_cap: s.market_cap_억, close: s.close,
      cur_per: s.cur_per, med_per: s.med_per, cur_pbr: s.cur_pbr, med_pbr: s.med_pbr,
      forward_per: s.forward_per, avg_target: s.avg_target,
      total_score: s.total_score, rank: s.rank,
      tier: scoreMap[s.code]?.tier, upside_raw: scoreMap[s.code]?.upside_raw,
      analyzed: !!s.in_universe,
    }));

    countEl.textContent = `${searchPool.length} 종목`;
    bindSearchControls();
    renderSearchResults('');
  } catch (e) {
    console.warn('[search] 로드 실패:', e.message);
    countEl.textContent = '로드 실패';
  }
}

function bindSearchControls() {
  const inputEl = document.getElementById('search-input');
  const sortEl = document.getElementById('search-sort');
  if (!inputEl || inputEl._bound) return;
  inputEl._bound = true;
  inputEl.addEventListener('input', (e) => { searchPage = 1; renderSearchResults(e.target.value); });
  sortEl.addEventListener('change', () => { searchPage = 1; renderSearchResults(inputEl.value); });
}

function renderSearchResults(query) {
  const resultsEl = document.getElementById('search-results');
  const emptyEl = document.getElementById('search-empty');
  const sortEl = document.getElementById('search-sort');
  const countEl = document.getElementById('search-count');
  if (!resultsEl) return;

  const q = (query || '').trim().toLowerCase();
  let filtered = searchPool;
  if (q) {
    filtered = searchPool.filter(s =>
      (s.name || '').toLowerCase().includes(q) ||
      (s.code || '').toLowerCase().includes(q)
    );
  }

  // 정렬
  const sortKey = sortEl.value;
  // 검색어 없이 순위순이면 Top N(위 카드)은 빼고 그 다음 순위부터 — 같은 종목을 두 번 보여주지 않는다
  if (!q && sortKey === 'rank' && screenTopN) {
    filtered = filtered.filter(s => !(s.rank && s.rank <= screenTopN));
  }
  const sorters = {
    // 순위 번호 기준 — 퀄리티 탈락 종목은 점수가 높아도 뒤로 밀리므로 total_score 로 정렬하면 순서가 어긋난다
    rank:       (a, b) => (a.rank ?? 9e9) - (b.rank ?? 9e9),
    market_cap: (a, b) => (b.market_cap || 0) - (a.market_cap || 0),
    cur_per:    (a, b) => (a.cur_per ?? 9e9) - (b.cur_per ?? 9e9),
    upside:     (a, b) => (b.upside_raw ?? -9e9) - (a.upside_raw ?? -9e9),
    name:       (a, b) => (a.name || '').localeCompare(b.name || ''),
  };
  filtered.sort(sorters[sortKey] || sorters.rank);

  countEl.textContent = q
    ? `${filtered.length} / ${searchPool.length} 종목`
    : `${searchPool.length} 종목`;

  // 페이지네이션
  const totalPages = Math.max(1, Math.ceil(filtered.length / SEARCH_PAGE_SIZE));
  if (searchPage > totalPages) searchPage = totalPages;
  if (searchPage < 1) searchPage = 1;
  const start = (searchPage - 1) * SEARCH_PAGE_SIZE;
  const view = filtered.slice(start, start + SEARCH_PAGE_SIZE);

  if (filtered.length === 0) {
    resultsEl.innerHTML = '';
    emptyEl.style.display = '';
    return;
  }
  emptyEl.style.display = 'none';

  const fmtP = (v) => v == null ? '—' : v >= 1000 ? v.toLocaleString('en') : v.toFixed(2);
  const fmtZ = (v) => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2);
  const tierMap = { HIDDEN_GEM: 'gold', STRONG_BUY: 'green', BUY: 'blue',
                    WATCH: 'indigo', WEAK: 'gray', MISS: 'gray' };
  const tierLbl = { HIDDEN_GEM: 'Hidden Gem', STRONG_BUY: 'Strong Buy', BUY: 'Buy',
                    WATCH: 'Watch', WEAK: 'Weak', MISS: 'Miss' };

  resultsEl.innerHTML = view.map(s => {
    // tier는 전 종목 STRONG_BUY로 통일 운영이라 배지가 정보를 담지 못한다
    // (#N 순위와 Z 점수가 이미 위치를 말해준다). 예외 상태일 때만 노출한다.
    const tierBadge = (s.tier && s.tier !== 'STRONG_BUY')
      ? `<span class="srch-tier-badge tier-${s.tier.toLowerCase()}">${tierLbl[s.tier] || s.tier}</span>`
      : '';
    const rankBadge = s.rank ? `#${s.rank}` : '';
    const upPct = s.upside_raw == null ? '' :
      `<span class="srch-up" title="증권사 평균 목표가 대비 — 점수 미반영">목표가 괴리 <b>${(s.upside_raw >= 0 ? '+' : '') + (s.upside_raw * 100).toFixed(1)}%</b></span>`;
    return `
      <a class="srch-card" href="stock.html?code=${s.code}">
        <div class="srch-row1">
          <span class="srch-rank">${rankBadge}</span>
          <span class="srch-name">${s.name}</span>
          ${tierBadge}
        </div>
        <div class="srch-row2">
          <span class="srch-code">${s.code} · ${s.market}</span>
          <span class="srch-price">${fmtP(s.close)}원</span>
        </div>
        <div class="srch-row3">
          <span title="현재 / 5년 중앙">PER <b>${fmtP(s.cur_per)}</b> <small>/ ${fmtP(s.med_per)}</small></span>
          <span title="현재 / 5년 중앙">PBR <b>${fmtP(s.cur_pbr)}</b> <small>/ ${fmtP(s.med_pbr)}</small></span>
          ${s.analyzed ? `<span>Fwd <b class="fwd">${fmtP(s.forward_per)}</b></span>` : ''}
          <span class="srch-score">${s.analyzed ? 'Z ' + fmtZ(s.total_score) : 'universe 밖'}</span>
        </div>
      </a>`;
  }).join('');
  // 페이지네이션 컨트롤
  if (totalPages > 1) {
    const fromIdx = start + 1;
    const toIdx = Math.min(start + SEARCH_PAGE_SIZE, filtered.length);
    const pages = buildPageButtons(searchPage, totalPages);
    resultsEl.insertAdjacentHTML('beforeend', `
      <nav class="srch-pager" aria-label="검색 결과 페이지">
        <div class="srch-pager-info">${fromIdx}–${toIdx} / ${filtered.length}</div>
        <div class="srch-pager-controls">
          <button class="srch-page-btn" data-page="prev" ${searchPage === 1 ? 'disabled' : ''}>이전</button>
          ${pages.map(p => p === '…'
            ? `<span class="srch-page-ellipsis">…</span>`
            : `<button class="srch-page-btn ${p === searchPage ? 'is-active' : ''}" data-page="${p}">${p}</button>`
          ).join('')}
          <button class="srch-page-btn" data-page="next" ${searchPage === totalPages ? 'disabled' : ''}>다음</button>
        </div>
      </nav>
    `);
    resultsEl.querySelectorAll('.srch-page-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const v = btn.getAttribute('data-page');
        if (v === 'prev') searchPage--;
        else if (v === 'next') searchPage++;
        else searchPage = parseInt(v, 10);
        const inputEl = document.getElementById('search-input');
        renderSearchResults(inputEl ? inputEl.value : '');
        document.getElementById('section-search')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }
}

function buildPageButtons(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out = [1];
  if (current > 4) out.push('…');
  const lo = Math.max(2, current - 1);
  const hi = Math.min(total - 1, current + 1);
  for (let i = lo; i <= hi; i++) out.push(i);
  if (current < total - 3) out.push('…');
  out.push(total);
  return out;
}

async function load() {
  await Promise.all(KEYS.map(async (key) => {
    try {
      const r = await fetch(`data/${key}.json?t=${Date.now()}`);
      if (!r.ok) throw new Error(`${key} HTTP ${r.status}`);
      datasets[key] = await r.json();
    } catch (e) {
      console.warn(`[load] ${key} 실패:`, e.message);
      datasets[key] = null;
    }
  }));

  const validDates = Object.values(datasets)
    .filter(d => d?.updated_at)
    .map(d => new Date(d.updated_at).getTime());
  if (validDates.length) {
    document.getElementById('updated').textContent =
      new Date(Math.max(...validDates)).toLocaleString('ko-KR');
  }

  const notes = Object.values(datasets)
    .filter(d => d?.note)
    .map(d => `· ${d.name}: ${d.note}`);
  document.getElementById('note').innerHTML = notes.join('<br>');

  bindControls();
  render();
  loadTripleCross();
  loadSearchPool();
}

function bindControls() {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      currentMode = btn.dataset.mode;
      document.querySelectorAll('.tab').forEach(b => b.classList.toggle('is-active', b === btn));
      updateModePanel();
      render();
    });
  });
  document.querySelectorAll('input[type=checkbox]').forEach(cb => {
    cb.addEventListener('change', render);
  });
  document.getElementById('opt-period').addEventListener('change', render);
}

function updateModePanel() {
  const isCompare = currentMode === 'compare';
  document.getElementById('panel-compare').style.display = isCompare ? '' : 'none';
}

function getSelected() {
  if (currentMode !== 'compare') {
    return datasets[currentMode] ? [currentMode] : [];
  }
  return KEYS.filter(k =>
    document.querySelector(`#panel-compare input[data-key="${k}"]`)?.checked && datasets[k]
  );
}

function getPeriodCutoff() {
  const yrs = parseInt(document.getElementById('opt-period').value, 10);
  const d = new Date();
  d.setFullYear(d.getFullYear() - yrs);
  return d;
}

function filterByPeriod(d, metricKey) {
  const cutoff = getPeriodCutoff();
  const xs = [], ys = [];
  for (let i = 0; i < d.dates.length; i++) {
    const dt = new Date(d.dates[i]);
    if (dt < cutoff) continue;
    xs.push(d.dates[i]);
    ys.push(d[metricKey]?.[i] ?? null);
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

function percentileRank(values, target) {
  const v = values.filter(x => x !== null && Number.isFinite(x));
  if (!v.length) return null;
  const below = v.filter(x => x <= target).length;
  return (below / v.length) * 100;
}

function normalizeClose(ys) {
  let base = null;
  for (const y of ys) { if (y !== null && Number.isFinite(y)) { base = y; break; } }
  if (!base) return ys;
  return ys.map(y => y === null ? null : +(y / base * 100).toFixed(2));
}

function lastNonNull(arr) {
  for (let i = arr.length - 1; i >= 0; i--) if (arr[i] !== null) return { idx: i, val: arr[i] };
  return null;
}

function buildTraces(metricKey) {
  const selected = getSelected();
  const traces = [];
  const showBand = document.getElementById('opt-band').checked;
  const showMean = document.getElementById('opt-mean').checked;
  const norm     = metricKey === 'close' && document.getElementById('opt-norm').checked
                   && currentMode === 'compare';

  for (const key of selected) {
    const d = datasets[key];
    let { xs, ys } = filterByPeriod(d, metricKey);
    if (!ys.length || ys.every(v => v === null)) continue;
    if (norm) ys = normalizeClose(ys);

    const color = COLORS[key];
    const stat = statBand(ys);

    if (!norm && showBand && stat && stat.sd > 0 && metricKey !== 'close') {
      const upper = xs.map(() => +(stat.mean + stat.sd).toFixed(2));
      const lower = xs.map(() => +(stat.mean - stat.sd).toFixed(2));
      traces.push({
        x: xs, y: upper, type: 'scatter', mode: 'lines',
        line: { width: 0, color },
        showlegend: false, hoverinfo: 'skip',
      });
      traces.push({
        x: xs, y: lower, type: 'scatter', mode: 'lines',
        line: { width: 0, color },
        fill: 'tonexty', fillcolor: hexToRgba(color, 0.10),
        showlegend: false, hoverinfo: 'skip',
      });
    }
    if (!norm && showMean && stat && metricKey !== 'close') {
      traces.push({
        x: [xs[0], xs[xs.length - 1]],
        y: [stat.mean, stat.mean],
        type: 'scatter', mode: 'lines',
        line: { dash: 'dash', width: 1, color: hexToRgba(color, 0.55) },
        name: `${d.name} 평균 ${stat.mean.toFixed(2)}`,
        hoverinfo: 'name',
        showlegend: false,
      });
    }

    traces.push({
      x: xs, y: ys, type: 'scatter', mode: 'lines',
      name: d.name,
      line: { color, width: 2, shape: 'spline', smoothing: 0.3 },
      connectgaps: true,
      hovertemplate: '%{x|%Y-%m-%d}<br>%{y:.2f}<extra>' + d.name + '</extra>',
    });
  }
  return traces;
}

function hasAnyData(metricKey) {
  const selected = getSelected();
  for (const key of selected) {
    const arr = datasets[key]?.[metricKey];
    if (arr && arr.some(v => v !== null && Number.isFinite(v))) return true;
  }
  return false;
}

function updateCardVisibility() {
  for (const m of METRICS) {
    const card = document.querySelector(`.chart-card[data-metric="${m.key}"]`);
    if (!card) continue;
    const visible = currentMode === 'compare' || hasAnyData(m.key);
    card.style.display = visible ? '' : 'none';
  }
  const cards = document.querySelectorAll('.chart-card');
  const visibleCount = [...cards].filter(c => c.style.display !== 'none').length;
  document.querySelector('.charts').classList.toggle('charts-single', visibleCount === 1);
}

function render() {
  updateCardVisibility();
  for (const m of METRICS) {
    const traces = buildTraces(m.key);
    const layout = {
      margin: { l: 56, r: 16, t: 8, b: 36 },
      xaxis: { type: 'date', showgrid: false, color: '#6b7280' },
      yaxis: { gridcolor: '#eef2f7', color: '#6b7280', zerolinecolor: '#e5e7eb' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      legend: { orientation: 'h', y: -0.18, x: 0, font: { size: 11 } },
      hovermode: 'x unified',
      font: { family: 'inherit', size: 11 },
    };
    Plotly.react(m.chartId, traces, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }
  renderSummary();
}

function renderSummary() {
  const summaryEl = document.getElementById('summary');
  const titleEl = document.getElementById('summary-title');

  if (currentMode === 'compare') {
    titleEl.textContent = '현재 PER 요약';
    summaryEl.innerHTML = renderCompareSummary();
  } else {
    const d = datasets[currentMode];
    if (!d) {
      titleEl.textContent = '요약';
      summaryEl.innerHTML = '<p style="color:#9ca3af;font-size:11px">데이터 없음</p>';
      return;
    }
    titleEl.textContent = `${d.name} 통계`;
    summaryEl.innerHTML = renderSingleSummary(d);
  }
}

function renderCompareSummary() {
  const selected = getSelected();
  const rows = [];
  for (const key of selected) {
    const d = datasets[key];
    const { ys } = filterByPeriod(d, 'per');
    const stat = statBand(ys);
    const last = lastNonNull(ys);
    if (!last || !stat) {
      rows.push(`
        <div class="row">
          <span class="name">${d.name}</span>
          <span class="val" style="color:#9ca3af">데이터 없음</span>
        </div>`);
      continue;
    }
    const z = stat.sd > 0 ? (last.val - stat.mean) / stat.sd : 0;
    const zCls = z >= 0 ? 'z-pos' : 'z-neg';
    const sign = z >= 0 ? '+' : '';
    rows.push(`
      <div class="row">
        <span class="name">${d.name}</span>
        <span class="val">
          ${last.val.toFixed(2)}
          <div class="sub ${zCls}">평균 ${stat.mean.toFixed(2)} · ${sign}${z.toFixed(2)}σ</div>
        </span>
      </div>`);
  }
  return rows.join('') || '<p style="color:#9ca3af;font-size:11px">선택된 지수 없음</p>';
}

function renderSingleSummary(d) {
  const blocks = [];
  const labelMap = { per: 'PER', pbr: 'PBR', div_yield: '배당수익률 (%)' };
  for (const m of ['per', 'pbr', 'div_yield']) {
    const { ys } = filterByPeriod(d, m);
    const stat = statBand(ys);
    const last = lastNonNull(ys);
    if (!last || !stat) {
      blocks.push(`
        <div class="stat-block">
          <div class="stat-label">${labelMap[m]}</div>
          <div class="stat-val" style="color:#9ca3af">—</div>
        </div>`);
      continue;
    }
    const z = stat.sd > 0 ? (last.val - stat.mean) / stat.sd : 0;
    const pct = percentileRank(ys, last.val);
    const zCls = z >= 0 ? 'z-pos' : 'z-neg';
    const sign = z >= 0 ? '+' : '';
    blocks.push(`
      <div class="stat-block">
        <div class="stat-label">${labelMap[m]}</div>
        <div class="stat-val">${last.val.toFixed(2)}</div>
        <div class="stat-grid">
          <span>평균</span><span>${stat.mean.toFixed(2)}</span>
          <span>z-score</span><span class="${zCls}">${sign}${z.toFixed(2)}σ</span>
          <span>최저</span><span>${stat.min.toFixed(2)}</span>
          <span>최고</span><span>${stat.max.toFixed(2)}</span>
          <span>백분위</span><span>${pct.toFixed(0)}%</span>
        </div>
      </div>`);
  }
  return blocks.join('');
}

function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

load();
