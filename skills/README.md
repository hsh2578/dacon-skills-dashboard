# Skills.md 패키지

DACON 해커톤 제출용 Skills.md 패키지. 이 폴더 전체를 .zip으로 묶어 제출.

## 구성

### 메인 룰북
- [`value_recovery_quant.md`](./value_recovery_quant.md) — 역사적 저평가 + 회복 모멘텀 + 미래 이익 성장 (Triple Cross)

### 보조 룰북 (계획)
- `forward_attractive.md` — 12개월 선행 PER 단독 매력
- `peer_relative.md` — 동종 섹터 대비 저평가
- `dividend_value.md` — 배당 + 가치 결합

### 종목 상세 21섹션 ([stock_detail/](./stock_detail/))
종목 클릭 시 21패널 깊이 대시보드를 정의하는 .md 21개.

## 표준 스키마

모든 Skills.md는 다음 6섹션을 따른다.

```markdown
# {룰북 이름}

## 1. 핵심 컨셉
한 줄 요약 + 어떤 시장 통찰에서 출발했는지

## 2. 데이터 소스
- {출처}: {필드}, {기간}, {인증 여부}

## 3. 1차 필터 (필수)
통과 못하면 분석 제외

## 4. 점수화 룰
- 정규화 방식 (Z-score, percentile 등)
- 팩터별 가중치
- Value Trap 등 안전 가드

## 5. 시각화 룰
- 카드 형태·색상·차트 종류
- 그리드 위치
- 데이터 부족 시 표시

## 6. 인사이트 생성 룰
- 자동 코멘트 템플릿
- 3-소스 원칙 (확인 필요 명시)
```
