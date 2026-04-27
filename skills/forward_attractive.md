---
name: forward_attractive
version: 0.1.0
type: auxiliary_rulebook
description: Forward PER 단독 매력도로 종목을 발굴하는 보조 룰북. 메인 룰북의 4팩터 중 s3_per 한 축에 집중해, 향후 12개월 이익 추정 개선이 가장 가파른 종목을 추출합니다.
parent_rulebook: value_recovery_quant.md
status: 골격 (v1.0 작성 예정)
output: data/screens/forward_attractive.json (계획)
---

# forward_attractive — Forward PER 단독 보조 룰북

## 1. 핵심 컨셉

5년 평균 PER과의 비교는 흑자 분기 부족, 재무구조 변화, M&A 등으로 노이즈가 클 수 있습니다. 본 보조 룰북은 그런 노이즈를 우회하는 단순 모델입니다. 5년 평균을 보지 않고 **시장이 이미 12개월 후 이익을 추정해 놓은 Forward PER만 봅니다.**

가치투자 본질의 한 단면, 즉 "지금 사면 미래 PER이 얼마나 매력적인가"만 보는 모델입니다. 메인 룰북(`value_recovery_quant`)의 4팩터 중 `s3_per` 하나에 집중한 변형이며, 메인과 같은 universe와 데이터 소스를 공유하지만 완전히 독립적으로 정의됩니다.

## 2. 데이터 소스

| 데이터 | 출처 | 비고 |
|---|---|---|
| Forward PER | 네이버 Wisereport | 가장 최근 컨센서스 추정치 |
| Current PER | pykrx | TTM |
| broker_count (커버리지) | 네이버 | 신뢰도 가중치에 사용 |

본 룰북은 5년 시계열을 사용하지 않습니다. 컨센서스 데이터만으로 단일 시점 점수를 만듭니다.

## 3. 1차 필터

| 필터 | 임계값 | 이유 |
|---|---|---|
| 시가총액 | 3,000억 원 이상 | 메인 룰북 universe 그대로 사용 |
| Forward PER | 보유 + 양수 | 적자 추정 종목 제외 |
| Forward PER | 30 이하 | 절대 매력 임계 — 너무 높으면 의미 없음 |
| Current PER | 100 이하 | 극단치 제외 |
| broker_count | 2 이상 | 단일 증권사 의존 신뢰도 부족 방지 |

메인 룰북보다 다소 느슨한 필터를 사용합니다. 5년 PER 검증을 거치지 않으므로 적자 이력이 있어도 Forward 추정만 양수면 통과시킵니다.

## 4. 점수화 룰 (v1.0 계획)

```python
df["fwd_attractive_raw"] = (df["current_per"] - df["forward_per"]) / df["current_per"]
df["fwd_attractive_z"]   = zscore_from_rank(df["fwd_attractive_raw"])

# 신뢰도 페널티: broker_count 적으면 점수 감점
df["confidence"]   = (df["broker_count"].clip(2, 10) - 2) / 8   # 0 ~ 1
df["fwd_score"]    = df["fwd_attractive_z"] * (0.7 + 0.3 * df["confidence"])
```

| 결과 | 의미 |
|---|---|
| fwd_score ≥ +1.65σ | universe 상위 5% — Forward Strong Buy |
| fwd_score ≥ +0.84σ | 상위 20% — Forward Buy |
| fwd_score < 0 | Watch / Skip |

신뢰도 페널티는 본 룰북의 특징입니다. 컨센서스 단일 의존 모델이므로 broker_count가 작은 종목은 추정치 자체가 흔들릴 수 있어 점수를 감점합니다.

## 5. 시각화 룰 (v1.0 계획)

| 영역 | 시각화 |
|---|---|
| 메인 차트 | 산점도 — X축 시가총액(log), Y축 Forward 개선폭, 점 크기 broker_count, 색 z-score |
| 4분면 해석 | 우상단 (시총 큼 + Forward 매력 큼) = HIDDEN_GEM 후보. 좌상단 (시총 작음 + Forward 매력 큼) = 고변동 단일 베팅. 우하단 (시총 큼 + Forward 매력 약함) = 안정 보유 |
| 카드 형식 | 메인 룰북 Top 10과 같은 카드 디자인, 단 단일 팩터 막대 + 신뢰도 표시 |

본 룰북이 v1.0으로 완성되면 사이트 별도 페이지(또는 메인의 Section 4)로 추가됩니다.

## 6. 인사이트 생성 룰 (v1.0 계획)

```
[FWD_GAP] Forward PER {fwd:.2f} vs Current {cur:.2f} → -{raw*100:.1f}% 하향
[CONSENSUS] 증권사 {n}곳 추정, 평균 목표 {target}원 ({upside_raw*100:+.1f}%)
[POSITIONING] universe 내 {rank}위, Z={z:+.2f}σ
```

3-소스 원칙은 메인 룰북과 동일합니다. 사전 페치 정량만 인용하며, 정성 분석이 필요하면 메인 룰북의 서브에이전트(`fundamental_analyst`, `risk_analyst`, `synthesizer`)를 그대로 재사용합니다.

## 7. 메인 룰북과의 관계

| 구분 | 메인 (value_recovery_quant) | 본 룰북 (forward_attractive) |
|---|---|---|
| 팩터 수 | 4 | 1 |
| 시간축 | 과거 5년 + 미래 1년 | 미래 1년만 |
| Z-Score 정규화 | 그룹 합산 후 재 Z | 단일 팩터 Z |
| 가중치 | Value 60 + Growth 40 | (단일, 신뢰도 페널티) |
| 활용 | 종합 가치투자 | Forward 매력 단독 검색 |

본 룰북은 메인 룰북과 **완전히 독립적**이지만 같은 universe와 같은 데이터 소스를 공유합니다. 룰북을 추가하면 코드 변경 없이 새 페이지가 자동 매핑되는 Skills.md 패러다임의 1차 데모입니다.

---

## 부록 — 작업 일정

| 버전 | 내용 |
|---|---|
| v0.1 (현재) | 골격만 작성, 페치 스크립트 미구현, 시각화 미구현 |
| v1.0 (계획) | `apply_forward_attractive.py` 페치 스크립트 + 산점도 시각화 + Top 10 카드 + 자동 코멘트 |
