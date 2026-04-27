# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DACON 월간 해커톤 "투자 데이터를 시각화하라 — Skills 기반 대시보드 설계" 출품작.

- **공모 일정**: 기획서 PDF 2026-04-30 09:59 / Skills.md .zip 2026-05-07 / 최종 웹 URL 2026-05-14 / 1차 대중 투표 5/14~5/18 / 2차 내부 심사 5/18~5/22
- **평가 (100점)**: 범용성 25 · Skills.md 설계 25 · 대시보드 자동 생성 25 · 바이브코딩 활용 15 · 실용성·창의성 10
- **결정적 규칙**: 외부 API 사용 시 심사자가 별도 키 없이 확인 가능해야 함 → **정적 호스팅** (사전 페치 후 JSON commit) 채택

## Architecture

```
[로컬 Python] → data/*.json commit → GitHub Pages → [정적 사이트]
   ├─ scripts/fetch_*.py             시장 지수·universe·매트릭스·컨센서스
   ├─ scripts/apply_triple_cross.py  4팩터 Z-Score → Top 10
   └─ Agent tool (.claude/agents/)   정성 분석 → data/screens/ai_notes.json
```

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
5. 가중 합산: **`total = Value × 0.60 + Growth × 0.40`**
6. AI 정성 분석은 별도 단계 (점수 영향 X)

이전 컨셉이었던 회복 모멘텀 (S2)·Value Trap hard rule·Winsorize는 **모두 제거됨** (정규화로 대체).

### AI 서브에이전트 (`.claude/agents/` — Anthropic 공식 형식)

YAML frontmatter (name / description with "Use PROACTIVELY" / tools / model) + 시스템 프롬프트.

- `fundamental-analyst.md` — 정성 모멘텀 (CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS) — `tools: WebSearch, Read`
- `risk-analyst.md` — 정성 리스크 (EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE) — `tools: WebSearch, Read`
- `synthesizer.md` — 두 결과 통합 → 카드용 단일 JSON

모든 정성 항목 출처 태그 필수: `[출처: WebSearch · YYYY-MM]` / `확인 필요` / `[정량]`. 환각 방지 핵심.

DACON 제출용 동일 룰의 Skills.md 표준 6섹션 버전이 `skills/agents/`에 동기화됨 (이름·내용은 동일, 형식만 다름).

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
python scripts/apply_triple_cross.py               # 4팩터 → Top 10
python scripts/fetch_batch.py --from-screen triple_cross --top-n 10  # Top 10 일별 풀

# 사이트 로컬 서버 (정적 호스팅 시뮬레이션)
python -m http.server 8770
```

### 슬래시 커맨드 — `/update-data`

`.claude/commands/update-data.md` 정의. 위 파이프라인 + AI 정성 분석을 한 줄로 실행:

- `/update-data` — 시장 지수·매트릭스·점수·일별·AI (universe 제외, ~12분)
- `/update-data --full` — 위 + universe 재구축 (~30분)
- `/update-data --skip-ai` — AI 분석 건너뜀 (정량만, ~10분)

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
├─ screens/triple_cross.json              4팩터 raw·Z·점수·Top 10 + all_ranked
├─ screens/ai_notes.json                  AI 정성 분석 (Top 10)
└─ stocks/{code}.json                     Top 10 일별 풀 데이터
```

- `data/matrix/`는 universe 통과 후보 모든 종목용 fallback (검색 페이지에서 어떤 종목이든 PER/PBR 차트 표시)
- `data/stocks/{code}.json`은 Top 10만 (일별 페치 비용 때문에 풀 데이터는 Top 10 한정)

## Important Conventions

- **챗봇 형태 절대 금지** — 평가 25점(대시보드 자동 생성) 못 받음. 시각 대시보드만.
- **API 키 사이트 노출 금지** — 정적 호스팅 원칙, 사전 페치 후 JSON만 commit.
- **PER/PBR 정의**: TTM (Trailing Twelve Months, KRX/Naver 표준).
- **이름 컨벤션**: `data/screens/triple_cross.json` 같은 파일명은 옛 컨셉의 잔재 (UI 표시 이름은 "PER · PBR + Forward Top 10"). 데이터 호환성 위해 코드명은 유지.
- **이모지 미사용**: UI 톤은 퀀트 리서치 리포트체. 검색 input 아이콘만 예외.
- **Windows + Python 한글**: `os.environ.setdefault("PYTHONUTF8", "1")` + `sys.stdout.reconfigure(encoding="utf-8")` 필수.
- **AI 정성 항목 출처 태그**: `[출처: WebSearch · YYYY-MM]` / `확인 필요` / `[정량]` 절대 제거 금지.

## 미완성·시급 (2026-04-27 기준)

- `skills/value_recovery_quant.md` **메인 Skills.md 룰북 미작성** — 평가 25점 직격
- `skills/stock_detail/` 21섹션 .md 미작성
- 보조 룰북 (`forward_attractive.md`, `peer_relative.md`, `dividend_value.md`) 미작성
- 기획서 PDF 미작성 (4/30 09:59 마감)
- 시연 영상 1분 미제작 (대중 투표 임팩트용)

## Reference Assets (외부 폴더, 의존성 없음)

코드는 복사만 했고 의존하지 않음. 새 데이터·컨셉 추가 시 참고용:

- `vibecoding/주식 per pbr차트` — 시장 지수 차트 베이스, `incremental.py`, `naver_consensus.py`
- `vibecoding/주식웹사이트/국내주식웹사이트/stock-screener-kr` — `multi_factor.py` Z-Score 패턴 (현재 알고리즘 원형)
- `vibecoding/주식 ai 에이전트 종목 추천` — 서브에이전트 패턴 영감
