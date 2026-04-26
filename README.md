# DACON Skills.md 기반 가치투자 대시보드

DACON 월간 해커톤 "투자 데이터를 시각화하라 - Skills 기반 대시보드 설계" 출품작.

## 컨셉

**역사적 저평가 + 회복 모멘텀 + 미래 이익 성장이 만나는 교차점에 있는 종목을 자동 발굴하는 Skills.md 기반 대시보드.**

- 시가총액 2,000억 이상 1,000여 한국 종목 풀
- 5년 평균 PER/PBR 대비 저평가
- 12개월 선행 PER로 미래 이익 성장 검증 (Value Trap 차단)
- 6개월 PER 회복 모멘텀으로 "급상승 시작점" 포착
- Skills.md 룰북 추가 시 새 카테고리 즉시 등록

## 핵심 시그널: Triple Cross

```
역사적 저평가 (Current PER < 5Y avg PER)
       +
회복 모멘텀 (Current PER > 6M min PER)
       +
미래 이익 성장 (Forward PER < Current PER)
       =
🥇 HIDDEN GEM (5년에 한 번 시그널)
```

## 폴더 구조

```
dacon-skills-dashboard/
├── skills/                # Skills.md 패키지 (제출물)
│   ├── value_recovery_quant.md   # 메인 룰북
│   └── stock_detail/             # 종목 상세 21섹션
├── scripts/               # 데이터 수집·분석 (Python)
├── data/                  # 정적 JSON (커밋, GitHub Pages)
├── web/                   # 프론트엔드 (정적 사이트)
└── docs/                  # 설계 문서
```

## 데이터 흐름

```
[로컬 Python]                  [Git]            [GitHub Pages]
fetch + apply_skills.py  →  data/*.json  commit & push  →  정적 서빙
                                                                ↓
                                                          web/index.html
                                                                ↓ fetch
                                                          data/*.json
```

**백엔드 없음. API 키 노출 없음. 심사자 키 없이 동작.**

## 데이터 출처

| 데이터 | 출처 | 인증 |
|---|---|---|
| 한국 종목 PER/PBR (5Y+) | pykrx | KRX_ID/KRX_PW (로컬) |
| 종가·시총 | FinanceDataReader | 불필요 |
| Forward PER + 컨센서스 | 네이버 Wisereport | 불필요 |
| 재무 지표 (DART) | OpenDART API | API 키 (로컬) |

모든 페치는 로컬에서 수행되고 결과 JSON만 커밋. **사이트 자체는 정적**.

## 일정 (D-17, 2026-04-27 시작)

| 단계 | 마감 |
|---|---|
| 기획서 PDF 제출 | 4/30 09:59 (D-3) |
| Skills.md 제출 | 5/7 09:59 (D-10) |
| 최종 웹 링크 제출 | 5/14 09:59 (D-17) |
| 1차 대중 투표 | 5/14 ~ 5/18 |
| 2차 내부 심사 | 5/18 ~ 5/22 |

## 제출물

1. **기획서 PDF** — 서비스 개요·분석 흐름·대시보드 구성·Skills.md 설계 방향
2. **Skills.md (.zip)** — 메인 룰북 + 보조 룰북 + 21섹션 상세 .md
3. **웹 배포 URL** — GitHub Pages 정적 호스팅
