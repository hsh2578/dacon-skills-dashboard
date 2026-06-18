---
description: 시장 지수·universe 매트릭스·Top 10 점수·AI 정성 분석 — 모든 데이터를 오늘 자로 갱신
argument-hint: [--full | --skip-ai]
allowed-tools: Bash, Agent, Read, Write, Glob, Grep
---

# /update-data — 전체 데이터 일일 갱신

당신은 이 명령이 호출되면 다음 워크플로우를 **순서대로** 실행합니다. 각 단계 시작 전에 한 줄 진행 상황을 사용자에게 알리고, 단계 끝나면 결과 한 줄 보고하세요.

## 옵션 처리

호출 인자(`$ARGUMENTS`)에 따라 모드 결정:

- `--full`: 모든 단계 (universe 재구축 포함, ~30분)
- `--skip-ai`: 6번 AI 정성 분석 건너뜀 (정량 데이터만, ~10분)
- 기본 (인자 없음): universe 건너뜀 + 나머지 모두 (~12분)

universe는 종목 마스터·5Y PER 검증·컨센서스로, 거의 변동 없으니 주 1회 정도면 충분. 매일 갱신은 시장 지수·매트릭스·점수·AI만으로 OK.

## 1단계 — 시장 지수 갱신 (~3분)

다음 두 명령을 한 메시지에 **병렬 Bash 호출**:

```bash
python scripts/fetch_kr.py
```
```bash
python scripts/fetch_us.py
```

KOSPI/KOSDAQ 일별 PER/PBR (증분 갱신) + S&P 500 월별 (multpl + yfinance) → `data/kospi.json`, `data/kosdaq.json`, `data/sp500.json`.

## 2단계 — Universe 재구축 (~15분, `--full` 시에만)

`--full`이 아니면 이 단계 **건너뜁니다**. 기존 `data/universe.json` 그대로 사용.

`--full` 호출 시 순차 실행 (각 명령 끝나야 다음):

```bash
python scripts/fetch_universe.py
```
```bash
python scripts/validate_universe_quick.py
```
```bash
python scripts/fetch_consensus.py
```

시총 3,000억+ 보통주 마스터 → 5Y PER 검증 (적자분기 ≤ 4Q) → Naver Wisereport 컨센서스 (Forward + 목표가). 결과: `data/universe.json` 갱신, 통과 종목 ~303개.

## 3단계 — PER/PBR 매트릭스 갱신 (~3분)

```bash
python scripts/fetch_matrix.py
```

universe 전체 종목의 월별 PER/PBR 60개월 매트릭스 → `data/matrix/per_monthly.json`, `data/matrix/pbr_monthly.json`. 종목 검색 페이지의 PER/PBR 차트가 이 데이터로 그려짐.

## 4단계 — Top 10 점수 추출 (~30초)

먼저 `universe.json`의 close 필드를 직전 거래일 종가로 갱신합니다. `--full` 모드가 아닐 때 universe.json은 변경되지 않지만, 그 안의 close 필드는 `apply_triple_cross.py`가 사용하므로 stale되면 Top 10의 가격·upside가 옛 값이 됩니다. 가벼운 시장 일괄 호출(2회)로 30초 안에 갱신.

```bash
python scripts/refresh_universe_prices.py
python scripts/apply_triple_cross.py
```

4팩터 (s1_per / s1_pbr / s3_per / upside) Z-Score 정규화 → 그룹 합산 → 가중 합산 (Value 60% + Growth 40%) → Top 10. 결과: `data/screens/triple_cross.json`.

## 5단계 — Top 10 일별 풀 페치 (~3분)

```bash
python scripts/fetch_batch.py --from-screen triple_cross --top-n 10
```

상세페이지에 PER/PBR 차트뿐 아니라 시가총액·주가까지 보여주기 위해 Top 10 종목만 일별 풀 데이터 페치. 결과: `data/stocks/{code}.json` 10개 + `data/stocks/_index.json`.

## 5.5단계 — Top 10 재무 추이 페치 (DART, ~30초)

```bash
python scripts/fetch_financials.py
```

OpenDART 공식 API로 Top 10 종목의 매출·영업이익·순이익 5~6년 추이 + 마진을 페치. "싼 게 정당한가(이익 무너지는 중 = 구조적 함정)/일시적인가(이익 멀쩡 = 기회)"의 **데이터 근거**가 되어 6단계 AI 정성·ranker Value Trap 판별을 뒷받침한다. 결과: `data/financials/{code}.json` 10개 + `data/financials/_index.json` (+ 최초 1회 `_dart_corpmap.json` 캐시 생성). `.env`의 `DART_API_KEY` 필요.

## 6단계 — AI 정성 분석 (~2분, `--skip-ai` 시 건너뜀)

`--skip-ai` 호출 시 이 단계 **건너뜁니다**.

이 단계는 bash가 아니라 **Agent 도구로 직접 호출**합니다. 다음 절차:

### 6-1. Top 10 컨텍스트 추출

`data/screens/triple_cross.json` 읽고 `top` 배열에서 10개 종목 컨텍스트 구성. 각 종목에서 다음 필드만 추출:

```json
{
  "name": "...", "code": "...", "rank": N, "tier": "...",
  "valuation": { "current_per": ..., "avg_5y_per": ..., "current_pbr": ..., "avg_5y_pbr": ..., "forward_per": ..., "fwd_year": "...", "avg_target_price": ..., "broker_count": ... },
  "factors": { "s1_per_raw": ..., "s1_per_z": ..., "s1_pbr_raw": ..., "s1_pbr_z": ..., "s3_per_raw": ..., "s3_per_z": ..., "upside_raw": ..., "upside_z": ... },
  "scores": { "value_score": ..., "growth_score": ..., "total_score": ... }
}
```

### 6-2. Agent 도구로 10개 병렬 발사

**한 메시지에 10개 Agent tool call**을 동시에 보냅니다 (subagent_type=`general-purpose`). 각 종목 prompt 템플릿:

```
Triple Cross Top 10 종목의 ai_notes JSON을 정성 위주로 작성합니다.

먼저 다음 3개 .claude/agents/ 정의 파일을 Read로 정독하고 룰을 그대로 따르세요:
- C:/Users/hsh/Desktop/vibecoding/dacon-skills-dashboard/.claude/agents/fundamental-analyst.md
- C:/Users/hsh/Desktop/vibecoding/dacon-skills-dashboard/.claude/agents/risk-analyst.md
- C:/Users/hsh/Desktop/vibecoding/dacon-skills-dashboard/.claude/agents/synthesizer.md

WebSearch 3-5회로 종목의 최근 분기 ~ 6개월 이내 모멘텀(컴백·신작·신제품·M&A·정책·실적·가이던스)과 리스크(가이던스 하향·실행 지연·소송·경쟁)를 다각도 조사하세요.

종목 컨텍스트:
{종목 JSON 인라인}

규칙:
- investment_points 4-5개 (정성 3-4 + 정량 종합 시그널 0-1, 정량 마지막)
- risks 3-4개 (정성 2-3 + 정량 0-1, 정량 마지막)
- 정성 항목 모두 [출처: WebSearch · YYYY-MM] 또는 확인 필요 태그
- 정량 항목 [정량] 태그
- WebSearch 결과만 인용, 일반 추측 금지
- 퀀트 리서치 리포트체

출력: 마지막 메시지에 ```json ... ``` 코드 블록 하나, synthesizer.md 출력 스키마 (code + ai_notes 객체). 코드 블록 외 텍스트 금지.
```

### 6-3. 결과 합쳐서 저장

10개 에이전트 결과에서 각각 JSON 코드 블록 파싱 → 단일 객체로 병합:

```json
{
  "meta": {
    "generated_at": "<현재 ISO8601>",
    "model": "claude-sonnet-4-6",
    "rule_files": [".claude/agents/fundamental-analyst.md", ".claude/agents/risk-analyst.md", ".claude/agents/synthesizer.md"],
    "stocks_analyzed": 10,
    "note": "정성 위주 분석 (투자포인트 4-5개 + 리스크 3-4개). 모든 정성 항목 WebSearch 출처 태그 필수. 정량 점수에는 영향 없음."
  },
  "items": [
    { "code": "...", "ai_notes": { ... } },
    ...
  ]
}
```

`Write` 도구로 `data/screens/ai_notes.json`에 저장.

## 7단계 — 데이터 검증 (sanity check)

```bash
python scripts/verify_data.py
```

페치된 데이터의 누락·stale 비율을 자동 체크. 임계값 초과 시 exit 1로 종료해서 후속 commit/push가 자동 차단됩니다. 시장 지수 fresh, universe.close 무효 비율, 매트릭스 coverage, Top 10 current_price, ai_notes 항목 수를 점검.

## 8단계 — 완료 보고

다음 항목을 사용자에게 마크다운 표로 보고:

| 단계 | 결과 |
|---|---|
| 시장 지수 (KOSPI/KOSDAQ/S&P 500) | 갱신 ✓ |
| Universe (`--full` 시) | 갱신 ✓ 또는 건너뜀 |
| 매트릭스 PER/PBR | N개 종목, 60개월 |
| Top 10 점수 | 1위 {name}({code}) Z={total} |
| Top 10 일별 풀 데이터 | 10/10 |
| AI 정성 분석 | 갱신 ✓ 또는 건너뜀 |

브라우저 캐시는 자동 무효화됩니다 (사이트가 fetch 시 `?t=Date.now()`로 강제 새로고침). 사용자는 페이지 새로고침만 하면 새 데이터 표시.

## 실패 처리

- 어떤 단계라도 실패하면 즉시 사용자에게 알리고 멈춥니다 (다음 단계가 이전 단계 데이터에 의존하므로)
- KRX 인증 실패 (KRX_ID/KRX_PW 미설정) → `.env` 확인 안내
- WebSearch 결과 부족 → 그 종목은 정성 항목 적게 반환 (룰에 명시됨)
- Naver 차단 → fetch_consensus.py가 ThreadPool 3 + sleep으로 회피하지만, 추가 차단 시 `time.sleep(60)` 후 재시도

## 시간 비용 요약

| 모드 | 단계 | 예상 시간 |
|---|---|---|
| 기본 | 1·3·4·5·6 | ~12-13분 (4단계에 refresh_universe_prices 30초 추가) |
| `--full` | 1·2·3·4·5·6 | ~30분 (2단계에 가격 갱신 포함되므로 4단계의 refresh 생략 가능) |
| `--skip-ai` | 1·3·4·5 | ~10-11분 |
