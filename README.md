# DACON Skills.md 기반 가치투자 대시보드

> **Live**: https://hsh2578.github.io/dacon-skills-dashboard/
> **DACON 월간 해커톤 — "투자 데이터를 시각화하라 · Skills 기반 대시보드 설계" 출품작**

한국 웹에 PER·PBR 시계열 차트를 정리해 놓은 곳이 거의 없다는 시장 갭에서 출발한 가치투자 대시보드. **시장 지수(KOSPI/KOSDAQ/S&P 500)와 개별 종목 303+를 같은 스케일의 60개월 PER·PBR 시계열 + 평균 ±1σ 밴드**로 보여주고, 그 위에 **4팩터 Z-Score 가치투자 시그널**과 **AI 서브에이전트 정성 분석**을 결합한다.

---

## 핵심 명제

> "투자 분석 룰을 코드가 아닌 **Skills.md 한 장**에 정의하고, 그 룰을 다양한 데이터 구조(시계열·횡단면·컨센서스)에 동일하게 적용해 대시보드를 자동 생성한다."

분석가는 .md만 수정하면 가중치·필터·시각화가 즉시 갱신된다.

## 차별화 포인트 5가지

| # | 포인트 |
|---|---|
| 1 | **PER·PBR 시계열 인프라** — 한국 웹 시장 갭을 직접 메움. KOSPI·KOSDAQ·S&P 500 + 종목 300+ 모두 60개월 시계열 + 평균 ±1σ 밴드 |
| 2 | **분석 룰을 .md 한 장에 정의** — `skills/value_recovery_quant.md` 한 장이 곧 `apply_triple_cross.py`의 명세서 |
| 3 | **AI 서브에이전트 + 출처 태그 강제** — `[출처: WebSearch · YYYY-MM]`/`[정량]`/`확인 필요` 태그 없으면 출력 금지 → 환각 차단 |
| 4 | **정적 호스팅** — 백엔드·API 키 0. 심사자 키 없이 URL 한 줄로 즉시 접속 |
| 5 | **`/update-data` 슬래시 커맨드 한 줄** — 시장 지수·universe·매트릭스·점수·일별·AI 7단계 파이프라인 자동 실행 (~12분) |

---

## 4팩터 알고리즘 (`scripts/apply_triple_cross.py`)

```
Universe 필터 (303종목)
  ↓ 시총 3,000억+ 보통주 · 5Y PER 검증 · Forward PER + 컨센 보유

4팩터 raw 계산
  s1_per = (avg_5y_per − cur)/avg_5y_per           ┐ Value
  s1_pbr = (avg_5y_pbr − cur)/avg_5y_pbr           ┘
  s3_per = (cur − fwd)/cur                         ┐ Growth
  upside = (avg_target − cur)/cur                  ┘

Rank → Z-Score 정규화 (universe 내)
  ↓ rank percentile → norm.ppf — outlier 제거 + 분포 정규화

그룹 합산 → 재 Z-Score
  value_score  = Z(s1_per_z + s1_pbr_z)
  growth_score = Z(s3_per_z + upside_z)

가중 합산 → Top 10
  total_score = value_score × 0.60 + growth_score × 0.40
```

**왜 60:40인가**: Value(5Y 평균)는 안정된 앵커, Growth(컨센)는 분기마다 변동. 신뢰도 높은 Value에 더 큰 가중치.

**왜 Z-Score 정규화인가**: hard rule의 cliff effect(평균 14.1 / 현재 14.0 통과 vs 14.2 탈락) 제거. rank → Z로 outlier도 자동 처리.

상세는 [`skills/value_recovery_quant.md`](skills/value_recovery_quant.md) 참조.

---

## AI 서브에이전트 (`.claude/agents/` — Anthropic 공식 형식)

Top 10 종목에 대해 정성 모멘텀·리스크를 자동 생성. 모든 항목 출처 태그 필수.

| 에이전트 | 역할 | 출처 |
|---|---|---|
| `fundamental-analyst` | 사업 모멘텀 (CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS) | `[출처: WebSearch · YYYY-MM]` |
| `risk-analyst` | 리스크 (EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE) | 동일 |
| `synthesizer` | 두 결과 → 카드용 단일 JSON | 출처 태그 절대 제거 금지 |

같은 룰을 **DACON 제출용 표준 6섹션 형식**으로 동기화한 버전이 `skills/agents/`에 있음. 내용 동일, 형식만 차이.

---

## 폴더 구조

```
dacon-skills-dashboard/
├── skills/                        Skills.md 패키지 (제출물)
│   ├── value_recovery_quant.md    ◀ 메인 룰북
│   ├── agents/                    AI 서브에이전트 (DACON 표준 6섹션)
│   └── README.md
│
├── .claude/
│   ├── agents/                    AI 서브에이전트 (Anthropic 공식 형식, 실행용)
│   └── commands/update-data.md    /update-data 슬래시 커맨드
│
├── scripts/                       데이터 페치·점수 파이프라인 (Python)
├── data/                          정적 JSON (commit 후 GitHub Pages 자동 서빙)
│   ├── kospi.json kosdaq.json sp500.json
│   ├── universe.json              universe 303종목 + 컨센
│   ├── matrix/{per,pbr}_monthly.json   60개월 매트릭스 (전체)
│   ├── screens/triple_cross.json  4팩터 점수 + Top 10
│   ├── screens/ai_notes.json      AI 정성 분석
│   └── stocks/{code}.json         Top 10 일별 풀
│
├── index.html stock.html app.js stock.js style.css   정적 사이트
└── docs/기획서_초안.md            DACON 제출용 기획서
```

---

## 데이터 흐름

```
[로컬 Python] → data/*.json commit → GitHub Pages → [정적 사이트]
```

**백엔드 없음. API 키 노출 없음. 심사자 키 없이 동작.**

| 데이터 | 출처 | 인증 |
|---|---|---|
| KOSPI/KOSDAQ PER/PBR/배당/종가 | pykrx | KRX_ID/PW (로컬 페치만) |
| Forward PER + 컨센 목표가 | 네이버 Wisereport | 불필요 |
| S&P 500 PER (월별) | multpl + yfinance | 불필요 |
| AI 정성 분석 | Claude Code Agent + WebSearch | 로컬 페치만 |

---

## 운영 — `/update-data` 슬래시 커맨드

```bash
/update-data            # 시장지수·매트릭스·점수·일별·AI (universe 제외, ~12분)
/update-data --full     # universe 재구축 포함 (~30분)
/update-data --skip-ai  # AI 분석 건너뜀 (정량만, ~10분)
```

데이터 갱신은 로컬 → commit → push 후 ~30초 만에 GitHub Pages에 자동 반영.

---

## 평가 5축 매핑

| 평가항목 | 배점 | 본 서비스 적용 |
|---|---|---|
| 범용성 | 25 | Skills.md 표준 6섹션 스키마 + 룰북 카탈로그 + 매트릭스 fallback으로 universe 외 종목 PER/PBR 차트 표시 |
| Skills.md 설계 | 25 | 메인 룰북 + 보조 룰북 카탈로그 + AI 서브에이전트도 Skills.md로 정의 + 3-소스 원칙 |
| 대시보드 자동 생성 | 25 | 알고리즘 6단계 시각화 + 4-View(시장 지수·Top 10·검색·종목 상세) + 자동 갱신 |
| 바이브코딩 활용 | 15 | `/update-data` 슬래시 커맨드 + 서브에이전트 3종 + 코드 ≈ 100% LLM 생성 |
| 실용성·창의성 | 10 | 본인이 매주 사용할 도구 + 정량+정성 결합 + 시장 갭 직접 메움 |

---

## 일정 (대회)

| 단계 | 마감 |
|---|---|
| 기획서 PDF 제출 | 2026-04-30 09:59 |
| Skills.md 제출 | 2026-05-07 09:59 |
| 최종 웹 링크 제출 | 2026-05-14 09:59 |
| 1차 대중 투표 | 2026-05-14 ~ 05-18 |
| 2차 내부 심사 | 2026-05-18 ~ 05-22 |

---

## 제출물

1. **기획서 PDF** — `docs/기획서_초안.pdf` (서비스 개요·분석 흐름·대시보드 구성·Skills.md 설계·확장 기능)
2. **Skills.md (.zip)** — `skills/` 폴더 전체 (메인 룰북 + 보조 룰북 + AI 서브에이전트)
3. **웹 배포 URL** — https://hsh2578.github.io/dacon-skills-dashboard/
4. **GitHub 저장소** (선택) — https://github.com/hsh2578/dacon-skills-dashboard
