---
description: 시장 지수·universe·매트릭스·Top 20 점수·AI 정성 분석 — 모든 데이터를 오늘 자로 갱신
argument-hint: [--full | --skip-ai]
allowed-tools: Bash, Agent, Read, Write, Glob, Grep
---

# /update-data — 전체 데이터 갱신

이 명령이 호출되면 아래 워크플로우를 **순서대로** 실행합니다. 각 단계 시작 전에 한 줄 알리고, 끝나면 결과 한 줄 보고하세요.

> **폐기된 스크립트를 절대 호출하지 마세요.** `fetch_universe.py` · `validate_universe_quick.py` ·
> `fetch_matrix.py` · `fetch_batch.py` · `refresh_universe_prices.py` · `fetch_stock_kr.py` 는
> pykrx(data.krx.co.kr 스크래핑) 기반이라 2026-08-13 KRX IP 차단을 유발했고 삭제됐습니다.
> 아래 `*_api` / `*_kis` 계열만 사용합니다.

## 옵션

- `--full` : universe 재구축까지 전부 (~25분)
- `--skip-ai` : AI 정성 분석 건너뜀 (정량만, ~10분)
- 기본 : universe 재구축 건너뜀 + 나머지 전부 (~15분)

universe(종목 마스터·5Y 검증·컨센서스)는 변동이 느려 주 1회면 충분합니다.

## 1단계 — 시장 지수 (~3분)

두 명령을 한 메시지에 **병렬 Bash 호출**:

```bash
python scripts/fetch_kr.py
```
```bash
python scripts/fetch_us.py
```

`fetch_kr.py`는 KOSPI/KOSDAQ **지수** PER/PBR용으로 아직 pykrx를 씁니다 — 대체재가 없는 유일한 잔존 의존입니다. 종목 단위 대량 조회가 아니라 지수 2건 요청이라 차단 위험이 낮습니다. 실패하면 그대로 보고하고 나머지 단계는 계속 진행하세요(Section 1만 stale해집니다).

## 2단계 — universe 재구축 (`--full` 시에만, ~5분)

`--full`이 아니면 **건너뜁니다**. 기존 `data/universe.json`을 그대로 씁니다.

순차 실행 (각 명령이 끝나야 다음):

```bash
python scripts/fetch_universe_api.py
```
```bash
python scripts/validate_universe_api.py
```
```bash
python scripts/fetch_consensus.py
```

시총 2,000억+ 보통주(KRX 공식 API) → 5Y 실적 검증(KIS 분기 EPS, 적자분기 ≤ 4Q) → 네이버 컨센서스(Forward PER·목표주가). 결과 ~300종목.

`validate_universe_api.py`는 KIS 캐시를 읽으므로 **3단계보다 먼저 돌면 캐시가 비어 실패**할 수 있습니다. 최초 실행이거나 캐시가 없으면 3단계를 먼저 돌리고 2단계로 돌아오세요.

## 3단계 — PER/PBR 매트릭스 (~3분, 최초 ~20분)

```bash
python scripts/fetch_matrix_kis.py --months 60 --daily --all --replace
```

KRX 공식 API 일별 종가 → 월평균(최신 달만 최신 종가) + KIS 분기 EPS/BPS로 **TTM** PER/PBR 산출. 수정주가 보정 포함. 결과: `data/matrix/{per,pbr}_monthly.json`.

- `--daily` 최초 1회는 1,300거래일 수집으로 ~15분. 이후 캐시 증분이라 수십 초.
- `--all` 전 종목(검색 페이지 fallback). universe만 필요하면 생략 가능.
- `--replace` 정식 경로에 기록. 빼면 `*_ttm.json`으로 나갑니다.
- 캐시는 `data/.cache/` (gitignore, API 토큰 포함 — **절대 커밋 금지**).

## 4단계 — Top 20 점수 (~30초)

```bash
python scripts/apply_triple_cross.py
```

4팩터(s1_per·s1_pbr·s3_per·upside) Z-Score → 그룹 합산 → 가중합(Value 60 + Growth 40) → 상위 `TOP_N`(현재 20). 결과: `data/screens/triple_cross.json`.

## 5단계 — Top 20 일별 풀 + 재무 (~2분)

```bash
python scripts/fetch_batch_api.py --top-n 20
```
```bash
python scripts/fetch_financials.py
```

앞 단계 캐시를 재사용하므로 KRX 신규 호출이 없습니다(네이버 컨센서스만 종목당 1회). 재무는 OpenDART.

> **universe 전체 재무**: `python scripts/fetch_financials.py --universe`를 가끔(주 1회) 따로 실행해야 검색→상세에서 Top 20 밖 종목도 재무 추이 섹션이 보입니다.

## 6단계 — AI 정성 분석 (`--skip-ai` 시 건너뜀, ~10분)

Agent 도구로 직접 호출합니다.

### 6-1. 컨텍스트 추출

`data/screens/triple_cross.json`의 `top` 배열에서 종목별로 다음을 뽑아 `data/screens/_top20_context.json`에 저장:

```json
{"name","code","rank","tier","market_cap_억",
 "valuation":{"current_price","current_per","avg_5y_per","current_pbr","avg_5y_pbr","forward_per","fwd_year","avg_target_price","broker_count"},
 "factors":{"s1_per_raw","s1_per_z","s1_pbr_raw","s1_pbr_z","s3_per_raw","s3_per_z","upside_raw","upside_z"},
 "scores":{"value_score","growth_score","total_score"}}
```

### 6-2. 종목별 Agent 병렬 발사

**한 메시지에 최대 10개씩**, `subagent_type=general-purpose`. 프롬프트:

```
Triple Cross Top 20 중 **{종목명}({코드})** 의 ai_notes JSON을 작성합니다.

룰 파일 3개를 Read로 정독하고 그대로 따르세요:
- .claude/agents/fundamental-analyst.md
- .claude/agents/risk-analyst.md
- .claude/agents/synthesizer.md

데이터:
- 정량: data/screens/_top20_context.json 의 code="{코드}"
- 재무(DART): data/financials/{코드}.json

**undervaluation_cause.text 규격: 180~260자(2~3문장), 상한 320자.**
(1) 시장이 싸게 보는 직접 원인 (2) 재무 궤적이 뒷받침/반박하는지 (3) 해소 조건.
영업이익률·매출 추세 숫자 필수 인용.

PER/PBR은 TTM(최근 4개 분기) 기준입니다. WebSearch 3-5회로 최근 분기~6개월
모멘텀·리스크를 조사하세요.

규칙: investment_points 4-5개 · risks 3-4개 · 정성 항목 전부
`[출처: WebSearch · YYYY-MM]` 또는 `확인 필요` 태그 · 정량 `[정량]` ·
퀀트 리포트체 · 이모지 금지.

출력: ```json ... ``` 코드 블록 하나만 (code + ai_notes). 코드 블록 외 텍스트 금지.
```

종목별 특이사항(5년 평균 PER이 비정상적으로 높음, Forward PER > 현재 PER, 상장 이력 짧음 등)은 프롬프트에 명시해 에이전트가 검증하도록 하세요.

### 6-3. 병합 후 ranker 재순위

결과를 `data/screens/ai_notes.json`에 병합(`{meta, items:[{code, name, quant_rank, ai_notes}]}`)한 뒤, `ranker` 룰로 Agent 1개를 돌려 `ai_rank`/`rerank_reason`을 산출하고 items를 `ai_rank` 순으로 정렬합니다.

ranker 프롬프트에 반드시 포함할 것:
- `.claude/agents/ranker.md` 정독
- 입력: `ai_notes.json` · `_top20_context.json` · `data/financials/{code}.json`
- **nature(§4.3)를 1차 축으로 쓰되 그룹 내부 순서와 경계는 촉매 임박도(§4.1)·피크 어닝스(§4.2.1)·절대 밸류(§4.5)가 결정하도록** 지시. 과거 실행에서 ai_rank가 nature와 100% 일치해 §4.3이 다른 룰을 압도한 적이 있습니다.
- 새 사실 생성 금지, 4팩터 점수 변경 금지

## 7단계 — 검증

두 검사를 모두 돌립니다. 보는 것이 다릅니다.

```bash
python scripts/verify_data.py
```
```bash
python scripts/check_golden_matrix.py
```

- `verify_data.py` — 산출물의 **신선도·커버리지**. 임계값 위반 시 exit 1.
- `check_golden_matrix.py` — 동결된 30종목 기준선과 대조해 **과거 값이 바뀌었는지**. 과거 PER/PBR은 원칙적으로 불변이므로(원주가 저장 + 사용 시점 보정), 변동은 회귀 신호입니다. `verify_data.py`는 PBR이 154배여도 통과시키므로 이 검사가 그 구멍을 막습니다.

골든이 위반을 보고하면 **먼저 원인을 확인하세요.** 분할·증자로 전 구간이 균일하게 움직인 경우는 "참고"로 분류되어 통과합니다. 특정 구간만 튀면 회귀입니다.
의도한 변경임이 확인되면 `python scripts/check_golden_matrix.py --freeze`로 기준선을 다시 동결합니다.

정식 파일을 덮어쓰기 전에 후보를 먼저 검사하려면 3단계를 `--replace` 없이 돌린 뒤
`python scripts/check_golden_matrix.py --suffix _ttm`으로 확인하고, 통과하면 승격하세요.

단위 테스트도 함께 돌릴 것 (TTM 판정 로직 — 네트워크 불필요, 1초):

```bash
python -m pytest tests/ -q
```

## 8단계 — 완료 보고

마크다운 표로 보고: 시장 지수 · universe(수) · 매트릭스(종목수) · Top 20 1위 · 일별 풀 · 재무 · AI 분석 · 검증 결과.

브라우저 캐시는 사이트가 `?t=Date.now()`로 버스팅하므로 새로고침만 하면 반영됩니다.

## 실패 처리

- 단계 실패 시 즉시 보고하고 멈춥니다(후속 단계가 앞 결과에 의존).
- 단, **1단계 `fetch_kr.py` 실패는 예외** — 지수만 stale해지므로 보고 후 계속 진행.
- KRX 공식 API 실패 → `.env`의 `KRX_API_KEY` 확인.
- KIS 토큰 403 → 토큰 재발급은 분당 제한이 있습니다. `data/.cache/_kis_token_real.json`이 24h 캐시되므로 잠시 후 재시도.
- DART `ConnectionReset` → 과호출 신호. 순차·저속으로만 재시도하세요.
- 네이버 차단 → `fetch_consensus.py`가 ThreadPool 3 + sleep으로 회피하지만, 추가 차단 시 60초 대기 후 재시도.

## 시간 요약

| 모드 | 단계 | 예상 |
|---|---|---|
| 기본 | 1·3·4·5·6·7 | ~15분 |
| `--full` | 전체 | ~25분 |
| `--skip-ai` | 1·3·4·5·7 | ~8분 |
