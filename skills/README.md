# Skills.md 패키지 — 한국 주식 가치투자 종목 발굴

DACON 월간 해커톤 "투자 데이터를 시각화하라 — Skills 기반 대시보드 설계" 출품작의 Skills.md 제출 패키지입니다. 본 패키지는 한국 주식 시장에서 가치투자 종목을 자동 발굴하기 위한 분석 규칙을 .md 문서들로 정의합니다. 각 문서가 곧 알고리즘 명세서이며, 사이트의 자동 갱신 파이프라인이 이 문서들을 따라 동작합니다.

---

## 패키지 구성

본 패키지는 메인 룰북 한 장, 보조 룰북 두 장, AI 서브에이전트 룰북 세 장, 그리고 본 README로 구성됩니다.

| 구분 | 파일 | 역할 |
|---|---|---|
| 메인 | `value_recovery_quant.md` | 4팩터 Z-Score 가중합산으로 가치투자 Top 10 추출 |
| 보조 | `forward_attractive.md` | Forward PER 단독 매력도 모델 (단일 팩터 변형) |
| 보조 | `dividend_value.md` | 배당 + 가치 결합 모델 (보수적 변형) |
| AI 에이전트 | `agents/fundamental_analyst.md` | 정성 모멘텀 추출 (WebSearch + 출처 태그) |
| AI 에이전트 | `agents/risk_analyst.md` | 정성·정량 리스크 추출 |
| AI 에이전트 | `agents/synthesizer.md` | 두 정성 분석을 카드용 단일 JSON으로 통합 |
| 패키지 설명 | `README.md` | 본 문서 |

---

## 표준 6섹션 스키마

본 패키지의 모든 룰북은 다음 6섹션 구조를 따릅니다. 이 구조가 곧 대시보드 자동 생성의 입력 명세서 역할을 합니다.

| 섹션 | 내용 |
|---|---|
| 1. 핵심 컨셉 | 한 줄 요약 + 어떤 시장 통찰에서 출발했는지 |
| 2. 데이터 소스 | 출처, 필드, 기간, 인증 여부 |
| 3. 1차 필터 | 통과하지 못하면 분석 자체에서 제외 |
| 4. 점수화 룰 | 정규화 방식, 가중치, 안전 가드 |
| 5. 시각화 룰 | 카드 형태, 색상, 차트 종류, 데이터 부족 시 표시 |
| 6. 인사이트 생성 룰 | 자동 코멘트 템플릿, 3-소스 원칙 |

룰북을 추가하면 사이트에 새 섹션이 자동으로 매핑되도록 설계의 첫 단추를 마련했습니다. 사용자가 자기 신념을 담은 새 룰북을 작성해 추가하면, 기존 코드 수정 없이도 결과가 사이트에 반영될 수 있는 구조입니다.

---

## 룰북 카탈로그

세 룰북은 같은 universe와 같은 데이터 소스를 공유하면서도 서로 다른 투자 철학을 표현합니다. 가중치, 시간축, 데이터 의존도 차이가 본 패키지의 정체성을 형성합니다.

| 룰북 | 시간축 | 가중치 | 컨센 의존 | 타깃 사용자 |
|---|---|---|---|---|
| value_recovery_quant (메인) | 과거 5년 + 미래 1년 | Value 60 + Growth 40 | 있음 | 회복 모멘텀 추구 가치투자자 |
| forward_attractive | 미래 1년만 | 단일 팩터 + 신뢰도 페널티 | 있음 | Forward 매력 단독 검색자 |
| dividend_value | 과거 5년 + 현재 (배당) | Income 50 + Value 50 | 없음 | 안정 인컴 + 저평가 추구자 |

같은 Skills.md 스키마가 어떻게 다른 투자 철학을 표현할 수 있는지 보여 주는 것이 룰북 카탈로그의 의도입니다.

---

## AI 서브에이전트 — 정성 분석도 Skills.md입니다

본 패키지의 큰 특징은 AI 서브에이전트 자체도 Skills.md 형식으로 정의되어 있다는 점입니다. 정성 분석이 매번 달라지지 않고 동일한 룰을 따라 재현 가능하게 만들기 위해서입니다.

| 에이전트 | 담당 카테고리 | 출력 |
|---|---|---|
| fundamental_analyst | CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS | 정성 모멘텀 4~5개 + evidence_strength |
| risk_analyst | EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE | 정성·정량 리스크 3~4개 + overall_risk_level |
| synthesizer | (위 두 결과 통합) | 카드용 단일 JSON (one_liner, points, risks, verdict, 배지) |

세 에이전트 모두 동일한 출처 태그 강제 룰을 따릅니다. 어떤 항목이든 "이 정보가 어디서 왔는지"를 명시하지 않으면 출력이 막힙니다.

| 출처 태그 | 의미 |
|---|---|
| `[정량]` | 입력 JSON 필드에서 도출된 진술 |
| `[출처: WebSearch · YYYY-MM]` | WebSearch에서 직접 확인된 사실 |
| `확인 필요` | 출처가 모호하거나 1년 이상 오래된 정보 |

출처 태그가 없는 주장은 환각으로 분류되어 출력에서 제외됩니다. 이 단순한 룰이 본 패키지의 모든 정성 인사이트의 신뢰성을 담보합니다.

---

## 3-소스 원칙

본 패키지의 모든 룰북은 다음 세 출처만 인용 가능합니다. 그 외의 출처(특히 LLM이 학습 단계에서 외운 수치)는 환각으로 분류됩니다.

| 소스 | 적용 영역 | 태그 |
|---|---|---|
| 사전 페치 정량 | pykrx, 네이버 컨센, multpl, yfinance에서 페치된 JSON | [정량] |
| Tool Call 결과 | WebSearch (정성 룰북에서만 사용) | [출처: WebSearch · YYYY-MM] |
| 룰 정의 자체 | Skills.md에 적힌 임계값, 가중치, 공식 | 표기 불필요 |

---

## 룰북 간 의존 관계

본 패키지의 룰북들이 어떻게 연결되는지 정리하면 다음과 같습니다.

```
data/universe.json (universe 303종목)
    ↓
value_recovery_quant.md (메인) ──→ data/screens/triple_cross.json (Top 10 + 정량 점수)
    ↓
fundamental_analyst.md ──→ 정성 모멘텀
risk_analyst.md       ──→ 정성·정량 리스크
    ↓
synthesizer.md        ──→ data/screens/ai_notes.json (카드용 통합 JSON)
    ↓
사이트 (index.html, stock.html)


[보조 룰북 — 독립 적용]
forward_attractive.md ──→ data/screens/forward_attractive.json (계획)
dividend_value.md     ──→ data/screens/dividend_value.json (계획)
```

메인 룰북이 정량 점수를 만들고, 두 정성 분석 에이전트가 모멘텀과 리스크를 별도 관점에서 도출하며, 통합 에이전트가 이를 카드용 JSON으로 합칩니다. 보조 룰북은 메인과 독립적으로 적용되어 같은 universe에 다른 가중치 모델을 시연합니다.

---

## 사이트 적용

본 패키지의 룰북들은 정적 호스팅 사이트에서 다음과 같이 적용됩니다.

| 룰북 | 적용 위치 |
|---|---|
| value_recovery_quant.md | 메인 페이지 Section 2 (Top 10 카드), 종목 상세 페이지 시그널 카드 |
| fundamental_analyst.md + risk_analyst.md + synthesizer.md | Top 10 카드 펼침 영역, 종목 상세 페이지 AI 서브에이전트 분석 영역 |
| forward_attractive.md | (계획) 메인 페이지 Section 4 또는 별도 페이지 |
| dividend_value.md | (계획) 동일 |

배포 URL: https://hsh2578.github.io/dacon-skills-dashboard/

---

## 갱신 운영

본 패키지의 룰북들은 슬래시 커맨드 한 줄로 일괄 적용됩니다.

| 명령 | 동작 | 소요 시간 |
|---|---|---|
| /update-data | 시장 지수 + 매트릭스 + 정량 점수 + AI 정성 분석 | 약 12분 |
| /update-data --full | universe 재구축 포함 | 약 30분 |
| /update-data --skip-ai | 정량만 갱신 | 약 10분 |

명령 한 줄로 본 패키지의 모든 룰북이 적용되어 데이터 JSON이 갱신되고, GitHub에 커밋하면 약 30초 만에 사이트에 반영됩니다.

---

## 환각 방지 설계 요약

본 패키지가 LLM 출력의 환각을 차단하는 네 가지 장치는 다음과 같습니다.

| 장치 | 적용 |
|---|---|
| 3-소스 원칙 | 사전 페치 정량 / WebSearch / 룰 정의 외 출처 금지 |
| 출처 태그 강제 | 정성 항목마다 [출처: ...] 또는 [정량] 또는 확인 필요 태그 필수 |
| 데이터·정성 분리 | 정량 점수(메인 룰북)는 LLM이 만들지 않고 결정론적 코드로 산출 |
| 카테고리 라벨 | 정성 항목마다 사전 정의된 카테고리(CATALYST/THESIS/EARNINGS/EXECUTION 등) 적용 |

이 네 장치가 동시에 작동해, 어떤 출력 항목도 추적 불가능한 주장이 되지 않도록 보장합니다.

---

## Skills.md 메타 명세 — 새 룰북 추가 가이드

본 패키지에 새로운 룰북을 추가하려는 사용자가 따라야 할 메타 규칙입니다. 이 명세를 지키면 사이트의 자동 매핑 파이프라인이 새 룰북을 인식할 수 있습니다.

### 필수 frontmatter

모든 룰북은 .md 파일 최상단에 다음 YAML frontmatter를 포함해야 합니다.

```yaml
---
name: <룰북 식별자, snake_case>
version: <semver, 예: 1.0.0>
type: main_rulebook | auxiliary_rulebook | agent_rulebook
description: <한 줄 설명, 100자 이내>
parent_rulebook: <메인 룰북 경로, 보조 룰북에만 필수>
output: <결과 JSON 경로, 정량 룰북에만>
implementation: <Python 스크립트 경로, 구현된 경우>
tools: <에이전트 룰북에만, 예: WebSearch, Read>
---
```

### 메타 필드 검증 룰

| 필드 | 필수 여부 | 검증 룰 |
|---|---|---|
| name | 필수 | 영문 소문자 + underscore, 다른 룰북과 중복 금지 |
| version | 필수 | semver 형식 (1.0.0, 1.1.0 등) |
| type | 필수 | 위 4종 중 하나 |
| description | 필수 | 100자 이내, 합쇼체 종결 |
| parent_rulebook | 보조·에이전트 룰북에만 | 메인 룰북 파일 경로 (skills/ 기준) |
| output | 정량 룰북에만 | data/screens/{name}.json 형식 |
| implementation | 구현된 경우만 | scripts/{name}.py 형식 |
| tools | 에이전트 룰북에만 | Anthropic 도구명 (WebSearch, Read 등) |

### 본문 표준 6섹션 (필수)

frontmatter 다음에는 표준 6섹션이 정확한 순서로 들어가야 합니다.

```markdown
## 1. 핵심 컨셉
## 2. 데이터 소스
## 3. 1차 필터
## 4. 점수화 룰         (또는 분석 룰)
## 5. 시각화 룰
## 6. 인사이트 생성 룰
```

추가 섹션은 §7 이후에 자유롭게 둘 수 있습니다. 본 패키지 룰북들은 §7 메인 룰북과의 관계, §8 운영 예외 처리를 공통으로 둡니다.

### 자동 매핑 동작

새 룰북이 위 명세를 따르면 다음 자동 처리가 일어납니다.

| 단계 | 자동 동작 |
|---|---|
| 1 | 슬래시 커맨드(`/update-data`)가 frontmatter의 `implementation` 필드를 읽어 페치 스크립트 실행 |
| 2 | 출력 JSON(`output` 필드)이 사이트에서 fetch 가능한 위치에 생성 |
| 3 | (계획) 사이트 메뉴에 새 룰북 카드 카탈로그 자동 추가 |
| 4 | (계획) §5 시각화 룰을 읽어 적절한 차트 컴포넌트 선택 |

3, 4번은 v2.0에서 본격 구현 예정인 자동 매핑 단계입니다. 현재 v1.0은 frontmatter 검증과 1, 2번 자동화까지 지원합니다.

### 새 룰북 추가 예시

가상의 "고변동성 모멘텀" 룰북을 추가한다고 가정합니다.

```yaml
---
name: high_volatility_momentum
version: 0.1.0
type: auxiliary_rulebook
description: 30일 변동성 상위 종목 중 단기 모멘텀 양호한 종목을 발굴하는 보조 룰북.
parent_rulebook: value_recovery_quant.md
output: data/screens/high_volatility_momentum.json
---

## 1. 핵심 컨셉
...
## 6. 인사이트 생성 룰
...
```

이 frontmatter만 있으면 본 패키지의 명세를 충족하며, 사이트가 새 룰북을 인식할 준비가 됩니다.

---

## 라이선스 및 저작권

본 패키지의 .md 문서들은 출품작의 일부이며, 코드 또는 데이터의 재사용·수정·재배포는 출처 표기와 함께 허용됩니다. 외부 데이터 출처(pykrx, 네이버 Wisereport, multpl, yfinance)의 사용 정책은 각 출처의 라이선스를 따릅니다.
