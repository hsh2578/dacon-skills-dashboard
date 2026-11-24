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
3 실적 검증 → 컨센서스 → 일별 PER/PBR → 점수 Top 30 → Top 30 재무·자료 묶음·메자닌(CB/BW/EB) → **AI 대상 선정** →
4 시장 지수(fetch_kr 는 pykrx — KRX 비밀번호 만료 시 실패해도 계속) → 5 검증.

- 5단계 `verify_data` 가 **"ai_notes 가 현재 Top 에 없는 종목 포함"으로 실패하는 것은 정상** (AI 단계 전).
  그 외 실패는 로그를 보고 `python scripts/update_all.py --from N` 으로 이어서.
- 모든 수집은 이어받기 — 지난 실행 이후 새로 생긴 것만 받는다.
- KRX 로그인 실패("패스워드 변경 필요") → data.krx.co.kr 에서 비밀번호 변경 → 마스터 `Desktop/.env` 의 `KRX_PW` 수정 → `python C:/Users/hsh/Desktop/sync_env.py --apply`.

## 2단계 — AI (`--skip-ai` 면 건너뜀)

> 순서가 중요하다 (2026-11-24 사고: 병합 전 브리핑 10개 유실). **에이전트 → merge → rank_ai → apply-rank → briefs** 순서를 지킬 것.
> `ai_stage.py targets` 는 1단계 끝에서 이미 돌았다 — 재사용 종목은 직전 ai_notes(분석·브리핑·buy_check 전부)가 `_ai/{code}.json` 에 복사돼 있다.

`data/screens/_ai_targets.json` 의 `analyze` 종목마다 Agent(`general-purpose`) **하나가 끝까지**(분석→브리핑→매수 점검). 한 메시지에 최대 10개, `run_in_background`. 프롬프트:

```
작업 폴더: <repo 절대경로>
대상: **{종목명}({코드})** — 저평가 스크리너 Top 30 중 1종목. 오늘은 {YYYY-MM-DD}. 재분석 사유: {why}.
룰 파일을 정독하고 순서대로:
1. .claude/agents/fundamental-analyst.md  2. .claude/agents/risk-analyst.md
3. .claude/agents/resolution-scout.md(1 이후)  4. .claude/agents/synthesizer.md
5. .claude/agents/buy-check.md — premium(과거 밸류의 이유: 해자 4유형/업황/테마/구조적 할인 → 유효·약해짐·사라짐)·margin(durable)·trap(WATCH 는 진행 중 사건만)·매수 이유·날카로운 질문
6. .claude/agents/briefer.md — 브리핑 (§0.5: buy_check 판정과 같은 말, 순위 숫자 금지)
데이터: data/research/{코드}.json(먼저) · data/screens/_top_context.json 의 code 항목(buy_inputs·price) ·
data/financials/{코드}.json · data/mezzanine.json · 지난 판단 data/judgments/latest.json(사실이 바뀔 때만 판정 변경, change_reason) ·
직전 분석 data/screens/_ai/{코드}.json(있으면 참고 후 덮어씀).
WebSearch 는 자료 묶음에 없는 것만, 합계 4~8회. 출처 태그 필수, 이모지 금지. 한국 시장 맥락(지주·중복상장·주주환원·오너·CB/BW·경기순환·테마).
출력: {"code","name","ai_notes":{synthesizer 스키마 + buy_check + briefing, generated_at, model}} 를 data/screens/_ai/{코드}.json 에 Write.
scratchpad 는 scratchpad_{코드}\ 만. 최종 응답 한 줄: "{코드} premium=… durable=… trap=… verdict=…"
```

전부 끝나면 (순서대로):

```bash
python scripts/ai_stage.py merge          # _ai/*.json → ai_notes.json (빠진 종목 있으면 멈춤)
python scripts/rank_ai.py                 # 매수 매력 순위 = (주주이익 수익률 + 재평가) × 확실성 → _ranking.json
python scripts/ai_stage.py apply-rank     # ai_rank·rank_detail 반영 + 판단 기록(data/judgments/)
python scripts/ai_stage.py briefs         # 30종목 모두 briefing 있는지 확인 (없으면 멈춤 → 그 종목 briefer 다시)
python scripts/judgments.py grade         # 지난 판단 채점 (1·3·6·12개월 도래분) — 순위가 실제로 맞았는지
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

마크다운 표: 유니버스 수 · 매수 매력 상위 5 · premium 판정 분포 · trap 분포 · 재분석/재사용 수 ·
채점 결과(있으면) · 검증 결과.
