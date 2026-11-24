---
description: 월 1회 전체 갱신 — 정량(update_all) + AI 정성 분석(변화 있는 종목만) + 검증 + 커밋
argument-hint: [--skip-ai]
allowed-tools: Bash, Agent, Read, Write, Glob, Grep
---

# /update-data — 월 1회 전체 갱신 (v6, 2026-11-24)

운영 빈도는 **월 1회**. 정량과 AI 를 **같은 날 함께** 돌린다 (같은 시점의 숫자와 판단).

> **폐기된 스크립트를 부르지 말 것.** `fetch_matrix_kis.py`(KIS 재무비율 API 404 — 실행하면 새 매트릭스를
> 옛 KIS 값으로 덮어쓴다) · `fetch_batch_api.py`(옛 `data/stocks/`) · pykrx 계열 종목 스크립트.
> 수집 순서는 `scripts/update_all.py` 한 곳이 소유한다. 이 문서는 그걸 부르고 AI 단계만 더한다.

## 1단계 — 정량 파이프라인 (~5분, 최초 백필은 수십 분)

```bash
python scripts/update_all.py
```

1 유니버스(KRX) → 2 동시 수집(시총·종가 KRX · 분기 재무 dartlab→DART · 연간 EPS 네이버) →
3 실적 검증 → 컨센서스 → 일별 PER/PBR → 점수 Top 30 → Top 30 재무·자료 묶음 → **AI 대상 선정** →
4 시장 지수(fetch_kr 는 pykrx — KRX 비밀번호 만료 시 실패해도 계속) → 5 검증.

- 5단계 `verify_data` 가 **"ai_notes 가 현재 Top 에 없는 종목 포함"으로 실패하는 것은 정상** (AI 단계 전).
  그 외 실패는 로그를 보고 `python scripts/update_all.py --from N` 으로 이어서.
- 모든 수집은 이어받기 — 지난 실행 이후 새로 생긴 것만 받는다.
- KRX 로그인 실패("패스워드 변경 필요") → data.krx.co.kr 에서 비밀번호 변경 → 마스터 `Desktop/.env` 의 `KRX_PW` 수정 → `python C:/Users/hsh/Desktop/sync_env.py --apply`.

## 2단계 — AI 정성 분석 (`--skip-ai` 면 건너뜀)

`data/screens/_ai_targets.json` 을 Read. `analyze` 배열 = 다시 분석할 종목(신규 진입·새 공시/리포트·추정치 ±5%),
`reuse` = 지난 분석 재사용(이미 `data/screens/_ai/{code}.json` 에 복사됨).

`analyze` 종목마다 Agent(`subagent_type=general-purpose`)를 **한 메시지에 최대 10개**, `run_in_background`.
자리가 비면 다음을 띄운다. 프롬프트:

```
작업 폴더: <repo 절대경로>
대상: **{종목명}({코드})** 의 ai_notes JSON 작성 (저평가 스크리너 Top 30 중 1종목). 오늘은 {YYYY-MM-DD}.

룰 파일 4개를 Read로 정독하고 아래 순서대로 수행:
1. .claude/agents/fundamental-analyst.md — 왜 저평가인가 진단 (cause_type, implied_expectations 포함)
2. .claude/agents/risk-analyst.md — 리스크 (PEAK_EARNINGS 조건 확인)
3. .claude/agents/resolution-scout.md — 1에서 진단한 원인이 풀리는지 검증 + expectation_gap 판정 (반드시 1 이후)
4. .claude/agents/synthesizer.md — 통합 (새 verdict 매트릭스)

데이터 (전부 Read):
- 자료 묶음(가장 먼저): data/research/{코드}.json — DART 공시·증권사 리포트·뉴스·텔레그램·추정치 변화
- 정량: data/screens/_top_context.json 에서 code="{코드}" (apply_triple_cross 가 만든다)
- 재무(DART 연간): data/financials/{코드}.json
- 지난 판단: data/judgments/latest.json 에서 code="{코드}" (있으면 resolution-scout §6.5 — 사실이 바뀔 때만 판정 변경, change_reason 필수)

WebSearch는 자료 묶음에 없는 것(업황·글로벌 가격·해외 경쟁사)만 보충, 합계 4~8회.
해소 근거를 못 찾으면 verdict NO_EVIDENCE + 빈 evidence, expectation_gap FAIR. 억지로 채우지 말 것.
모든 정성 항목에 출처 태그([출처: DART · YYYY-MM-DD] / [출처: 리포트 · 증권사 · YYYY-MM] /
[출처: 뉴스 · 언론사 · YYYY-MM] / [출처: WebSearch · YYYY-MM] / 확인 필요), 정량은 [정량]. 이모지 금지.

출력: {"code","name","ai_notes":{… synthesizer 스키마 전체, resolution 은 구조 그대로 …}} 를
Write 도구로 data/screens/_ai/{코드}.json 에 저장. 최종 응답은 한 줄:
"{코드} cause_type=… expectation_gap=… verdict=… info_grade=…"
```

전부 끝나면:

```bash
python scripts/ai_stage.py merge          # _ai/*.json → ai_notes.json (빠진 종목 있으면 멈춤)
```

ranker Agent 1개 (general-purpose): `.claude/agents/ranker.md` 정독 → `ai_notes.json` + `triple_cross.json` top
([정량] 기대 필드) + 필요 시 `data/financials/` → `data/screens/_ranking.json` 에 Write
(`{"ranking":[{code, ai_rank, quant_rank, rerank_score, score_breakdown, rerank_reason}], "ranked_at", "basis"}`).
새 사실 생성·정량 점수 변경 금지, `nature` 는 점수에 쓰지 않는다.

```bash
python scripts/ai_stage.py apply-rank     # ai_rank 반영 + 판단 기록(data/judgments/{날짜}.json, latest.json)
python scripts/judgments.py grade         # 지난 판단 채점 (1·3·6·12개월 도래분)
```

### 2-3. 종목 브리핑 (사람이 읽는 해설)

`analyze` 종목만 (재사용 종목은 직전 브리핑이 ai_notes 에 따라온다). Agent(`general-purpose`) 최대 10개 동시, 프롬프트:
`.claude/agents/briefer.md 정독 후 그대로 따를 것. 대상 {코드} {종목명}. 입력 _ai/{코드}.json · _top_context.json price · research/{코드}.json · financials/{코드}.json. _ai/{코드}.json 에 ai_notes.briefing 만 추가해 Write. written_at={오늘}.`

```bash
python scripts/ai_stage.py briefs         # briefing → ai_notes.json (순위 유지). 빠진 종목이 있으면 멈춘다
```

## 3단계 — 검증

```bash
python scripts/update_all.py --from 5
```

`verify_data`(신선도·커버리지·Top/AI 정합) · `check_golden_matrix`(과거 PER/PBR 불변) · `pytest`.
골든 위반은 원인부터 — 분할·증자로 전 구간 균일 이동은 "참고", 특정 구간만 튀면 회귀.
의도한 변경이면 `python scripts/check_golden_matrix.py --freeze`.

## 4단계 — 커밋 · 배포

사용자 확인 후. `data/.cache/`·`data/screens/_*` 는 커밋하지 않는다(.gitignore). 사이트는 `?t=` 캐시버스터라 push 후 새로고침이면 반영.

## 보고

마크다운 표: 유니버스 수 · Top 30 1위(정량/AI) · 이익 정점 의심 수 · expectation_gap 분포 · 재분석/재사용 수 ·
채점 결과(있으면) · 검증 결과.
