# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DACON 월간 해커톤 "투자 데이터를 시각화하라 — Skills 기반 대시보드 설계" **최종 1등 수상작**.

- **공모 일정**: 기획서 PDF 2026-04-30 09:59 / Skills.md .zip 2026-05-07 / 최종 웹 URL 2026-05-14 / 1차 대중 투표 5/14~5/18 / 2차 내부 심사 5/18~5/22
- **평가 (100점)**: 범용성 25 · Skills.md 설계 25 · 대시보드 자동 생성 25 · 바이브코딩 활용 15 · 실용성·창의성 10
- **결정적 규칙**: 외부 API 사용 시 심사자가 별도 키 없이 확인 가능해야 함 → **정적 호스팅** (사전 페치 후 JSON commit) 채택
- **사이트 표시 이름**: **PER · PBR Lens** (부제: 한국 주식 시계열 가치 평가 + 4팩터 스크리너) — 내부 코드/파일명은 옛 'triple_cross' 잔재 유지 (데이터 호환성)

## Architecture

```
[로컬 Python] → data/*.json commit → GitHub Pages → [정적 사이트]
   ├─ scripts/fetch_universe_api.py  universe 1단계 (KRX 공식 API, 시총·보통주 필터)
   ├─ scripts/validate_universe_api.py  2단계 5Y 실적 검증 (KIS 분기 EPS)
   ├─ scripts/fetch_consensus.py     3단계 컨센서스 (Naver Wisereport)
   ├─ scripts/fetch_matrix_kis.py    PER/PBR 매트릭스 (KRX 종가 + KIS EPS/BPS, TTM)
   ├─ scripts/fetch_batch_api.py     Top 20 일별 풀 (캐시 재사용, 새 호출 거의 없음)
   ├─ scripts/fetch_financials.py    OpenDART 재무(매출·영업이익·순이익 5~6년) — 저평가 진단 근거
   ├─ scripts/apply_triple_cross.py  4팩터 Z-Score → Top 20 후보 (정량, 재현 가능) · TOP_N 상수
   └─ Agent tool (.claude/agents/)   정성 분석 + ranker 재순위 (재무 교차검증) → ai_notes.json
```

### 데이터 출처 (2026-08-13 전면 전환)

pykrx(data.krx.co.kr 스크래핑)로 KRX IP가 1일 차단된 뒤 공식 경로로 옮겼다.
자세한 사고 경위는 아래 "Data Fetch 트러블슈팅 메모" 참조.

| 데이터 | 출처 | 키 |
|---|---|---|
| 종가·시가총액·상장주식수 | **KRX 공식 OpenAPI** (`data-dbg.krx.co.kr`) | `KRX_API_KEY` |
| EPS·BPS (분기 30행 ≈ 7년) | **KIS 재무비율** `FHKST66430300` | `KIS_REAL_APP_KEY` (실전 조회 전용) |
| Forward PER·목표주가 | Naver Wisereport | 없음 |
| 상세 재무 (매출·영업이익) | OpenDART | `DART_API_KEY` |
| KOSPI/KOSDAQ 지수 PER/PBR | **아직 pykrx** — 유일하게 남은 의존 | `KRX_ID`/`KRX_PW` |

- KRX 공식 OpenAPI는 **PER/PBR을 주지 않는다**(시세·시총·상장주식수만). 그래서 KIS EPS/BPS로 역산한다.
- 검증: 기준일 20260424에 universe 1단계를 돌려 **816종목**이 나와 pykrx 기록과 정확히 일치했고,
  종목별 시총 비율도 1.000이었다. 즉 시세·시총은 pykrx와 완전 동일하다.
- **캐시는 `data/.cache/`** (gitignore). 일별 종가 원본(~60MB)·주식수·KIS 응답·API 토큰이 들어간다.
  토큰이 들어가므로 **절대 커밋 금지** — `.gitignore`에 `data/.cache/`와 `*_token.json` 등록됨.
- 일별 종가는 **원주가로 저장**한다. 수정주가는 "현재 시점 기준"이라 새 분할이 생기면 과거 값이
  전부 바뀌지만, 원주가는 불변이라 한 번 받으면 재수집이 필요 없다. 보정은 사용 시점에 적용한다.

**2단계 랭킹 구조 (핵심)**: 4팩터 정량 점수는 **Top 20** *후보*를 객관·재현 가능하게 선별한다. 화면에 보이는 순위(`ai_rank`, #1~#20)는 그 위에서 `ranker` 에이전트가 **"저평가 해소 가능성"** 으로 재배열한 것이다. `quant_rank`(정량 순위)는 후보 자격, `ai_rank`(AI 순위)는 회복 가능성을 의미하며 둘 다 `ai_notes.json`에 commit되어 정적 재현된다.

후보 수는 `apply_triple_cross.py`의 **`TOP_N`** 한 곳에서 정한다(2026-08-13 10 → 20). 바꾸면 `fetch_batch_api.py`·`fetch_financials.py`·AI 분석 대상이 함께 따라온다 — 셋 다 `triple_cross.json`의 `top` 배열을 읽기 때문이다. `index.html`의 표기(Top 20 / #1~#20)도 같이 고칠 것.

> **2026-08-13 실행 관찰**: ranker가 매긴 `ai_rank`가 `undervaluation_cause.nature`와 거의 완전히 일치했다 — TEMPORARY 10종목이 1~10위, STRUCTURAL 10종목이 11~20위(예외 0건). §4.3이 §4.1 촉매·§4.2 실적강도·§4.5 절대밸류를 사실상 압도한 셈이라, **그룹 내부 순서의 근거는 상대적으로 약하다.** 또 verdict 20개 중 12개가 "관망 권고"로 매수 의견이 하나도 없었다. 룰 변경 전 반드시 재확인할 관찰 사항.

3-Section 단일 정적 사이트:
- `index.html` — Section 1 시장 지수 (KOSPI/KOSDAQ/S&P 500) · Section 2 PER · PBR + Forward Top 20 · Section 3 종목 검색
- `stock.html?code={code}` — 종목 상세 (시그널 카드 + AI 분석[숏 논거↔반박 듀얼 · Watch 모니터링] + 재무 추이(DART, `#fin-section`) + PER/PBR 차트). AI 분석은 Top 20만, 재무 추이는 universe 전체 표시
- `app.js` / `stock.js` — 페이지별 렌더링, Plotly 차트
- 한국 시장은 일별 데이터, S&P 500은 월별 (multpl PER/PBR + FRED 종가·yfinance 폴백)

### 4팩터 알고리즘 (`scripts/apply_triple_cross.py`)

1. **Universe 필터**: 시총 2,000억+ 보통주 (우선주·리츠·스팩 제외) · 5Y PER 검증 (적자분기 ≤ 4Q) · Forward PER + 컨센 목표가 보유

> **시총 컷 이력**: 2026-05 제출 당시엔 **3,000억**(→303종목)이었고, 2026-08-13 **2,000억으로 변경**했다. 2026년 6월 급등·8월 급락으로 3,000억 통과 종목이 816→672로 18% 줄면서 모집단이 과하게 축소된 게 이유다. 옛 `fetch_universe.py`의 기본값도 원래부터 `MIN_MARKET_CAP_억 = 2000`이었고 4월 실행 때만 `--min-cap 3000`을 수동으로 넘겼던 것이라, 이제 코드(`fetch_universe_api.py`)·문서·명령이 모두 2,000억으로 일치한다.
> **제출 원본인 `docs/기획서_초안.md`/`.pdf`는 3,000억 그대로 보존**한다(심사받은 기록). `skills/` 룰북은 재사용 가능한 산출물이므로 2,000억으로 갱신됨.
2. **4팩터 raw**:
   - `s1_per` = (avg_5y_per − cur)/avg_5y_per (Value)
   - `s1_pbr` = 같은 패턴 PBR (Value)
   - `s3_per` = (cur − fwd)/cur (Growth)
   - `upside` = (target − cur)/cur (Growth)
3. Rank → Z-Score 정규화 (universe 내, `multi_factor.py` 패턴)
4. 그룹 합산 → 재 Z-Score (Value · Growth)
5. 가중 합산: **`total = Value × 0.60 + Growth × 0.40`** → 상위 20 = **후보** (정량 `quant_rank`)
6. `ranker` 에이전트가 20 후보를 "저평가 해소 가능성"으로 재순위 → 화면 순위 `ai_rank`

- **티어 통일**: `tier`는 전 종목 `STRONG_BUY` (NaN만 `MISS`). 옛 Z-score 세분(HIDDEN_GEM/BUY/WATCH)은 `ai_rank` 순위 축과 달라 혼란을 줘 **제거됨** — 변경 시 `apply_triple_cross.py`의 `tier =` 한 줄과 `triple_cross.json` 양쪽 갱신.
- 이전 컨셉이었던 회복 모멘텀 (S2)·Value Trap hard rule·Winsorize는 **모두 제거됨** (정규화로 대체).
- 4팩터 점수 자체는 ranker가 **변경하지 않음**. 후보 풀은 정량이 보장, 그 안에서 순서만 재배열.

### AI 서브에이전트 (`.claude/agents/` — Anthropic 공식 형식)

YAML frontmatter (name / description with "Use PROACTIVELY" / tools / model) + 시스템 프롬프트.

파이프라인 순서: `fundamental-analyst` + `risk-analyst` → **`resolution-scout`** → `synthesizer`(종목별 통합) → **`ranker`(20종목 종합 재순위)**.

- `fundamental-analyst.md` — 정성 모멘텀 (CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS) + **UNDERVALUATION_CAUSE** ("왜 저평가인가" + `nature`: TEMPORARY/STRUCTURAL, 필수 1개) — `tools: WebSearch, Read`
- `risk-analyst.md` — 정성 리스크 (EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE) — `tools: WebSearch, Read`
- **`resolution-scout.md`** — **진단된 원인이 풀리는지 검색해 `nature`(일시적/지속적)를 최종 확정** (`tools: WebSearch, Read`). 반드시 `fundamental-analyst` **이후** — 검색 쿼리를 `undervaluation_cause`에서 파생시키기 때문. 산출 `resolution`: `evidence[]`(각 항목에 `kind`·`verifiable_by` 필수) · `counter_evidence[]` · `expected_window` · `verdict`(RESOLVING/EARLY_SIGNS/NO_EVIDENCE/WORSENING) · **`nature`·`nature_initial`·`nature_basis`·`confidence`**.
  - **`nature`의 주인이 여기로 옮겨졌다**: 이전엔 `fundamental-analyst`가 근거를 모으기 **전에** 판정하고 그 라벨이 끝까지 바뀌지 않았다. 이제 그건 **잠정 가설**이고, 증거가 반박하면 뒤집는다. 확정 규칙: `RESOLVING`→TEMPORARY / `NO_EVIDENCE`·`WORSENING`→**STRUCTURAL**(초기가 TEMPORARY였어도 뒤집음) / `EARLY_SIGNS`는 재무 마진 추세가 가른다.
  - **왜 필요했나**: `ranker`는 `tools: Read`뿐이라 검색을 못 하는데 "저평가 해소 가능성"을 판정했다. `fundamental-analyst`의 촉매 검색은 원인 진단과 같은 패스라 "이 종목에 무슨 호재가 있나"가 되고 "**바로 그 싼 이유가 걷히는가**"를 겨냥하지 못한다. 진단이 검증보다 앞서 있었다.
  - **핵심 규율**: 근거는 진단된 원인을 **직접** 겨냥해야 하고(무관한 호재 무효), `verifiable_by`가 없으면 의견이므로 버린다. **`NO_EVIDENCE`는 정당한 결과** — 억지로 채우면 Value Trap이 상위로 올라간다. **TEMPORARY/STRUCTURAL 비율을 맞추지 말 것** — 2026-08-13 실행에서 정확히 10:10이 나온 건 판정이 아니라 균형 맞추기의 징후였다. 저평가 후보군은 애초에 시장이 싸게 본 종목들이라 STRUCTURAL 다수가 자연스럽다.
- `synthesizer.md` — 세 결과 통합 → 종목별 `ai_notes` JSON. `undervaluation_cause.nature`에는 **`resolution.nature`(확정본)** 를 쓰고, 뒤집혔으면 `nature_initial`·`nature_basis`를 함께 남긴다. `resolution`은 **요약하지 말고 구조 그대로** 옮긴다 (항목 수·`kind`·`verifiable_by`가 ranker 점수 계산에 쓰임)
- `ranker.md` — 20종목(TOP_N)을 "저평가 해소 가능성"으로 재순위 (`ai_rank`/`rerank_reason` 산출) — `tools: Read`, `model: sonnet`. 새 사실 생성 금지, 기존 출처 태그된 필드만 종합. 점수 룰 **§4.1 저평가 해소 근거** — 주 입력은 `resolution.verdict`(RESOLVING +3.5 / EARLY_SIGNS +2.5 / NO_EVIDENCE −2 / WORSENING −3) + `expected_window` 시점 보정(1-2Q +0.5 / 1년+·불명 −0.5, **RESOLVING·EARLY_SIGNS에만** — 악화가 임박한 건 가점 대상이 아님) + counter_evidence 팽팽하면 −1. `resolution`이 없을 때만 옛 촉매 4단계로 폴백 · §4.2 실적 강도(+2.5/+1/+0.5/−1.5) · **§4.2.1 피크 어닝스 보정**(일회성 신작·수주發 이익이 risks에 선반영·차기작 공백으로 명시되면 +2.5→−1.0 — Forward PER 압축이 분모 착시인 경우 차단) · §4.3 `undervaluation_cause.nature`로 Value Trap 판별 + **`data/financials/` 영업이익률 추세 교차검증**(마진 추세 하락+매출 감소면 TEMPORARY라도 −1) + **`resolution`과 충돌 시 관측 우선**(STRUCTURAL+RESOLVING이면 −2를 −0.5로 완화 / TEMPORARY+WORSENING이면 +1을 −2로 반전 / TEMPORARY+NO_EVIDENCE면 +1→0) · §4.4 단기 노이즈 보정 · §4.5 절대 밸류 페널티 · §4.7 동점은 `quant_rank` tiebreak. `data/financials/{code}.json`이 있으면 nature 판정이 실제 이익 궤적에 앵커됨.

모든 정성 항목 출처 태그 필수: `[출처: WebSearch · YYYY-MM]` / `확인 필요` / `[정량]`. 환각 방지 핵심.

DACON 제출용 동일 룰의 Skills.md 표준 6섹션 버전이 `skills/agents/`에 동기화됨 (`ranker` ↔ `portfolio_ranker`). 룰 변경 시 **양쪽 모두 갱신 + 해당 PDF·zip 재생성** 필요. 글자수 가이드는 "여유롭게"(강제 상한 아닌 권장 + 여유 상한, 출처 태그 포함 기준) — 정보·출처가 흐려질 만큼 줄이지 않음.

### Skills.md 패키지 (`skills/`)

DACON 제출용. 9개 .md + 같은 내용의 PDF 9개 구성:

- `value_recovery_quant.md` — 메인 룰북 (4팩터 Z-Score, 검증 5종, 인터페이스 명세, 운영 예외)
- `forward_attractive.md` / `dividend_value.md` — 보조 룰북 (단일 팩터 / 배당+가치)
- `agents/{fundamental,risk}_analyst.md`, `agents/resolution_scout.md`, `agents/synthesizer.md`, `agents/portfolio_ranker.md` — 정성 분석 5종 (`portfolio_ranker` = `.claude/agents/ranker.md`의 제출용, `resolution_scout` = `resolution-scout.md`)
- `README.md` — 패키지 설명 + Skills.md 메타 명세 (새 룰북 추가 가이드, frontmatter 표준)

새 룰북 추가 시 `skills/README.md`의 "Skills.md 메타 명세" 섹션 frontmatter 필드(name/version/type/output 등)를 따라야 함.

## Frontend Design System

`style.css` 상단에 CSS 변수로 디자인 토큰이 정의됨. 색·여백·그림자 변경은 토큰만 수정.

| 영역 | 적용 |
|---|---|
| 토큰 | `--bg / --surface / --border / --text / --text-muted / --accent / --shadow-card` 등 (style.css 첫 30줄) |
| 폰트 | **Pretendard** (CDN, SIL OFL) 본 폰트 + **JetBrains Mono** (브랜드 마크에서, SIL OFL). `font-feature-settings: 'ss03' 1, 'kern' 1` |
| 색 | 모노크롬 베이스 + 한국 시장 색 컨벤션 (`--kr-up: #e31b1b` 빨강 상승 / `--kr-down: #1261c4` 파랑 하락) |
| 헤더 | sticky + `backdrop-filter: blur(14px)` |
| 모바일 | `@media (max-width: 768px)` — 헤더 nav 풀 너비 3등분, padding 축소, screen-meta 세로 정렬, `html/body { overflow-x: hidden }` 안전장치 |
| 검색 페이지네이션 | 30개/페이지 (`SEARCH_PAGE_SIZE` in app.js) + `buildPageButtons()` 7페이지 초과 시 ellipsis |
| 저작권 | 폰트는 SIL OFL만 사용, 외부 이미지·아이콘 0개. 검색창 input 아이콘만 텍스트 이모지 예외 |

UI 검증은 chrome devtools MCP의 `resize_page`로 데스크톱(1440)·모바일(390) 양쪽 점검 권장. PDF 시각 검증은 `pypdfium2`로 페이지 PNG 추출 (아래 빌드 명령 섹션 참조).

## Common Commands

`.env`에 `KRX_ID` / `KRX_PW` 필요 (pykrx 인증, 로컬에만).

```bash
# 개별 파이프라인 단계 (2026-08-13 이후 — *_api / *_kis 계열이 정식)
python scripts/fetch_kr.py                         # KOSPI/KOSDAQ 지수 (아직 pykrx)
python scripts/fetch_us.py                         # S&P 500 월별 (multpl PER/PBR + FRED 종가·yfinance 폴백)

python scripts/fetch_universe_api.py               # universe 1단계 — 시총 2,000억+ 보통주 (KRX 공식 API)
python scripts/fetch_matrix_kis.py --daily --all   # 매트릭스 — 일별 종가 수집 후 월평균, 전 종목
python scripts/validate_universe_api.py            # 2단계 — 5Y 실적 검증 (KIS 분기 EPS)
python scripts/fetch_consensus.py                  # 3단계 — Naver 컨센서스 (Forward PER·목표주가)
python scripts/apply_triple_cross.py               # 4팩터 → Top 20 (TOP_N)
python scripts/fetch_batch_api.py --top-n 20       # Top 20 일별 풀 (캐시 재사용)
python scripts/fetch_financials.py                 # Top 20 재무 추이 (OpenDART)

# 검증 3종 — 보는 게 각각 다르다. 셋 다 돌릴 것.
python scripts/verify_data.py                      # 산출물 신선도·커버리지
python scripts/check_golden_matrix.py              # 매트릭스 과거 값 회귀 (골든 30종목)
python -m pytest tests/ -q                         # TTM 판정 로직 (네트워크 불필요)

# 매트릭스 옵션
#   --daily       일별 종가를 받아 월평균으로 집계 (특정일 노이즈 제거). 최초 ~15분,
#                 이후 캐시 증분이라 수십 초. 생략하면 매월 15일 1일 샘플.
#   --all         universe 밖 종목까지 (검색 페이지 차트 fallback용, KIS ~2,200콜)
#   --replace     정식 경로(per_monthly.json)에 기록. 생략하면 *_ttm.json
#   --krx-workers 일별 수집 동시성 (기본 4). 순차 대비 4배.

# 삭제됨 (pykrx 의존 — 2026-08-13 KRX IP 차단 유발. 되살리지 말 것)
#   fetch_universe.py → fetch_universe_api.py
#   validate_universe_quick.py → validate_universe_api.py
#   fetch_matrix.py → fetch_matrix_kis.py
#   fetch_batch.py → fetch_batch_api.py
#   refresh_universe_prices.py → fetch_universe_api.py가 종가까지 갱신
#   fetch_stock_kr.py → fetch_batch_api.py
# 이력은 커밋 히스토리에 남아 있다 (git log -- scripts/fetch_matrix.py).

# 사이트 로컬 서버 (정적 호스팅 시뮬레이션)
python -m http.server 8770
```

### 제출용 산출물 빌드 (PDF + zip)

```bash
# 기획서 .md → PDF (한 번)
npx --yes md-to-pdf docs/기획서_초안.md --stylesheet docs/pdf-style.css \
  --pdf-options '{"format":"A4","margin":{"top":"18mm","bottom":"18mm","left":"16mm","right":"16mm"},"printBackground":true}'

# Skills.md 8개 일괄 PDF 변환 (portfolio_ranker 포함 — 누락 주의)
for f in skills/value_recovery_quant.md skills/forward_attractive.md skills/dividend_value.md \
         skills/agents/fundamental_analyst.md skills/agents/risk_analyst.md \
         skills/agents/synthesizer.md skills/agents/portfolio_ranker.md skills/README.md; do
  npx --yes md-to-pdf "$f" --stylesheet docs/pdf-style.css \
    --pdf-options '{"format":"A4","margin":{"top":"18mm","bottom":"18mm","left":"16mm","right":"16mm"},"printBackground":true}'
done

# Skills.md 제출용 .zip 생성 (skills/ 폴더 전체)
python -c "
import zipfile, os
out = 'skills_submission.zip'
if os.path.exists(out): os.remove(out)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('skills'):
        for f in files:
            fp = os.path.join(root, f)
            zf.write(fp, os.path.relpath(fp, '.'))
"

# PDF 시각 검증 (페이지 → PNG, 본인 확인용)
python -c "
import pypdfium2 as pdfium  # pip install pypdfium2
pdf = pdfium.PdfDocument('docs/기획서_초안.pdf')
for i in range(len(pdf)):
    pdf[i].render(scale=1.4).to_pil().save(f'_p{i+1}.png')
"
```

PDF 스타일은 `docs/pdf-style.css`에 통합됨 (Pretendard 폰트 + 다이어그램 박스 스타일 + 표 페이지 나누기 방지).

### 슬래시 커맨드 — `/update-data`

`.claude/commands/update-data.md` 정의. 위 파이프라인 + AI 정성 분석을 한 줄로 실행:

- `/update-data` — 시장 지수·매트릭스·점수·일별·AI (universe 제외, ~12분)
- `/update-data --full` — 위 + universe 재구축 (~30분)
- `/update-data --skip-ai` — AI 분석 건너뜀 (정량만, ~10분)

**운영 빈도**: 평소 **주 1회** (매일 X — 매일 돌리면 AI 정성 분석이 새로 생성되어 ai_rank가 며칠 사이 4단계 이상 흔들림. 변동성 자체는 정성 본질로 수용하되 빈도로 완화). 대회·심사 기간엔 예외적으로 더 자주 가능.

AI 정성 분석은 Agent 도구로 종목 10개 동시 발사 (`subagent_type=general-purpose` + prompt에서 `.claude/agents/` 룰을 Read). `subagent_type` 직접 호출은 사전 등록된 type만 받으므로 이 우회 방식 사용.

## Deployment

- **Repository**: https://github.com/hsh2578/dacon-skills-dashboard (public)
- **Live Site**: https://hsh2578.github.io/dacon-skills-dashboard/ (GitHub Pages, master / root)
- 빌드는 정적 파일 그대로 서빙 (별도 빌드 스텝 없음). 데이터 갱신은 로컬에서 실행 → commit & push → 자동 배포 (~30초).
- 사이트는 `?t=${Date.now()}` 캐시 버스터로 fetch하므로 commit 후 새로고침만 하면 새 데이터 반영.

## Git Notes

- `git config user.name`/`user.email` **미설정**. 사용자가 직접 한 번 설정하는 게 편함:
  ```bash
  git config --local user.name "hsh2578"
  git config --local user.email "hsh2578111@gmail.com"
  ```
- 위 설정 전까지는 instruction "NEVER update the git config" 준수를 위해 환경변수 우회:
  ```bash
  GIT_AUTHOR_NAME="hsh2578" GIT_AUTHOR_EMAIL="hsh2578111@gmail.com" \
  GIT_COMMITTER_NAME="hsh2578" GIT_COMMITTER_EMAIL="hsh2578111@gmail.com" \
  git commit -m "..."
  ```

## Data Layout

```
data/
├─ kospi.json kosdaq.json sp500.json     시장 지수 시계열 (Section 1)
├─ universe.json                          universe 통과/제외 + 컨센서스
├─ matrix/{per,pbr}_monthly.json          PER/PBR 60개월 매트릭스 (검색·종목 차트)
├─ screens/triple_cross.json              4팩터 raw·Z·점수·Top 20 + all_ranked (tier 전부 STRONG_BUY)
├─ screens/ai_notes.json                  AI 정성 + ranker 재순위 (Top 20)
├─ stocks/{code}.json                     Top 20 일별 풀 데이터
└─ financials/{code}.json                 재무 추이 (OpenDART, 매출·영업이익·순이익·마진 5~6년 + 최근분기) — Top 20 기본, --universe로 전체
```

- `ai_notes.json` 각 item: `{code, quant_rank, ai_rank, rerank_reason, ai_notes:{one_liner, investment_points[], risks[], undervaluation_cause:{text, nature, nature_initial?, nature_basis?}, resolution:{cause_restated, conditions[], evidence[], counter_evidence[], expected_window, verdict, nature, nature_initial, nature_basis, confidence, summary}, verdict, evidence_strength, risk_level, ...}}`. items는 `ai_rank` 순 정렬. `meta.ranking`에 basis·ranked_at·note.
  - `nature_initial`은 **증거가 초기 가설을 뒤집었을 때만** 존재한다. 있으면 사이트에 "초기 일시적 → 검증 후 구조적" 배지가 뜬다.
- 사이트는 `ai_rank` 순으로 카드 정렬. "왜 저평가인가" 블록(`.ai-uc`)이 nature별 색(일시적=초록 #059669 / 구조적=빨강 #dc2626, `:has()` 셀렉터)으로 표시 — app.js `renderAiBlock`/`natLabel`, stock.js `loadAiNotes`, stock.html `#ai-detail-uc`.
- **해소 근거 블록**(`.ai-res`, 종목 상세 전용) — `resolution`을 근거/반증 2열로 표시. verdict 배지 색: RESOLVING 초록 · EARLY_SIGNS 청록 · NO_EVIDENCE 회색 · WORSENING 빨강. `expected_window`는 RESOLVING·EARLY_SIGNS일 때만 노출(악화 임박은 안내 가치가 없음). `evidence`가 비면 "근거를 찾지 못했습니다"를 **그대로 표시** — 결측이 아니라 결론이다. stock.js `renderResolution`, stock.html `#ai-detail-res`.
- `data/matrix/`는 universe 통과 후보 모든 종목용 fallback (검색 페이지에서 어떤 종목이든 PER/PBR 차트 표시)
- `data/stocks/{code}.json`은 Top 20만 (일별 페치 비용 때문에 풀 데이터는 Top 20 한정)
- `data/financials/{code}.json`은 OpenDART(`DART_API_KEY`) 공식 재무. `fnlttSinglAcntAll` + account_id 표준 태그(`ifrs-full_Revenue`/`dart_OperatingIncomeLoss`/`ifrs-full_ProfitLoss`)로 매칭, CFS(연결) 우선·OFS(별도) 폴백. 각 item: `{code, corp_code, source, annual:[{year,revenue,op_income,op_margin,net_income,net_margin,fs_div}], latest_quarter}`. `_dart_corpmap.json`은 code→corp_code 캐시 (corpCode.xml 1회 다운). 적자·금융사는 마진 자연 결측 허용.
  - `/update-data`는 매번 **Top 20만** 페치. **universe 전체**(299종목)는 `python scripts/fetch_financials.py --universe`를 가끔(주1회 정도) 따로 실행 — 그래야 검색→상세에서 Top 20이 아닌 종목도 `stock.html`의 독립 **재무 추이 섹션**(`#fin-section`, `renderFinChart`)이 표시됨. 이 섹션은 `ai_notes` 없이 `data/financials/{code}.json`만 있으면 렌더된다 (Top 20은 AI 섹션 + 재무 섹션 둘 다).

## 검증 계층 (2026-08-14 추가)

세 겹이고 각각 다른 걸 봅니다. 하나로 대체되지 않습니다.

| 검사 | 보는 것 | 못 보는 것 |
|---|---|---|
| `verify_data.py` | 산출물 신선도·커버리지·Top N 정합 | **값의 정확성** — PBR이 154배여도 통과 |
| `check_golden_matrix.py` | 동결 30종목의 **과거 값 불변성** | 신규 종목·최신 달 |
| `pytest tests/` | TTM 판정 로직 · 컨센서스 붕괴 가드 | 실제 API 응답 형태 변화 |

### 조용한 열화 방지 (2026-08-14)

"오류 없이 나쁜 데이터가 통과하는" 경로를 세 군데서 막았습니다. 공통 원인은
**실패를 빈 값으로 표현**하고 그걸 그대로 기록한 것입니다.

- **네이버 컨센서스** — 스로틀되면 요약표가 "최근3개월 이내에 제시된 의견이 없습니다"로
  온다. `fetch_consensus.py`는 컨센서스 없는 종목을 universe에서 **제외**하고 결과를
  무조건 덮어썼으므로, 스로틀 한 번에 모집단이 무너지고 그 집합으로 4팩터가 돌았다.
  → 직전 값 승계(`CARRY_MAX_DAYS` 14일) + 총량 가드(`MIN_RETAIN_RATIO` 80% 미만이면
  **기록 거부**). `fetch_batch_api.py`도 `merge_consensus()`로 기존 값을 지킨다.
  실측: 2026-08-14 스로틀 상황에서 20종목 중 18종목의 목표주가가 날아가던 것이 손실 0.
  승계된 항목은 `consensus_carried: true`로 표시되므로 나중에 재페치할 대상이 보인다.
- **KIS 캐시 폴백** — `_real` → `_paper` → 무접미 순으로 훑어, 실전 캐시가 없으면
  모의투자 데이터로 조용히 내려앉았다. → `feeds.kis_ratio_cache_path()`로 계정 명시, 폴백 제거.
- **ai_notes stale** — 정량 순위가 바뀌어도 AI 분석만 옛 Top N으로 남았다.
  → `verify_data.py`가 현재 Top N에 없는 종목이 섞이면 오류로 차단.

> 새 외부 소스를 붙일 때 물어볼 것: **"이 소스가 조용히 빈 값을 주면 무슨 일이 생기나?"**
> 답이 "종목이 빠진다"거나 "값이 null로 덮인다"면 승계·가드를 같이 넣어야 합니다.

- **`scripts/ttm.py`** — TTM 판정의 유일한 소유자. 순수 함수라 네트워크 없이 테스트됩니다.
  불변식 3개(0=결측 · 연간 폴백 금지 · 공시 시차)가 전부 실제 사고 뒤에 추가된 것이라,
  `fetch_matrix_kis.py`·`validate_universe_api.py`에 복제돼 있던 것을 한 곳으로 모았습니다.
  **다시 복제하지 말 것** — 한쪽만 고치면 유니버스 기준과 매트릭스가 조용히 어긋납니다.
- **골든 스냅샷** (`tests/golden/matrix.json`) — 과거 PER/PBR은 원칙적으로 불변입니다.
  일별 종가를 **원주가로** 저장하고 수정주가 보정을 사용 시점에 적용하기 때문입니다.
  따라서 과거 값 변동은 (a) 주식수 변동 (b) 실적 정정 (c) **회귀** 셋 중 하나이고,
  (a)는 전 구간이 균일하게 움직여 자동 분류됩니다. 이관 때 나온 버그 7개를 냈던
  종목(롯데렌탈·SK텔레콤·에코프로 등)이 `BUG_HISTORY`에 등록돼 있습니다.
  의도한 변경이면 `--freeze`로 재동결. **정식 파일 덮어쓰기 전 `--suffix _ttm`으로 후보 검사 가능.**

> pykrx를 삭제하면서 "손으로 대조할 정답"이 사라졌기 때문에 만든 계층입니다.
> 이관 당시 버그 7개를 전부 pykrx 값과 대조해서 찾았다는 걸 기억할 것.

## Data Fetch 트러블슈팅 메모

외부 사이트 HTML 구조가 변경되어 페치가 깨지는 일이 가끔 있습니다. 다음 두 가지만 알아 두면 빠르게 대응 가능:

- **`scripts/fetch_us.py::_fetch_multpl`** — multpl.com 테이블 파싱을 **BeautifulSoup**로 처리 (이전 `pd.read_html`이 rowspan/abbr 구조 오해해서 1709개 행을 NaT 처리한 사고가 있었음). 페치 시 `_fetch_multpl(url)` 결과를 직접 출력해서 행 수·last value 점검하면 문제 즉시 식별. **S&P 종가는 FRED(`FRED_API_KEY`) 우선·yfinance 폴백** (`_fetch_fred_sp500_monthly`, `meta.close_source`로 확인). PER/PBR/배당은 FRED 미제공이라 multpl 유지. **KRX 공식 OpenAPI(`KRX_API_KEY`)는 PER/PBR을 주지 않음**(시세·시총·기본정보만) — PER/PBR 매트릭스는 pykrx(`KRX_ID`/`KRX_PW` 로그인) 전용. 그래서 KRX 로그인 전환 불가.
- **`scripts/verify_data.py`** — `/update-data` 7단계로 자동 호출. 임계값 위반 시 exit 1로 commit/push **자동 차단**. 임계값: 시장 지수 fresh 7일 (sp500은 multpl yearly PBR 특성상 90일 허용), non-null 80%, universe.close 무효 ≤ 5%, 매트릭스 coverage ≥ 50% (적자 종목 자연 NaN 고려), Top 10 current_price > 0. 검증 실패하면 stderr 메시지가 어느 데이터 어느 임계값인지 정확히 알려줌.

새 데이터 출처 추가 시 `verify_data.py`에 해당 검증 룰도 추가하면 stale 사고를 미리 차단.

## Important Conventions

- **챗봇 형태 절대 금지** — 평가 25점(대시보드 자동 생성) 못 받음. 시각 대시보드만.
- **API 키 사이트 노출 금지** — 정적 호스팅 원칙, 사전 페치 후 JSON만 commit.
- **PER/PBR 정의**: **TTM (최근 4개 분기 합산)**. 2026-08-13 전환.
  ```
  PER = 수정주가 / TTM EPS      TTM = 직전연간 − 전년동기누적 + 당해누적
  PBR = 수정주가 / BPS          최근 공시 분기말
  공시 시차: 분기 45일 · 사업보고서 90일 (look-ahead 방지)
  ```
  **KRX·네이버 표시값과 다르다 — 의도된 차이다.** 실측 결과 KRX PER/PBR은 TTM이
  아니라 **직전 확정 결산 기준이고 연 1회(5월)만 갱신**된다(58개월 오차표에서 4월→5월에만
  계단이 있고 8월·11월엔 없음). 그래서 실적이 급변한 기업은 KRX 값이 최대 17개월 뒤처진다.
  전환 전 문서에 "TTM (KRX/Naver 표준)"이라고 적혀 있었으나 **실제 데이터는 연간 기준이었고
  문서가 틀렸던 것**이다.
  - 검증: IC 백테스트(58개월)에서 연간·TTM·정규화(CAPE) 3종을 비교했으나 테스트 구간이
    10~16개월뿐이라 **판정 불가**였다(정규화만 명확히 열등해 탈락). TTM 채택은 성능 우위가
    아니라 "최신 실적 반영"이라는 사용자 결정에 따른 것. 데이터가 쌓이면 재판정 가능.
  - 부작용 주의: TTM은 **이익 급증 기업의 PER을 낮춰 보이게** 한다(피크 어닝스 착시).
    `ranker` §4.2.1이 정성 단계에서 이를 걸러내는 역할을 계속 해야 한다.
- **이름 컨벤션**: `data/screens/triple_cross.json` 같은 파일명은 옛 컨셉의 잔재 (UI 표시 이름은 "PER · PBR + Forward Top 10"). 데이터 호환성 위해 코드명은 유지.
- **이모지 미사용**: UI 톤은 퀀트 리서치 리포트체. 검색 input 아이콘만 예외.
- **Windows + Python 한글**: `os.environ.setdefault("PYTHONUTF8", "1")` + `sys.stdout.reconfigure(encoding="utf-8")` 필수.
- **AI 정성 항목 출처 태그**: `[출처: WebSearch · YYYY-MM]` / `확인 필요` / `[정량]` 절대 제거 금지. `undervaluation_cause.text`도 동일.
- **순위 용어 혼동 금지**: `quant_rank` = 4팩터 정량 후보 순위 / `ai_rank` = ranker 재순위(화면 표시 메인). ranker는 4팩터 점수를 바꾸지 않음.
- **`npx md-to-pdf` 백그라운드 실행 금지**: 백그라운드에서 hang함(이번 세션 실제 사고). PDF 생성은 foreground + 충분한 timeout(≥180000ms). zip 재생성은 순수 Python이라 안전 — PDF hang 시 룰북/데이터 먼저 commit 후 PDF·zip 분리 처리.
- **ai_rank 변동성은 본질로 수용**: 매 갱신마다 새 WebSearch·뉴스·실적이 verdict/risk_level/evidence_strength 라벨을 다시 매기므로 며칠 사이 4단계 이상 흔들릴 수 있음. 이건 의도된 동작. **ranker 룰의 §4.6 가중을 축소하거나 정량 점수(quant_rank/total_score)를 ranker 점수에 섞는 변경을 제안하지 말 것** — 후자는 "4팩터=후보 선정 / ranker=정성만" 2단계 원칙 위반. 흔들림은 갱신 빈도(주 1회)로 완화.

## 제출 산출물 (2026-05-21 기준)

| 제출물 | 위치 | 상태 |
|---|---|---|
| 기획서 PDF | `docs/기획서_초안.pdf` (1.4 MB) | 완료 |
| Skills.md 패키지 | `skills_submission.zip` (~2.45 MB, .md 8 + .pdf 8) | 완료 |
| 배포 URL | https://hsh2578.github.io/dacon-skills-dashboard/ | 완료 |
| GitHub 저장소 | https://github.com/hsh2578/dacon-skills-dashboard | 완료 (선택 제출) |
| **최종 결과** | DACON 월간 해커톤 **1등 수상** | Skills 기반 대시보드 설계 부문 |

기획서·Skills.md 본문을 수정하면 위 "제출용 산출물 빌드" 명령으로 PDF·zip을 다시 생성해야 함.

### 후속 확장 아이디어 (선택)

수상 이후에도 시스템 확장 여지로 남겨둔 항목들. 우선순위는 사용자가 정함.

- ETF 또는 포트폴리오 데이터 데모 1패널 추가 → universe·자산 클래스 확장 실증
- `skills/stock_detail/` 21섹션 .md (확장 기능, 현재 §7에만 명시)
- `forward_attractive` / `dividend_value` 룰북의 페치 스크립트 + 사이트 페이지 (현재 명세만 확정)

## Reference Assets (외부 폴더, 의존성 없음)

코드는 복사만 했고 의존하지 않음. 새 데이터·컨셉 추가 시 참고용:

- `vibecoding/주식 per pbr차트` — 시장 지수 차트 베이스, `incremental.py`, `naver_consensus.py`
- `vibecoding/주식웹사이트/국내주식웹사이트/stock-screener-kr` — `multi_factor.py` Z-Score 패턴 (현재 알고리즘 원형)
- `vibecoding/주식 ai 에이전트 종목 추천` — 서브에이전트 패턴 영감
