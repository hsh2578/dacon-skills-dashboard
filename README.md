# PER · PBR Lens — 한국 주식 시계열 가치 평가 + 4팩터 스크리너

> **Live**: https://hsh2578.github.io/dacon-skills-dashboard/
> **DACON 월간 해커톤 — "투자 데이터를 시각화하라 · Skills 기반 대시보드 설계" 출품작**

한국 웹에 PER·PBR 시계열 차트를 정리해 놓은 곳이 거의 없다는 시장 갭에서 출발한 가치투자 대시보드입니다. **시장 지수(KOSPI/KOSDAQ/S&P 500)와 개별 종목 300+종을 같은 스케일의 60개월 PER·PBR 시계열 + 평균 ±1σ 밴드**로 보여주고, 그 위에 **4팩터 Z-Score 가치투자 시그널**과 **AI 서브에이전트 정성 분석**을 결합한 정적 사이트입니다.

---

## 핵심 명제

> "투자 분석 룰을 코드가 아닌 **Skills.md 한 장**에 정의하고, 그 룰을 다양한 데이터 구조(시계열·횡단면·컨센서스)에 동일하게 적용해 대시보드를 자동 생성한다."

분석가는 .md 파일만 수정하면 가중치·필터·시각화가 즉시 갱신됩니다.

## 차별화 포인트 5가지

| # | 포인트 |
|---|---|
| 1 | **PER·PBR 시계열 인프라** — 한국 웹의 시장 갭을 직접 메움. 시장 지수와 종목 300+를 같은 스케일의 60개월 시계열 + 평균 ±1σ 밴드 |
| 2 | **분석 룰을 .md 한 장에 정의** — `skills/value_recovery_quant.md` 한 장이 곧 `scripts/apply_triple_cross.py`의 명세서 |
| 3 | **AI 서브에이전트 + 출처 태그 강제** — `[출처: WebSearch · YYYY-MM]` / `[정량]` / `확인 필요` 태그 없으면 출력 금지 → 환각 차단 |
| 4 | **정적 호스팅** — 백엔드·API 키 0. 심사자가 별도 인증 없이 URL 한 줄로 즉시 접속 |
| 5 | **`/update-data` 슬래시 커맨드 한 줄** — 시장 지수 · universe · 매트릭스 · 점수 · 일별 · AI · 검증 8단계 자동 실행 (~12분) |

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
  ↓ rank percentile → norm.ppf · outlier 제거 + 분포 정규화

그룹 합산 → 재 Z-Score
  value_score  = Z(s1_per_z + s1_pbr_z)
  growth_score = Z(s3_per_z + upside_z)

가중 합산 → Top 10
  total_score = value_score × 0.60 + growth_score × 0.40
```

**왜 60:40 가중치인가**: Value(5Y 평균)는 안정된 앵커, Growth(컨센)는 분기마다 변동. 신뢰도 높은 Value에 더 큰 가중치.

**왜 Z-Score 정규화인가**: hard rule의 cliff effect(평균 14.1 / 현재 14.0 통과 vs 14.2 탈락) 제거. rank → Z로 outlier도 자동 처리.

상세는 [`skills/value_recovery_quant.md`](skills/value_recovery_quant.md) 참조.

---

## AI 서브에이전트 (`.claude/agents/` — Anthropic 공식 형식)

Top 10 종목에 대해 정성 모멘텀과 리스크를 자동 생성합니다. 모든 항목 출처 태그 필수.

| 에이전트 | 역할 | 출처 |
|---|---|---|
| `fundamental-analyst` | 사업 모멘텀 (CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS) | `[출처: WebSearch · YYYY-MM]` |
| `risk-analyst` | 리스크 (EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE) | 동일 |
| `synthesizer` | 두 결과 → 카드용 단일 JSON | 출처 태그 절대 제거 금지 |

같은 룰을 **DACON 제출용 표준 6섹션 형식**으로 동기화한 버전이 `skills/agents/`에 있습니다. v1.0에서 입출력 인터페이스 명세(§7.1)와 운영 예외 처리(§8) 추가됨.

---

## 운영 — `/update-data` 슬래시 커맨드

```bash
/update-data            # 시장지수·매트릭스·점수·일별·AI (universe 제외, ~12분)
/update-data --full     # universe 재구축 포함 (~30분)
/update-data --skip-ai  # AI 분석 건너뜀 (정량만, ~10분)
```

자동 실행되는 8단계:

| 단계 | 스크립트 | 출력 |
|---|---|---|
| 1 | `fetch_kr.py` + `fetch_us.py` (병렬) | 시장 지수 시계열 |
| 2 | `fetch_universe.py` 등 (`--full`만) | universe.json |
| 3 | `fetch_matrix.py` | matrix/{per,pbr}_monthly.json |
| 4 | `refresh_universe_prices.py` + `apply_triple_cross.py` | 직전 거래일 종가로 universe.close 갱신 + 4팩터 Top 10 |
| 5 | `fetch_batch.py --top-n 10` | Top 10 일별 풀 데이터 |
| 6 | Agent tool ×10 (병렬) | ai_notes.json |
| 7 | `verify_data.py` | 페치 결과 sanity 검증, 임계값 위반 시 commit 차단 |
| 8 | 완료 보고 | (마크다운 표) |

데이터 갱신은 로컬에서 실행 → commit → push 후 ~30초 만에 GitHub Pages에 자동 반영됩니다.

---

## 데이터 출처

| 데이터 | 출처 | 인증 |
|---|---|---|
| KOSPI/KOSDAQ PER/PBR/배당/종가 | pykrx | KRX_ID/PW (로컬 페치만) |
| Forward PER + 컨센 목표가 | 네이버 Wisereport | 불필요 |
| S&P 500 PER (월별) | multpl + yfinance | 불필요 |
| AI 정성 분석 | Claude Code Agent + WebSearch | 로컬 페치만 |

**API 키 사이트 노출 0, 백엔드 0**. 모든 데이터는 로컬 페치 후 JSON으로 commit되며, GitHub Pages가 정적 파일을 그대로 서빙합니다.

---

## Skills.md 패키지 (`skills/`)

DACON 제출용. 7개 .md + 같은 내용의 PDF 7개로 구성:

| 파일 | 역할 |
|---|---|
| `value_recovery_quant.md` (메인) | 4팩터 Z-Score 가중합산 / 검증 5종 / 룰북 간 인터페이스 / 운영 예외 처리 |
| `forward_attractive.md` (보조) | Forward PER 단독 매력 모델 (단일 팩터 + 신뢰도 페널티) |
| `dividend_value.md` (보조) | 인컴(배당) + 가치 결합, 컨센 의존 0 |
| `agents/fundamental_analyst.md` | 정성 모멘텀 추출 |
| `agents/risk_analyst.md` | 정성 리스크 추출 |
| `agents/synthesizer.md` | 두 정성 분석 통합 |
| `README.md` | 패키지 설명 + Skills.md 메타 명세 (새 룰북 추가 가이드) |

새 룰북 추가 시 `skills/README.md`의 메타 명세(frontmatter 표준: name/version/type/parent_rulebook/output)를 따르면 시스템이 자동 인식합니다.

---

## 사이트 UI

- 헤더: sticky + backdrop blur 14px, `PER · PBR` 모노스페이스 브랜드 마크
- 폰트: Pretendard (SIL OFL) + JetBrains Mono (SIL OFL)
- 색: 모노크롬 베이스 + 한국 시장 색 컨벤션(상승 빨강 / 하락 파랑)
- 검색: 30개/페이지 페이지네이션 (303종목 → 11페이지) + ellipsis
- 모바일: 768px 이하 반응형 (헤더 nav 풀 너비 3등분, 가로 스크롤 0)
- 저작권: 외부 이미지·아이콘 0, 폰트는 모두 OFL

---

## 폴더 구조

```
dacon-skills-dashboard/
├── skills/                        Skills.md 패키지 (제출물)
│   ├── value_recovery_quant.md    ◀ 메인 룰북
│   ├── forward_attractive.md      ◀ 보조 룰북 (Forward 단독)
│   ├── dividend_value.md          ◀ 보조 룰북 (배당+가치)
│   ├── agents/{fundamental,risk}_analyst.md, synthesizer.md
│   └── README.md                  ◀ 패키지 설명 + 메타 명세
│
├── .claude/
│   ├── agents/                    Anthropic 공식 형식 (실행용)
│   └── commands/update-data.md    /update-data 슬래시 커맨드
│
├── scripts/                       Python 페치·점수·검증 파이프라인
│   ├── fetch_kr.py / fetch_us.py
│   ├── fetch_universe.py / validate_universe_quick.py / fetch_consensus.py
│   ├── fetch_matrix.py
│   ├── refresh_universe_prices.py ◀ universe.close 빠른 갱신 (~30초)
│   ├── apply_triple_cross.py      ◀ 4팩터 점수
│   ├── fetch_batch.py             ◀ Top 10 일별 풀
│   └── verify_data.py             ◀ 페치 결과 sanity 검증
│
├── data/                          정적 JSON (commit 후 GitHub Pages 자동 서빙)
│   ├── kospi.json kosdaq.json sp500.json
│   ├── universe.json              universe 303종목 + 컨센
│   ├── matrix/{per,pbr}_monthly.json   60개월 매트릭스
│   ├── screens/triple_cross.json  4팩터 점수 + Top 10
│   ├── screens/ai_notes.json      AI 정성 분석
│   └── stocks/{code}.json         Top 10 일별 풀
│
├── index.html stock.html app.js stock.js style.css   정적 사이트
└── docs/기획서_초안.md / .pdf      DACON 제출용 기획서
```

---

## 제출물 (DACON)

| 제출물 | 위치 |
|---|---|
| 기획서 PDF | `docs/기획서_초안.pdf` |
| Skills.md 패키지 | `skills_submission.zip` (.md 7 + .pdf 7) |
| 배포 URL (필수) | https://hsh2578.github.io/dacon-skills-dashboard/ |
| GitHub 저장소 (선택) | https://github.com/hsh2578/dacon-skills-dashboard |

---

## 평가 5축 매핑

| 평가항목 | 배점 | 본 서비스 적용 |
|---|---|---|
| 범용성 | 25 | Skills.md 표준 6섹션 + 메타 명세(새 룰북 추가 가이드) + 매트릭스 fallback으로 universe 외 종목 PER/PBR 차트 |
| Skills.md 설계 | 25 | 메인 룰북 + 보조 2종 + AI 에이전트 3종 + 검증 5종 / 인터페이스 명세 / 운영 예외 처리 / 3-소스 원칙 |
| 대시보드 자동 생성 | 25 | 알고리즘 6단계 시각화 + 4-View(시장 지수·Top 10·검색·종목 상세) + sticky 헤더 + 모바일 반응형 |
| 바이브코딩 활용 | 15 | `/update-data` 슬래시 커맨드 8단계 + AI 서브에이전트 3종 + 코드 ≈ 100% LLM 생성 |
| 실용성·창의성 | 10 | 본인이 매주 사용하는 도구 + 정량+정성 결합 + 시장 갭 직접 메움 + `verify_data.py`로 stale 차단 |

---

## 라이선스

본 저장소는 출품작이며, 외부 데이터 출처(pykrx, 네이버 Wisereport, multpl, yfinance)의 사용 정책은 각 출처의 라이선스를 따릅니다. 폰트(Pretendard, JetBrains Mono)는 모두 SIL OFL입니다.
