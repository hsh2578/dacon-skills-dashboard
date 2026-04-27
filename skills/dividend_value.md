---
name: dividend_value
version: 0.1.0
type: auxiliary_rulebook
description: 배당수익률(Income)과 가치(저평가)를 동시에 만족하는 종목을 발굴하는 보조 룰북. 메인 룰북의 회복 모멘텀 결합 대신 안정 인컴 + 저평가 결합을 노립니다.
parent_rulebook: value_recovery_quant.md
status: 골격 (v1.0 작성 예정)
output: data/screens/dividend_value.json (계획)
---

# dividend_value — 배당 + 가치 결합 보조 룰북

## 1. 핵심 컨셉

가치투자의 보수적 변형입니다. 메인 룰북(`value_recovery_quant`)이 "성장 + 가치" 결합으로 회복 모멘텀을 노린다면, 본 보조 룰북은 "인컴 + 가치" 결합으로 **현금흐름이 검증된 종목 중 시장 평균 대비 저평가**된 종목만 추출합니다.

배당은 거짓말을 못 합니다. 회사가 실제로 현금이 있어야만 지급 가능하기 때문입니다. 그래서 배당 안정성은 회사 재무 건전성의 강력한 시그널입니다. 본 룰북은 이 시그널을 가치 평가와 결합해, 적극적 매크로 베팅보다 안정적인 인컴과 저평가 회수를 노리는 사용자를 위한 도구로 설계했습니다.

## 2. 데이터 소스

| 데이터 | 출처 | 비고 |
|---|---|---|
| 배당수익률 | pykrx (`get_market_fundamental_by_ticker`) | DIV 필드 |
| Current PER · PBR | pykrx | TTM |
| 5Y 평균 PER · PBR | `data/matrix/{per,pbr}_monthly.json` | 본 프로젝트 사전 페치 |
| 5Y 배당 시계열 | pykrx 일별 DIV → 분기 평균 (구현 예정) | 배당 안정성 검증 |

본 룰북의 큰 장점은 **컨센서스 의존도가 0**이라는 점입니다. 네이버 컨센이 일시 차단되거나 컨센이 없는 종목도 분석 가능합니다.

## 3. 1차 필터

| 필터 | 임계값 | 사유 |
|---|---|---|
| 시가총액 | 3,000억 원 이상 | 메인 룰북과 통일 |
| 배당수익률 | 3% 이상 | 시장 평균(약 1.8%) 대비 매력 임계 |
| 5Y 배당 지급 | 무지급 분기 4분기 이하 | 안정성 검증 |
| Current PER | 5Y 평균 PER 이하 | 저평가 조건 |
| Current PBR | 5Y 평균 PBR 이하 | 동일 |

통과 universe는 약 50종목 정도로 메인보다 훨씬 좁아질 것으로 예상됩니다. 배당 안정성과 가치를 동시에 만족하는 종목은 시장에서 상대적으로 드물기 때문입니다.

## 4. 점수화 룰 (v1.0 계획)

```python
# 정규화 (rank → Z)
df["div_z"]            = zscore_from_rank(df["dividend_yield"])
df["per_undervalue_z"] = zscore_from_rank((df["avg_5y_per"] - df["current_per"]) / df["avg_5y_per"])
df["pbr_undervalue_z"] = zscore_from_rank((df["avg_5y_pbr"] - df["current_pbr"]) / df["avg_5y_pbr"])

# 그룹 점수
df["income_score"] = df["div_z"]
df["value_score"]  = zscore(df["per_undervalue_z"] + df["pbr_undervalue_z"])

# 가중 합산 — Income 50 / Value 50
df["dv_score"] = df["income_score"] * 0.50 + df["value_score"] * 0.50
```

가중치는 50:50입니다. 이는 메인 룰북의 60:40과 다른 의도적 결정입니다.

| 그룹 | 의미 | 본 룰북 가중치 |
|---|---|---|
| Income | 배당이 검증된 현실 | 50% |
| Value | 시장 평균 대비 저평가 | 50% |

검증된 현실(배당)과 시장 인식(저평가)을 동등하게 본다는 본 룰북의 정체성을 가중치에 반영했습니다. 이 차이가 같은 Skills.md 스키마가 어떻게 다른 투자 철학을 표현할 수 있는지 보여 주는 핵심 데모입니다.

## 5. 시각화 룰 (v1.0 계획)

| 영역 | 시각화 |
|---|---|
| 메인 차트 | 듀얼 축 차트 — X축: 5Y 평균 PER 대비 저평가 폭. Y축: 배당수익률. 우상단(저평가 + 고배당)이 가장 매력 |
| 카드 하단 | 배당 5Y 시계열 미니 차트로 안정성 시각 검증 |
| 안정성 라벨 | 배당 추세를 "증가 추세 / 안정 유지 / 변동성 있음"으로 분류 |

안정성 라벨 분류 기준은 다음과 같습니다.

| 5년 배당 변화 | 라벨 |
|---|---|
| 모두 증가 | 증가 추세 |
| 변동 폭 ±10% 이내 | 안정 유지 |
| 1회 이상 감소 | 변동성 있음 |

## 6. 인사이트 생성 룰

```
[INCOME] 배당수익률 {div:.2f}% (5Y 평균 {div_5y:.2f}%, {trend} 추세)
[VALUE_PER] 5Y 평균 PER {avg_5y:.2f} 대비 -{undervalue*100:.1f}%
[VALUE_PBR] 5Y 평균 PBR {avg_5y_pbr:.2f} 대비 -{undervalue*100:.1f}%
[STABILITY] 5Y 무배당 분기 {missing}/20 → {stability_label}
```

3-소스 원칙은 메인 룰북과 동일합니다. 사전 페치 정량만 인용하며, 정성 분석은 메인 룰북의 서브에이전트를 그대로 재사용합니다.

## 7. 메인 룰북과의 관계

| 구분 | 메인 (value_recovery_quant) | 본 룰북 (dividend_value) |
|---|---|---|
| 시간축 | 과거 + 미래 (Forward 포함) | 과거 + 현재 (배당 + 가치) |
| 베팅 성격 | 회복 모멘텀 | 안정 인컴 |
| 가중치 | Value 60 + Growth 40 | Income 50 + Value 50 |
| 타깃 사용자 | 적극적 가치투자자 | 안정적 인컴 투자자 |
| 컨센 의존 | 있음 (Forward, target) | 없음 (배당, PER, PBR만) |

본 룰북은 메인 룰북과 같은 Skills.md 스키마를 따르지만, 가중치와 시간축 선택만 바꾸어 완전히 다른 투자 철학을 표현합니다. 사용자가 자기 신념대로 룰북을 추가·수정할 수 있다는 Skills.md 패러다임의 두 번째 데모입니다.

---

## 부록 — 작업 일정

| 버전 | 내용 |
|---|---|
| v0.1 (현재) | 골격만 작성, 배당 5Y 시계열 페치 미구현 |
| v1.0 (계획) | `apply_dividend_value.py` 페치 스크립트 + 듀얼 축 차트 + 안정성 라벨 + Top 10 카드 |
