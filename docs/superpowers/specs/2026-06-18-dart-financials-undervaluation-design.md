# DART 재무 기반 "저평가 진단" 강화 — 설계

**작성일**: 2026-06-18
**상태**: 승인됨 (구현 착수)
**북극성**: ① 저평가 *이유*를 정확히 찾는다 ② 저평가 *해소 순위*를 잘 매긴다. DART 공식 재무가 이 둘의 공통 데이터 토대.

## 1. 배경 / 문제

현재 AI 정성 레이어(fundamental-analyst → risk-analyst → synthesizer → ranker)는 PER/PBR 정량 시그널 + **WebSearch 내러티브**에만 의존한다. "왜 싼가"(`undervaluation_cause.nature`: TEMPORARY/STRUCTURAL)와 Value Trap 판별(ranker §4.3)이 검색 기반 서술로만 결정돼, 실제 이익 궤적이라는 **객관 근거**가 빠져 있다.

OpenDART(전자공시 공식 API)로 매출·영업이익·순이익 5년 추세를 붙이면:
- "싼 게 정당한가(이익 무너지는 중 = 구조적 함정)/일시적인가(이익 멀쩡 = 기회)"를 **데이터로** 판정
- 출처가 `[출처: DART · YYYY]` 공식 공시로 격상 → 환각 위험↓, 심사 설득력↑
- 정적 호스팅·출처 태그 원칙과 정합 (API 키 노출 없음, 사전 페치 후 JSON commit)

**데이터 소스 결정**: FnGuide 크롤링 대신 **OpenDART API** 채택. 스크래핑 취약성을 늘리지 않고, 공식 출처라 태그 원칙에 맞음. (키 동작 검증 완료: `fnlttSinglAcnt.json` status 000.)

## 2. 아키텍처

기존 흐름 유지: `[로컬 Python] → data/*.json commit → GitHub Pages → 정적 사이트`

```
scripts/fetch_financials.py (신규, OpenDART)
  ├─ code→corp_code 매핑: corpCode.xml 1회 다운로드 → data/_dart_corpmap.json 캐시
  ├─ 주요계정 API(fnlttSinglAcnt.json): 최근 2개 사업보고서(reprt_code=11011)
  │     · 각 보고서가 당기/전기/전전기 3개년 반환 → 2개 보고서로 5~6년 커버
  ├─ 매출액·영업이익·당기순이익 추출 (CFS 우선, OFS 폴백)
  ├─ 영업이익률·순이익률 계산
  └─ data/financials/{code}.json commit
```

## 3. Phase 분해 (작동 코어를 안전하게 건드리는 순서)

### Phase 1 — DART 재무 토대 (데이터만) ◀ 본 스펙의 구현 대상

UI·분석 룰 변경 없음. 단독 실행·검증 가능.

**3.1 corp_code 매핑**
- `https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=KEY` → zip(zip 내 CORPCODE.xml) 다운로드·파싱
- `{stock_code: corp_code}` 딕셔너리 → `data/_dart_corpmap.json` 캐시 (이미 있으면 재사용, `--refresh-corpmap`으로 강제 갱신)
- stock_code(6자리)가 있는 상장사만 매핑 대상

**3.2 재무 페치**
- 대상: 우선 **Top 10** (`data/screens/triple_cross.json`의 top 배열 code). 풀데이터 티어와 일치.
- 호출: `fnlttSinglAcnt.json?corp_code=&bsns_year=&reprt_code=11011` — 최근 2개 사업연도(예: 2025, 2022)로 5~6년 확보
- 계정 추출 (account_nm 매칭, fs_div=CFS 우선):
  - 매출액: `매출액` / `수익(매출액)` / (금융사) `영업수익`
  - 영업이익: `영업이익` / `영업이익(손실)`
  - 당기순이익: `당기순이익` / `당기순이익(손실)`
  - 값은 `thstrm_amount`(당기)·`frmtrm_amount`(전기)·`bfefrmtrm_amount`(전전기) 사용 → 연도별 시계열로 병합·중복 제거
- 마진: op_margin = 영업이익/매출, net_margin = 순이익/매출 (매출 0/음수면 null)
- 분기(선택): 최근 분기 보고서(11013/11012/11014) 1건으로 직전 분기 스냅샷 — Phase 1에서는 연간만 필수, 분기는 가능하면 포함

**3.3 출력 스키마** `data/financials/{code}.json`
```json
{
  "code": "035720",
  "corp_code": "00258801",
  "source": "OpenDART",
  "fetched_at": "ISO8601",
  "unit": "원",
  "annual": [
    {"year": 2021, "revenue": ..., "op_income": ..., "op_margin": ..., "net_income": ..., "net_margin": ..., "fs_div": "CFS"}
  ],
  "latest_quarter": {"period": "2026-1Q", "revenue": ..., "op_income": ..., "op_margin": ..., "net_income": ..., "net_margin": ..., "fs_div": "CFS"} 
}
```
- `annual`은 연도 오름차순. 결측 연도는 배열에서 생략(억지 0 금지).

**3.4 파이프라인 통합**
- `/update-data` 신규 단계: Top 10 점수 추출(4단계) 직후, AI 분석(6단계) 직전에 `fetch_financials.py` 실행. (AI가 재무를 입력으로 쓰는 Phase 2 대비 위치)
- `.claude/commands/update-data.md` 갱신
- `verify_data.py` 검증룰 추가: Top 10 financials 파일 존재 + `annual` 비어있지 않음 + revenue non-null 비율 임계값(≥ 80%, 적자/금융사 자연 결측 고려). 위반 시 exit 1.

**3.5 환경/규칙**
- 키는 `.env`의 `DART_API_KEY`에서만 로드. 절대 commit·로그 출력 금지.
- Windows 한글: `PYTHONUTF8=1` + `sys.stdout.reconfigure(encoding="utf-8")`.
- OpenDART rate limit(20k/day) 내. Top 10×2~3콜 = 충분히 여유. 요청 간 짧은 sleep.
- 에러: status≠000(예: 013 무데이터, 020 한도초과)면 해당 종목 스킵·경고 로그, 파이프라인 중단 안 함(재무 없는 종목은 financials 파일 미생성 → verify 임계값으로 관리).

### Phase 2 — 재무가 진단을 뒷받침 (목표 직결, 별도 스펙)
- `fundamental-analyst`: `data/financials/{code}.json`을 Read 입력으로 추가. 영업이익률 5년 추세를 근거로 `undervaluation_cause.nature` 판정 ("OP마진 N년 연속 하락 = STRUCTURAL" / "단기 1개 분기 부진, 추세 유지 = TEMPORARY"). 해당 항목 출처 `[출처: DART · YYYY]`.
- `ranker §4.3`: 마진 추세 하락 → STRUCTURAL 강화 / 안정·회복 → TEMPORARY 지지. 데이터 기반 Value Trap 판별. `.claude/agents/ranker.md`·`skills/agents/portfolio_ranker.md` 양쪽 갱신 + PDF·zip 재생성.

### Phase 3 — 상세페이지 UI (별도 스펙)
- `stock.html`/`stock.js`: 재무 추이 미니차트(매출 bar + OP마진 line, Plotly) + **숏논거↔반박 쌍**(undervaluation_cause+risks = 숏 논거 / investment_points = 반박) + **Watch 모니터링 지표** 3개(기존 촉매·리스크·재무에서 파생, 신규 사실 금지).

## 4. 비범위 (YAGNI)
- KIS/KIWOOM 실시간 API (정적 대시보드라 불필요, DART+KRX와 중복)
- KRX 공식 API 전환(견고성 리팩터) — 별개 작업, 본 설계와 분리
- FRED/BOK 거시 보강 — 코어 목표 아님
- DCF/내재가치, Porter 5 Forces, 내부자·헤지펀드 — 데이터 없음·환각 위험, 텐배거 프롬프트에서 의도적 제외

## 부록 — 후속 API 확장 결정 (2026-06-18 추가)

Phase 1~3 완료 후 세 가지 후속을 검토, 실현가능성 검증 후 결정:

- **universe 전체 재무 (채택)**: `fetch_financials.py --universe`로 303종목 페치. UI는 재무 차트를 AI 카드 밖 독립 `#fin-section`으로 분리해 검색→상세의 모든 종목이 표시. `/update-data`는 Top 10만, universe는 주1회 별도 실행.
- **KRX 공식 OpenAPI 전환 (기각)**: 검증 결과 OpenAPI(`AUTH_KEY`, data-dbg.krx.co.kr)는 시세·시총·기본정보만 제공하고 **PER/PBR 미제공**(엔드포인트 404, 기본정보 필드에 없음). PER/PBR/배당은 data.krx.co.kr 마켓플레이스 웹 보드 전용 = pykrx가 로그인 스크래핑하는 데이터. 전환 시 핵심 손실 + pykrx는 안정적이라 동기 약함 → **스킵**. `KRX_ID`/`KRX_PW` 계속 필수.
- **FRED S&P 보강 (부분 채택)**: FRED는 S&P 가격지수만, PER/PBR 미제공. → 종가만 FRED(공식) 우선·yfinance 폴백(`_fetch_fred_sp500_monthly`, `meta.close_source`). PER/PBR/배당은 multpl 유지.

## 5. 성공 기준 (Phase 1)
- `python scripts/fetch_financials.py` 실행 시 Top 10 중 정상 상장사 전부 `data/financials/{code}.json` 생성, 각 `annual` ≥ 3개년, revenue/op_income/net_income·마진 계산됨.
- `verify_data.py` 통과.
- `/update-data` 신규 단계가 순서대로 동작.
- 키·시크릿 미노출.
