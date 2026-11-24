# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**PER · PBR Lens** — 한국 주식 저평가 스크리너 + AI 매수 매력 순위. 사용자 본인의 **실투자 판단 도구**(2026-11~, 월 1회 갱신).
원래 DACON 월간 해커톤 1등 수상작(2026-05)이었다 — 대회 제약(챗봇 금지·Skills.md 제출물·평가 점수)은 더 이상 기준이 아니다.
대회 시절 구조·제출물 빌드법(`skills/`, `docs/기획서_초안`)은 git 이력에 있다 (`git log -- CLAUDE.md`, 2026-11-24 이전 판).

## 사용자의 투자 논리 (설계의 중심 — 바꾸지 말 것)
1. **저평가 = 자기 과거 대비 싸다** — Top 30 선별은 정량 3팩터(PER 할인 · PBR 할인 · 전망). 선별 기준을 바꾸려면 먼저 물을 것.
2. **"높은 밸류를 받던 종목은 이유가 있다. 그 이유가 사라지지 않으면 과거 밸류로 회복한다."** — 매수 매력 순위의 재평가 항.
3. 정량으로 후보를 추리고 **AI 가 애널리스트처럼 그중 살 종목을 고른다**. AI 는 판정만, 점수는 코드 (같은 판정 = 같은 순위).
4. 판단 기준은 백테스트 수치가 아니라 **논리의 일관성**. 한국 시장 맥락 — 미국 대가 이론을 그대로 옮기지 않는다. 비평은 grill-me 스킬로.
5. 수익률·적중률은 코드로 확인한 값만 단정한다. 백테스트는 방향 확인용.

## 데이터 (전부 로컬 수집 → JSON → GitHub Pages 정적 사이트)
| 데이터 | 출처 | 스크립트 · 저장 |
|---|---|---|
| 일별 시가총액·종가 (우선주 포함) | KRX 공식 OpenAPI | `fetch_mcap_daily.py` → `data/.cache/_krx_{mcap,close}_daily.json` (2020-12~) |
| 분기 재무 2015~ (지배·전체 순이익, 자본, 매출, 영업이익, 영업CF, 설비투자, 자산, 금융비용·수익, 배당, 자사주 매입) | **DART 원본** — dartlab HuggingFace 미러(CC BY 4.0) 우선, 빈 곳만 OpenDART. 2019 이전 공시는 옛 `ifrs_` 태그 | `fetch_dart_quarterly.py` → `data/financials_q/{code}.json` (로컬 전용). 추출 규칙을 바꾸면 `--reextract --no-api --shard i/6` 6개 병렬(수 분) |
| 연간 EPS 실적·추정 (FY-2~FY+2) 월별 스냅샷 | 네이버 Wisereport | `fetch_eps_annual.py` → `data/consensus/` (로컬) |
| 목표가 (표시용, 점수 미사용) | 네이버 컨센서스 (요약표가 비면 증권사별 92일 평균) | `fetch_consensus.py` · `naver_consensus.py` |
| AI 자료 묶음: DART 주요사항 1년 · 증권사 리포트 1년(40건) · 뉴스 1년(네이버증권 종목 피드 + 검색 API, 월 12건) · 텔레그램 1년 · 추정치 변화 | DART · 네이버 · 모의투자대회 `catalyst_engine.grounding` · 리서치에이전트 `fnguide_data` | `build_research_pack.py` → `data/research/{code}.json` (**공개 금지** — 텔레그램 원문) |
| 메자닌(CB·BW·EB) 발행결정 5년 | OpenDART 주요사항 API | `fetch_mezzanine.py` → `data/mezzanine.json` |
| 지수 PER/PBR/배당 | KRX 정보데이터시스템 로그인(pykrx) — 유일한 잔존 의존 | `fetch_kr.py` (비밀번호 만료 시 data.krx.co.kr 에서 변경 → 마스터 `Desktop/.env` `KRX_PW` → `sync_env.py --apply`) |

API 키는 마스터 `C:/Users/hsh/Desktop/.env` 를 `feeds.load_env` 가 읽는다. 새로 발급하지 말 것.

## 계산
- **PER = (보통주+우선주 시총) ÷ TTM 지배주주 순이익 · PBR = 시총 ÷ 최근 분기 지배자본** (`build_valuation.py`). 주당 값을 안 써서 분할에 안전. 외화 공시 종목 제외. 공시 시차(분기 45일·사업보고서 90일)는 `ttm.py` 가 유일한 소유자 — 복제 금지.
- **권리락~신주 상장 사이 KRX 시총 과소**(무상증자·분할, 1년 약 40건)는 `build_valuation.fix_listing_lag` 가 보정.
- KRX·네이버 PER 과 다르다(그쪽은 직전 연간 기준, 연 1회 갱신) — 의도된 차이.
- 일별 → `data/.cache/daily/`(전 종목) · 월별 매트릭스 → `data/matrix/{per,pbr}_monthly.json` · 검색 대상 일별 사본 → `data/daily/`.

## 선별 — 정량 Top 30 (`apply_triple_cross.py`)
- 유니버스: 시총 2,000억+ 보통주 → 최근 20분기 TTM 적자 ≤4 → **내년(FY+1) 컨센서스 EPS 보유**(없으면 제외 — 사용자 결정).
- 점수 = ⅓ PER 할인 + ⅓ PBR 할인 + ⅓ 전망 (순위→Z). 할인 = 1 − 현재 ÷ 5년 중앙(최소 24개월). 전망 = 1 − Forward PER ÷ 5년 PER 중앙, Forward = avg(FY+1, FY+2) (FY+2 없으면 FY+1).
- 퀄리티 필터(`quality.py`, 점수 아님): 이익률 추세·이익의 질·이자보상 하위 20% 는 Top 자격 없음. TOP_N = 30.
- 에이전트 입력 `_top_context.json`: valuation · expectations · quality · price(시총 비례 수정주가) · **buy_inputs**(상대 PER 이력 원값·이익률 환산값, 이익률 평소/최근/지금).

## AI 단계 (`.claude/agents/`, `/update-data` 2단계)
종목당 에이전트 하나가 순서대로: `fundamental-analyst`(원인 진단·cause_type) → `risk-analyst` → `resolution-scout`(원인이 풀리는가·expectation_gap, 사실이 바뀔 때만 판정 변경) → `synthesizer` → **`buy-check`**(과거 밸류의 이유: 해자 4유형/업황/테마/구조적 할인 → 유효·약해짐·사라짐 · 이익률이 구조적인가 · 한국 함정 점검 · 매수 이유 · 날카로운 질문) → **`briefer`**(사람이 읽는 해설, buy-check 판정·순위 계산과 같은 말).
- 자료 묶음을 먼저 읽고 WebSearch 는 보충. 출처 태그(`[출처: …]`/`[정량]`/`확인 필요`) 필수, 이모지 금지.
- **재분석 대상만** (`ai_stage.py targets`): 신규 진입·새 공시/리포트·추정치 ±5%(직전 분석 20일 이상일 때). 나머지는 재사용 — 같은 분석의 작업 파일은 덮어쓰지 않는다.
- `ranker.md` 는 폐기(돌릴 때마다 해석이 달라 순위가 흔들렸다) — 이력용.

## 매수 매력 순위 (`scripts/value_core.py` + `scripts/rank_ai.py`)
**(주주이익 수익률 + 재평가 수익) × 확실성**. 설계·비평 이력: `docs/superpowers/specs/2026-11-24-buy-ranking-design.md` (grill-me 3회 + 브리핑 대조).
- **재평가**: 목표 PER = 자기 '상대 PER'(종목 ÷ 유니버스 중앙, 매달 그때 이익률 → 지금 쓰는 이익률로 환산한 5년 중앙) × 지금 시장 PER. buy-check premium: 유효 = 과거 배수 · 약해짐 = 과거와 시장의 기하평균 · 사라짐 = 시장. 업황·테마 프리미엄은 회복 불인정 · 할인 종목(또는 AI 가 '구조적 할인'으로 분류)은 '사라짐' 확인 시에만 시장 수준 · 이력 없으면 시장 배수. 근거 있으면 3년, 아니면 5년 회복, ±30%/년 상한.
- **주주이익**: 이익률 = 구조적(AI)이면 최근 8분기 · 지금 ≥ 평소면 평소와 (평소·최근·지금 중앙)의 중간 · 낮아졌으면 회복 근거 있을 때 평소, 없으면 중앙 (계단 없음). 함정 때문에 '구조적'을 무효로 하면 최근 8분기보다 낙관적이 되지 않게. min(영업 기준 × 이익 전환율 × 지배 몫, 순이익 기준) — 일회성·이자·비지배 제외. 일회성 이익 표시면 재평가도 이 보수적 이익으로.
- **확실성**: 좋은 사업 6관문(최근 5년: ROE≥8% · OCF/NI≥0.7 · 이자보상≥2 · 순이익률≥5% · FCF 적자 연도≤2 · 희석≤20%, 자료 없음=통과) × 배당성향<10% ×0.9 × 함정(SEVERE ×0.3, WATCH 는 플래그마다 곱, 하한 0.7) × 메자닌 오버행(전환가 근처 ≥5% ×0.9 · ≥15% ×0.8) × 정보량 C ×0.9. 기대 수익이 음수면 × (2 − 확실성).
- **순현금은 넣지 않는다** — PER(순이익) 기준이라 이자수익·비용이 이미 반영, 한국 기업 현금은 주주에게 잘 안 돌아와 시장도 할인(배당성향 계수 몫), 차입금 태그가 회사마다 달라 30종목 중 24개만 정확(2026-11-24 확인).
- 판단 기록·채점: `judgments.py record/grade` → `data/judgments/`. **AI·순위 효과는 이 사후 채점으로만 검증 가능**.

## 실행
```bash
python scripts/update_all.py           # 정량 전부 (--from N 으로 이어서). 수집은 전부 이어받기
# → /update-data 문서의 AI 단계 → ai_stage.py merge → rank_ai.py → ai_stage.py apply-rank → ai_stage.py briefs → judgments.py grade
python scripts/update_all.py --from 5  # 검증: verify_data(신선도·커버리지·Top/AI 정합) · check_golden_matrix(과거 값 불변) · pytest
python -m http.server 8770             # 로컬 미리보기
```
연구용: `backtest_value.py`(가치·퀄리티, 43개월 — 싼 20% ≈ 시장, 정량은 후보 추리기이지 우위 아님) · `backtest_signals.py`(싼 종목 안 신호: 퀄리티 IC t 3.9 · 이익률 수준 t 2.8 · 더 싼 것 0). 단정 인용 금지.
폐기(부르지 말 것): `fetch_matrix_kis.py`(KIS 404 — 새 매트릭스를 옛 값으로 덮음) · `fetch_batch_api.py` · `fetch_matrix_api.py` · pykrx 종목 스크립트.

## 사이트
- `index.html`/`app.js` — 시장 지수 · Top 30 카드(매수 매력 순위 ↔ 정량 순위 전환, 카드 = 기대 수익·확실성·과거 밸류 판정) · 나머지 종목 검색(765).
- `stock.html`/`stock.js` — 종목 브리핑(맨 위, 옆 칸에 순위 계산식·6관문·메자닌) → AI 분석 원문(접힘) → 재무 추이 → PER/PBR 차트.
- `style.css` 토큰(`--bg/--surface/--text/--kr-up 빨강 상승/--kr-down 파랑 하락`), Pretendard. 이모지 없음. 데스크톱 1440·모바일 390 둘 다 확인.
- 배포: https://github.com/hsh2578/dacon-skills-dashboard → GitHub Pages(master/root), push 후 ~30초. 데이터는 `?t=` 캐시버스터, 정적 파일은 `?v=N`(바꾸면 올릴 것).
- 커밋 금지: `.env*` · `data/.cache/`(API 토큰) · `data/research/` · `data/consensus/` · `data/financials_q/` · `data/screens/_*`. `.gitignore` 인라인 주석 금지(패턴이 깨진다).

## 규칙
- Windows + Python 한글: `os.environ.setdefault("PYTHONUTF8", "1")` + `sys.stdout.reconfigure(encoding="utf-8")`.
- 커밋·배포는 사용자 요청 시. git config 미설정 — `GIT_AUTHOR_NAME="hsh2578" GIT_AUTHOR_EMAIL=… GIT_COMMITTER_…` 환경변수로.
- 파일명 `triple_cross.json` 등은 옛 컨셉 잔재 — 호환성 때문에 유지.
- 새 외부 소스를 붙일 때 물을 것: **"이 소스가 조용히 빈 값을 주면 무슨 일이 생기나?"** — 승계·가드·기록 거부.

## 실제로 난 사고 (재발 방지)
KIS 404 를 삼켜 옛 캐시로 남음 · KRX 당일 빈 응답을 휴장일로 캐시 · 대형주 공시 50건 상한 · 외화 공시 PBR 930배 · 지배 태그 없는 회사(유한양행) · `triple_cross.json` NaN 으로 Top 목록 소실 · 네이버 요약표 스로틀로 목표가 90% 소실 · 권리락 시총 과소(코나아이) · 원주가로 '고점 대비' 과장(분할) · 뉴스 '90일'이 실제 일주일 · targets 가 병합 전 브리핑 10개 덮어씀 · 금융비용에 외환·파생 손실(HD현대 −) · 옛 `ifrs_` 태그 미인식(2019 이전 누락) · AI 가 본 상대 PER(원값)과 순위 계산(환산값)이 달라 할인/프리미엄이 뒤집힘(한국화장품제조).
공통 교훈: **실패를 빈 값으로 굳히지 말 것.** 숫자가 이상하면 계산식보다 데이터부터 의심한다.
