---
name: forward_attractive
version: 1.0.0
type: auxiliary_rulebook
description: Forward PER 단독 매력도로 종목을 발굴하는 보조 룰북. 메인 룰북의 4팩터 중 s3_per 한 축에 집중해, 향후 12개월 이익 추정 개선이 가장 가파른 종목을 추출합니다. 단일 팩터에 신뢰도 페널티를 결합한 단순 모델입니다.
parent_rulebook: value_recovery_quant.md
output: data/screens/forward_attractive.json
---

# forward_attractive — Forward PER 단독 보조 룰북

## 1. 핵심 컨셉

5년 평균 PER과의 비교는 흑자 분기 부족, 재무구조 변화, M&A 등으로 노이즈가 클 수 있습니다. 본 보조 룰북은 그런 노이즈를 우회하는 단순 모델입니다. 5년 평균을 보지 않고 시장이 이미 12개월 후 이익을 추정해 놓은 Forward PER만 사용합니다.

가치투자 본질의 한 단면, 즉 "지금 사면 미래 PER이 얼마나 매력적인가"만 보는 모델입니다. 메인 룰북(`value_recovery_quant`)의 4팩터 중 `s3_per` 하나에 집중한 변형이며, 메인과 같은 universe와 데이터 소스를 공유하지만 완전히 독립적으로 정의됩니다.

## 2. 데이터 소스

| 데이터 | 출처 | 비고 |
|---|---|---|
| Forward PER | 네이버 Wisereport | 가장 최근 컨센서스 추정치 |
| Current PER | pykrx | TTM |
| broker_count (커버리지) | 네이버 | 신뢰도 가중치에 사용 |

본 룰북은 5년 시계열을 사용하지 않습니다. 컨센서스 데이터만으로 단일 시점 점수를 만듭니다. 입력 데이터는 메인 룰북의 `universe.json`을 그대로 재사용하므로 별도 페치가 필요하지 않습니다.

## 3. 1차 필터

| 필터 | 임계값 | 이유 |
|---|---|---|
| 시가총액 | 3,000억 원 이상 | 메인 룰북 universe와 통일 |
| Forward PER | 보유 + 양수 | 적자 추정 종목 제외 |
| Forward PER | 30 이하 | 절대 매력 임계 |
| Current PER | 100 이하 | 극단치 제외 |
| broker_count | 2 이상 | 단일 증권사 의존 신뢰도 부족 방지 |

본 룰북은 메인 룰북보다 다소 느슨한 필터를 사용합니다. 5년 PER 검증을 거치지 않으므로 적자 이력이 있어도 Forward 추정만 양수면 통과시킵니다. 그 대신 컨센서스의 신뢰도(broker_count)를 별도 페널티로 반영해 균형을 맞춥니다.

## 4. 점수화 룰

본 룰북은 다음 세 단계를 순차 적용합니다.

### 4.1 Forward 매력도 raw 계산

```python
df["fwd_attractive_raw"] = (df["current_per"] - df["forward_per"]) / df["current_per"]
```

양수가 클수록 Forward PER이 현재보다 낮다는 의미이며, 시장이 향후 12개월 이익 개선을 가격에 반영하고 있다는 신호입니다.

### 4.2 Rank → Z-Score 정규화

```python
df["fwd_attractive_z"] = zscore_from_rank(df["fwd_attractive_raw"])
```

메인 룰북과 동일하게 순위 기반 Z-Score를 사용합니다. Outlier에 강하고 분포가 자동으로 정규화됩니다.

### 4.3 신뢰도 페널티 적용

```python
df["confidence"] = (df["broker_count"].clip(2, 10) - 2) / 8   # 0 ~ 1
df["fwd_score"]  = df["fwd_attractive_z"] * (0.7 + 0.3 * df["confidence"])
```

신뢰도 페널티는 본 룰북의 핵심 차이점입니다. 컨센서스 단일 의존 모델이므로 broker_count가 작은 종목은 추정치 자체가 흔들릴 가능성이 높아 점수를 감점합니다.

| broker_count | confidence | 점수 배수 |
|---|---|---|
| 2 | 0.0 | 0.70 |
| 4 | 0.25 | 0.78 |
| 6 | 0.50 | 0.85 |
| 10 이상 | 1.0 | 1.00 |

broker_count가 2면 raw Z-Score의 70%만, 10 이상이면 100%가 점수에 반영됩니다.

### 4.4 티어 분류

| 등급 | 임계값 | universe 상위 비율 |
|---|---|---|
| Forward Strong Buy | fwd_score ≥ +1.65σ | 5% |
| Forward Buy | fwd_score ≥ +0.84σ | 20% |
| Watch | fwd_score ≥ 0σ | 50% |
| Skip | fwd_score < 0σ | 하위 50% |

표준 정규분포 임계값을 메인 룰북과 동일하게 사용합니다.

## 5. 시각화 룰

### 5.1 메인 차트 — 산점도

본 룰북의 핵심 시각화는 산점도입니다. 메인 룰북의 카드 그리드와 다르게, Forward 매력도가 단일 팩터이므로 시총·신뢰도와의 관계를 동시에 보여 주는 산점도가 가장 적합합니다.

| 축·요소 | 매핑 |
|---|---|
| X축 | 시가총액 (log scale) |
| Y축 | Forward 개선폭 (raw) |
| 점 크기 | broker_count |
| 점 색 | fwd_score Z-Score (양수 녹색, 음수 회색) |

산점도의 4분면 해석은 다음과 같습니다.

| 위치 | 의미 |
|---|---|
| 우상단 (시총 큼 + Forward 매력 큼) | Hidden Gem 후보 |
| 좌상단 (시총 작음 + Forward 매력 큼) | 고변동 단일 베팅 |
| 우하단 (시총 큼 + Forward 매력 약함) | 안정 보유 |
| 좌하단 (시총 작음 + Forward 매력 약함) | 회피 |

### 5.2 Top 10 카드

산점도 우측에 메인 룰북과 같은 디자인의 카드 그리드가 함께 배치됩니다. 다만 4팩터 막대 대신 단일 팩터 막대 + 신뢰도 표시가 들어갑니다.

| 카드 영역 | 내용 |
|---|---|
| 헤더 | 순위 + Forward Strong Buy / Buy 배지 |
| 종목명 | 종목명, 코드, 시장, 현재가 |
| 단일 팩터 막대 | Forward 개선폭 (Z-Score 양수 강조) |
| 신뢰도 표시 | broker_count 점 N개 시각화 |
| 정량 수치 | Current PER, Forward PER, 개선폭 % |
| 종합 점수 | fwd_score 큰 폰트 표시 |

### 5.3 데이터 부족 시 처리

| 상황 | 처리 |
|---|---|
| Forward PER 미보유 | universe 통과 못함 → UI에서 표시 안 됨 |
| broker_count < 2 | universe 통과 못함 |
| 산점도 데이터 부재 | "데이터 미생성" 안내 표시 |

## 6. 인사이트 생성 룰

### 6.1 자동 코멘트 템플릿

```
[FWD_GAP] Forward PER {fwd:.2f} vs Current {cur:.2f} → -{raw*100:.1f}% 하향
[CONSENSUS] 증권사 {n}곳 추정, 평균 목표 {target}원 ({upside_raw*100:+.1f}%)
[POSITIONING] universe 내 {rank}위, Z={z:+.2f}σ
```

### 6.2 3-소스 원칙

본 룰북은 메인 룰북과 동일한 3-소스 원칙을 따릅니다. 사전 페치 정량(`[정량]`), Tool Call 결과(`[출처: WebSearch · YYYY-MM]`), 룰 정의 자체 외의 출처는 인용하지 않습니다.

### 6.3 정성 분석 위임

본 룰북은 정성 분석 에이전트를 별도로 정의하지 않습니다. 메인 룰북의 서브에이전트(`fundamental_analyst`, `risk_analyst`, `synthesizer`)를 그대로 재사용합니다. 정성 분석은 룰북별로 다를 이유가 없기 때문입니다.

## 7. 메인 룰북과의 관계

| 구분 | 메인 (value_recovery_quant) | 본 룰북 (forward_attractive) |
|---|---|---|
| 팩터 수 | 4 | 1 |
| 시간축 | 과거 5년 + 미래 1년 | 미래 1년만 |
| Z-Score 정규화 | 그룹 합산 후 재 Z | 단일 팩터 Z |
| 가중치 | Value 60 + Growth 40 | (단일 팩터, 신뢰도 페널티) |
| 시각화 | 카드 그리드 | 산점도 + 카드 |
| 활용 | 종합 가치투자 | Forward 매력 단독 검색 |

본 룰북은 메인 룰북과 완전히 독립적이지만 같은 universe와 같은 데이터 소스를 공유합니다. 룰북을 추가하면 코드 변경 없이 새 페이지가 자동 매핑되는 Skills.md 패러다임의 1차 데모입니다.

---

## 8. 운영 예외 처리

| 시나리오 | 처리 룰 |
|---|---|
| Forward PER 페치 실패 | 해당 종목 universe 제외, 다른 종목 정상 처리 |
| broker_count 데이터 부재 | broker_count = 2로 가정 (최저 신뢰도), 페널티 0.7 적용 |
| Current PER이 음수 (적자) | universe 제외 |
| Forward PER이 30 초과 | universe 제외 (절대 매력 임계 위반) |
| 정성 분석 필요 시 | 메인 룰북의 fundamental_analyst, risk_analyst, synthesizer 그대로 재사용 |

## 부록 — 구현 상태

본 룰북의 명세는 확정되어 있으나, 페치 스크립트와 산점도 시각화 컴포넌트는 메인 룰북 일정상 후순위에 있습니다. 명세에 따라 `apply_forward_attractive.py`와 산점도 차트가 추가되면 사이트의 Section 4로 노출됩니다.
