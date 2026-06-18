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
   ├─ scripts/fetch_*.py             시장 지수·universe·매트릭스·컨센서스
   ├─ scripts/apply_triple_cross.py  4팩터 Z-Score → Top 10 후보 (정량, 재현 가능)
   └─ Agent tool (.claude/agents/)   정성 분석 + ranker 재순위 → ai_notes.json
```

**2단계 랭킹 구조 (핵심)**: 4팩터 정량 점수는 Top 10 *후보*를 객관·재현 가능하게 선별한다. 화면에 보이는 순위(`ai_rank`, #1~#10)는 그 위에서 `ranker` 에이전트가 **"저평가 해소 가능성"** 으로 재배열한 것이다. `quant_rank`(정량 순위)는 후보 자격, `ai_rank`(AI 순위)는 회복 가능성을 의미하며 둘 다 `ai_notes.json`에 commit되어 정적 재현된다.

3-Section 단일 정적 사이트:
- `index.html` — Section 1 시장 지수 (KOSPI/KOSDAQ/S&P 500) · Section 2 PER · PBR + Forward Top 10 · Section 3 종목 검색
- `stock.html?code={code}` — 종목 상세 (시그널 카드 + AI 분석 + PER/PBR 차트)
- `app.js` / `stock.js` — 페이지별 렌더링, Plotly 차트
- 한국 시장은 일별 데이터, S&P 500은 월별 (multpl + yfinance)

### 4팩터 알고리즘 (`scripts/apply_triple_cross.py`)

1. **Universe 필터**: 시총 3,000억+ 보통주 (우선주·리츠·스팩 제외) · 5Y PER 검증 (적자분기 ≤ 4Q) · Forward PER + 컨센 목표가 보유 → **303종목**
2. **4팩터 raw**:
   - `s1_per` = (avg_5y_per − cur)/avg_5y_per (Value)
   - `s1_pbr` = 같은 패턴 PBR (Value)
   - `s3_per` = (cur − fwd)/cur (Growth)
   - `upside` = (target − cur)/cur (Growth)
3. Rank → Z-Score 정규화 (universe 내, `multi_factor.py` 패턴)
4. 그룹 합산 → 재 Z-Score (Value · Growth)
5. 가중 합산: **`total = Value × 0.60 + Growth × 0.40`** → 상위 10 = **후보** (정량 `quant_rank`)
6. `ranker` 에이전트가 10 후보를 "저평가 해소 가능성"으로 재순위 → 화면 순위 `ai_rank`

- **티어 통일**: `tier`는 전 종목 `STRONG_BUY` (NaN만 `MISS`). 옛 Z-score 세분(HIDDEN_GEM/BUY/WATCH)은 `ai_rank` 순위 축과 달라 혼란을 줘 **제거됨** — 변경 시 `apply_triple_cross.py`의 `tier =` 한 줄과 `triple_cross.json` 양쪽 갱신.
- 이전 컨셉이었던 회복 모멘텀 (S2)·Value Trap hard rule·Winsorize는 **모두 제거됨** (정규화로 대체).
- 4팩터 점수 자체는 ranker가 **변경하지 않음**. 후보 풀은 정량이 보장, 그 안에서 순서만 재배열.

### AI 서브에이전트 (`.claude/agents/` — Anthropic 공식 형식)

YAML frontmatter (name / description with "Use PROACTIVELY" / tools / model) + 시스템 프롬프트.

파이프라인 순서: `fundamental-analyst` + `risk-analyst` → `synthesizer`(종목별 통합) → **`ranker`(10종목 종합 재순위)**.

- `fundamental-analyst.md` — 정성 모멘텀 (CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS) + **UNDERVALUATION_CAUSE** ("왜 저평가인가" + `nature`: TEMPORARY/STRUCTURAL, 필수 1개) — `tools: WebSearch, Read`
- `risk-analyst.md` — 정성 리스크 (EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE) — `tools: WebSearch, Read`
- `synthesizer.md` — 두 결과 통합 → 종목별 `ai_notes` JSON (`undervaluation_cause` 포함)
- `ranker.md` — 10종목을 "저평가 해소 가능성"으로 재순위 (`ai_rank`/`rerank_reason` 산출) — `tools: Read`, `model: sonnet`. 새 사실 생성 금지, 기존 출처 태그된 필드만 종합. 점수 룰 §4.1 촉매 4단계(+3.5/+2.5/+1/−2) · §4.2 실적 강도(+2.5/+1/+0.5/−1.5) · §4.3 `undervaluation_cause.nature`로 Value Trap 판별 · §4.4 단기 노이즈 보정 · §4.5 절대 밸류 페널티 · §4.7 동점은 `quant_rank` tiebreak.

모든 정성 항목 출처 태그 필수: `[출처: WebSearch · YYYY-MM]` / `확인 필요` / `[정량]`. 환각 방지 핵심.

DACON 제출용 동일 룰의 Skills.md 표준 6섹션 버전이 `skills/agents/`에 동기화됨 (`ranker` ↔ `portfolio_ranker`). 룰 변경 시 **양쪽 모두 갱신 + 해당 PDF·zip 재생성** 필요. 글자수 가이드는 "여유롭게"(강제 상한 아닌 권장 + 여유 상한, 출처 태그 포함 기준) — 정보·출처가 흐려질 만큼 줄이지 않음.

### Skills.md 패키지 (`skills/`)

DACON 제출용. 8개 .md + 같은 내용의 PDF 8개 구성:

- `value_recovery_quant.md` — 메인 룰북 (4팩터 Z-Score, 검증 5종, 인터페이스 명세, 운영 예외)
- `forward_attractive.md` / `dividend_value.md` — 보조 룰북 (단일 팩터 / 배당+가치)
- `agents/{fundamental,risk}_analyst.md`, `agents/synthesizer.md`, `agents/portfolio_ranker.md` — 정성 분석 4종 (`portfolio_ranker` = `.claude/agents/ranker.md`의 제출용)
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
# 개별 파이프라인 단계
python scripts/fetch_kr.py                         # KOSPI/KOSDAQ 일별 (증분 갱신)
python scripts/fetch_us.py                         # S&P 500 월별 (multpl + yfinance)
python scripts/fetch_universe.py                   # universe 마스터 (시총·필터)
python scripts/validate_universe_quick.py          # 5Y PER 검증
python scripts/fetch_consensus.py                  # Naver Wisereport 컨센서스
python scripts/fetch_matrix.py                     # 매트릭스 PER/PBR (60개월)
python scripts/refresh_universe_prices.py          # universe.json close 직전 거래일 종가로 갱신 (~30초)
python scripts/apply_triple_cross.py               # 4팩터 → Top 10
python scripts/fetch_batch.py --from-screen triple_cross --top-n 10  # Top 10 일별 풀
python scripts/fetch_financials.py                 # Top 10 재무 추이 (OpenDART, 매출·영업이익·순이익 5~6년)
python scripts/verify_data.py                      # 페치 결과 sanity 검증 (누락/stale 비율 체크)

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
├─ screens/triple_cross.json              4팩터 raw·Z·점수·Top 10 + all_ranked (tier 전부 STRONG_BUY)
├─ screens/ai_notes.json                  AI 정성 + ranker 재순위 (Top 10)
├─ stocks/{code}.json                     Top 10 일별 풀 데이터
└─ financials/{code}.json                 Top 10 재무 추이 (OpenDART, 매출·영업이익·순이익·마진 5~6년 + 최근분기)
```

- `ai_notes.json` 각 item: `{code, quant_rank, ai_rank, rerank_reason, ai_notes:{one_liner, investment_points[], risks[], undervaluation_cause:{text,nature}, verdict, evidence_strength, risk_level, ...}}`. items는 `ai_rank` 순 정렬. `meta.ranking`에 basis·ranked_at·note.
- 사이트는 `ai_rank` 순으로 카드 정렬. "왜 저평가인가" 블록(`.ai-uc`)이 nature별 색(일시적=초록 #059669 / 구조적=빨강 #dc2626, `:has()` 셀렉터)으로 표시 — app.js `renderAiBlock`, stock.js `loadAiNotes`, stock.html `#ai-detail-uc`.
- `data/matrix/`는 universe 통과 후보 모든 종목용 fallback (검색 페이지에서 어떤 종목이든 PER/PBR 차트 표시)
- `data/stocks/{code}.json`은 Top 10만 (일별 페치 비용 때문에 풀 데이터는 Top 10 한정)
- `data/financials/{code}.json`은 OpenDART(`DART_API_KEY`) 공식 재무. `fnlttSinglAcntAll` + account_id 표준 태그(`ifrs-full_Revenue`/`dart_OperatingIncomeLoss`/`ifrs-full_ProfitLoss`)로 매칭, CFS(연결) 우선·OFS(별도) 폴백. 각 item: `{code, corp_code, source, annual:[{year,revenue,op_income,op_margin,net_income,net_margin,fs_div}], latest_quarter}`. `_dart_corpmap.json`은 code→corp_code 캐시 (corpCode.xml 1회 다운). 우선 Top 10, `--universe`로 확장 가능. 적자·금융사는 마진 자연 결측 허용.

## Data Fetch 트러블슈팅 메모

외부 사이트 HTML 구조가 변경되어 페치가 깨지는 일이 가끔 있습니다. 다음 두 가지만 알아 두면 빠르게 대응 가능:

- **`scripts/fetch_us.py::_fetch_multpl`** — multpl.com 테이블 파싱을 **BeautifulSoup**로 처리 (이전 `pd.read_html`이 rowspan/abbr 구조 오해해서 1709개 행을 NaT 처리한 사고가 있었음). 페치 시 `_fetch_multpl(url)` 결과를 직접 출력해서 행 수·last value 점검하면 문제 즉시 식별.
- **`scripts/verify_data.py`** — `/update-data` 7단계로 자동 호출. 임계값 위반 시 exit 1로 commit/push **자동 차단**. 임계값: 시장 지수 fresh 7일 (sp500은 multpl yearly PBR 특성상 90일 허용), non-null 80%, universe.close 무효 ≤ 5%, 매트릭스 coverage ≥ 50% (적자 종목 자연 NaN 고려), Top 10 current_price > 0. 검증 실패하면 stderr 메시지가 어느 데이터 어느 임계값인지 정확히 알려줌.

새 데이터 출처 추가 시 `verify_data.py`에 해당 검증 룰도 추가하면 stale 사고를 미리 차단.

## Important Conventions

- **챗봇 형태 절대 금지** — 평가 25점(대시보드 자동 생성) 못 받음. 시각 대시보드만.
- **API 키 사이트 노출 금지** — 정적 호스팅 원칙, 사전 페치 후 JSON만 commit.
- **PER/PBR 정의**: TTM (Trailing Twelve Months, KRX/Naver 표준).
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
