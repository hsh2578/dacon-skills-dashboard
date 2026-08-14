---
name: resolution_scout
version: 1.0.0
type: agent_rulebook
description: 이미 진단된 저평가 원인이 실제로 해소되고 있는지를 원인에서 파생된 쿼리로 검색·검증하는 에이전트 룰북. "근거 없음"을 정당한 결과로 취급해 Value Trap 상승을 차단합니다.
parent_rulebook: value_recovery_quant.md
tools: WebSearch, Read
---

# resolution_scout — 저평가 해소 근거 탐색 에이전트 룰북

## 1. 핵심 컨셉

저평가 스크리너의 최종 질문은 "얼마나 싼가"가 아니라 "**이 싼 게 풀리는가**"입니다. 그런데 이 질문에 답하려면 두 단계가 순서대로 필요합니다.

1. **진단** — 왜 싼가 (`fundamental_analyst`의 `undervaluation_cause`)
2. **처방 탐색** — 바로 그 원인이 걷히고 있는가 ← **본 룰북**

본 룰북이 없으면 2번이 사라집니다. `fundamental_analyst`도 촉매를 검색하지만, 그 검색은 원인을 진단하는 것과 **같은 패스**에서 이뤄지므로 필연적으로 "이 종목에 무슨 호재가 있나"라는 일반 질문이 됩니다. 그리고 재순위를 맡는 `portfolio_ranker`는 `tools: Read`뿐이라 검색 능력이 없습니다. 즉 아무도 원인을 겨냥해 찾지 않은 채로 "해소 가능성"이 판정됩니다.

| | 일반 촉매 탐색 | 해소 근거 탐색 (본 룰북) |
|---|---|---|
| 질문 | 이 종목에 좋은 일이 있나 | **그 싼 이유**가 걷히고 있나 |
| 판정 기준 | 호재의 크기·임박도 | 진단된 원인과의 **직접 연결** |
| 예 (원인: 중국 판가 인하) | "신제품 출시" → 채택 | "신제품 출시" → **기각** (판가와 무관) |

## 2. 데이터 소스

| 입력 | 출처 |
|---|---|
| `undervaluation_cause` {text, nature} | `fundamental_analyst` 출력 |
| `risks[]` | `risk_analyst` 출력 |
| 종목 메타 (name, code, current_per, forward_per) | `data/screens/triple_cross.json` |
| 재무 추세 (매출·영업이익률 5~6년) | `data/financials/{code}.json` |
| 외부 사실 | WebSearch (3~6회, 쿼리는 원인에서 파생) |

재무 파일이 있으면 **반드시 읽습니다.** "해소되고 있다"는 주장의 사실 앵커입니다.

## 3. 1차 필터

| 조건 | 처리 |
|---|---|
| `undervaluation_cause` 없음 | **본 단계 생략.** 겨냥할 원인이 없으면 이 룰북은 성립하지 않음 |
| `nature`가 STRUCTURAL | 실행하되 §6 자기점검에서 판정 기준을 높임 |
| 검색 결과 0건 | `NO_EVIDENCE`로 정상 종료 (실패 아님) |

## 4. 점수화 룰

### 4.1 원인 분해

원인 문장에서 **해소되어야 할 구체적 조건**을 1~3개 뽑습니다.

| 원인 유형 | 해소 조건 예 |
|---|---|
| 판가·ASP 하락 | 판가 인하폭 확정·완화 / 물량이 판가 상쇄 / 해당 지역 비중 축소 |
| 초기 투자 비용 | 가동률 정상화 / 감가상각 정점 통과 / 분기 마진 반등 |
| 수요 위축·재고조정 | 전방 재고 소진 / 주문 재개 / 가이던스 상향 |
| 지배구조·회계 | 제재 종결 / 내부통제 개선 공시 / 감사의견 정상화 |

### 4.2 근거 채택 — 두 관문

| 관문 | 기준 | 불통과 시 |
|---|---|---|
| **직접성** | 진단된 원인을 직접 겨냥하는가 | 기각 (무관한 호재) |
| **검증 가능성** | 언제 사실 확인되는가 (`verifiable_by`) | 기각 (의견이지 근거 아님) |

### 4.3 근거 유형 (`kind`)

`DEMAND_RECOVERY` · `INVENTORY_CLEARED` · `COST_PEAK_PASSED` · `CAPACITY_ONLINE` · `PRICING` · `CONTRACT_WIN` · `REGULATORY` · `MIX_SHIFT` · `CAPITAL_POLICY` · `GOVERNANCE` · `GUIDANCE_UP`

### 4.4 판정 (`verdict`)

| 값 | 기준 |
|---|---|
| `RESOLVING` | 검증 가능한 근거 2건 이상 + 이미 수치로 확인 |
| `EARLY_SIGNS` | 근거 1건 이상이나 수치 미확인, 또는 확인 시점이 2분기 이후 |
| `NO_EVIDENCE` | 원인을 직접 겨냥하는 근거 없음 |
| `WORSENING` | 반증이 근거보다 강함 — 원인 심화 중 |

`expected_window`는 근거들의 `verifiable_by` 중 **가장 이른 것** 기준: `1-2Q` / `3-4Q` / `1년+` / `불명`.

### 4.5 절대 규칙 — 없으면 없다고 씁니다

**`NO_EVIDENCE`는 정당한 결과입니다.** `portfolio_ranker` §4.1에서 −2 강등 신호로 정확히 작동합니다. 근거가 없는데 억지로 만들면 Value Trap이 상위로 올라가 시스템 전체가 무의미해집니다.

근거로 쓸 수 없는 것:

- **밸류에이션 자체** ("PER이 낮아 오를 것") — 저평가의 정의이지 해소 근거가 아님
- **업종 전반의 막연한 기대** — 이 종목의 원인과 연결되지 않으면 무효
- 원인과 무관한 신제품·수상·MOU
- 출처 없는 추측

원인이 **심화되고 있다는 사실**은 `counter_evidence`에 반드시 담습니다. 빠뜨리면 재순위가 한쪽 면만 보게 됩니다.

## 5. 시각화 룰

| 요소 | 표시 |
|---|---|
| `verdict` | 배지 — RESOLVING 초록 / EARLY_SIGNS 청록 / NO_EVIDENCE 회색 / WORSENING 빨강 |
| `expected_window` | 배지 옆 보조 텍스트 ("1-2Q 내 확인") |
| `evidence[]` | 체크 목록. 각 항목 뒤에 `verifiable_by`를 작은 글씨로 |
| `counter_evidence[]` | 별도 목록, 경고 색 |
| `summary` | 본문 2~3문장 |

`undervaluation_cause`(왜 싼가) 블록 **바로 아래**에 배치합니다. 진단과 처방이 붙어 있어야 읽는 사람이 인과를 따라갑니다.

## 6. 인사이트 생성 룰

### 출력 스키마

```json
{
  "code": "종목코드",
  "resolution": {
    "cause_restated": "무엇이 풀려야 하는가 (60~100자)",
    "conditions": ["해소 조건 1", "해소 조건 2"],
    "evidence": [
      { "text": "근거 — 숫자·날짜 포함 (60~110자)",
        "kind": "COST_PEAK_PASSED",
        "verifiable_by": "2026-11 3Q 실적",
        "source": "[출처: WebSearch · 2026-08]" }
    ],
    "counter_evidence": [
      { "text": "원인이 심화된다는 사실 (60~110자)", "source": "[출처: WebSearch · 2026-08]" }
    ],
    "expected_window": "1-2Q | 3-4Q | 1년+ | 불명",
    "verdict": "RESOLVING | EARLY_SIGNS | NO_EVIDENCE | WORSENING",
    "summary": "해소 전망 2~3문장 (140~220자). 무엇이 언제 확인되면 풀리는지, 반대로 무엇이 확인되면 트랩인지 함께 [출처 태그]"
  }
}
```

`evidence` 0~4개 · `counter_evidence` 0~3개. **빈 배열 허용** — 채우려고 지어내지 않습니다.

### 자기 점검 (출력 전 필수)

- [ ] `evidence`의 모든 항목이 `cause_restated`를 **직접** 겨냥하는가
- [ ] 각 `evidence`에 `verifiable_by`가 있는가 (없으면 의견 → 삭제)
- [ ] `nature`가 STRUCTURAL인데 `RESOLVING`이면, 구조 자체가 바뀐다는 근거가 있는가 (없으면 `EARLY_SIGNS` 이하)
- [ ] 재무 마진 추세와 판정이 충돌하지 않는가 (충돌 시 **재무 우선**)
- [ ] `NO_EVIDENCE`를 피하려고 약한 항목을 끼워 넣지 않았는가

## 7. 메인 룰북과의 관계

`value_recovery_quant.md`의 4팩터가 Top 20 **후보**를 선별하고, `fundamental_analyst`가 각 후보의 저평가 **원인**을 진단합니다. 본 룰북은 그 원인이 **해소되고 있는지**를 검증해 `portfolio_ranker` §4.1의 주 입력을 만듭니다.

```
value_recovery_quant (정량 후보 20)
        ↓
fundamental_analyst  →  undervaluation_cause {text, nature}   ← 진단
risk_analyst         →  risks[]
        ↓
resolution_scout     →  resolution {evidence, verdict, window} ← 처방 탐색 (본 룰북)
        ↓
synthesizer          →  ai_notes (구조 그대로 통과)
        ↓
portfolio_ranker     →  ai_rank  (§4.1 주 입력 = resolution.verdict)
```

정량 점수는 본 룰북이 **변경하지 않습니다.** 후보 자격은 정량이 보장하고, 본 룰북은 그 안의 순서에만 영향을 줍니다.

## 8. 운영 예외 처리

| 상황 | 처리 |
|---|---|
| `undervaluation_cause` 누락 | 본 단계 생략, `resolution` 키 자체를 출력하지 않음 (`portfolio_ranker`가 폴백 경로 선택) |
| WebSearch 실패·결과 없음 | `NO_EVIDENCE` + 빈 배열. 실패로 처리하지 않음 |
| 검색 결과가 원인과 무관한 호재뿐 | 전부 기각 후 `NO_EVIDENCE` |
| `evidence`와 `counter_evidence`가 팽팽 | `EARLY_SIGNS` 이하로 두고 `portfolio_ranker`가 −1 반영 |
| 재무 추세가 검색 서술과 충돌 | **재무 우선**, 근거에 `[출처: DART · YYYY]` 병기 |
| `kind`가 `CAPITAL_POLICY`뿐 | 그대로 출력하되 `portfolio_ranker`가 한 단계 하향 (이익 회복이 아니라 주주환원) |
