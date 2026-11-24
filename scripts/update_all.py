"""정량 파이프라인 한 번에 — 서버가 다른 수집은 동시에 돌린다.

    python scripts/update_all.py            # 전체
    python scripts/update_all.py --from 3   # 3단계부터 (수집 생략)

  1  유니버스 1단계           KRX                    ~1분
  2  동시: 일별 시총(KRX) · 분기 재무(dartlab→DART) · 연간 EPS(네이버)
                                                     최초 수십 분, 이후 수 분 (전부 이어받기)
  3  실적 검증(DART) → 컨센서스(네이버) → 일별 PER/PBR → 점수(Top N) → Top N 재무·자료 묶음 → AI 대상 선정
  4  시장 지수 (fetch_kr 는 아직 pykrx — 실패해도 계속)
  5  검증 (verify_data · golden · pytest) — AI 단계 전이면 ai_notes 불일치로 막히는 게 정상

AI 분석(에이전트)·ranker 는 /update-data 문서의 6단계. 그 뒤 `python scripts/ai_stage.py merge` → ranker → `apply-rank`.

한 단계라도 실패하면 멈춘다 — 이후 단계가 옛 데이터로 조용히 계산되는 것을 막는다.
AI 정성 분석은 여기 없다 (/update-data 의 AI 단계).
"""
import argparse, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = {**os.environ, "PYTHONUTF8": "1"}


def run(cmd):
    t = time.time()
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, env=ENV, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-4:])
    print(f"  {'OK ' if r.returncode == 0 else 'ERR'} {cmd[0]:<34} {time.time() - t:6.0f}s\n    "
          + tail.replace("\n", "\n    "), flush=True)
    return r.returncode


def stage(n, title, cmds, parallel=False, fatal=True):
    print(f"\n[{n}] {title}", flush=True)
    if parallel:
        with ThreadPoolExecutor(len(cmds)) as ex:
            codes = list(ex.map(run, cmds))
    else:
        codes = []
        for c in cmds:
            codes.append(run(c))
            if codes[-1]:
                break
    if any(codes) and not fatal:
        print(f"  [WARN] {n}단계 일부 실패 — 계속 진행", flush=True)
    elif any(codes):
        sys.exit(f"\n[STOP] {n}단계 실패 — 위 로그 확인 후 `--from {n}` 으로 이어서 실행")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1)
    a = ap.parse_args()
    t0 = time.time()
    steps = [
        (1, "유니버스 1단계 (KRX 시총 2,000억+ 보통주)", [["scripts/fetch_universe_api.py"]], False, True),
        (2, "수집 — 서버별 동시 실행", [["scripts/fetch_mcap_daily.py"],
                                        ["scripts/fetch_dart_quarterly.py"],
                                        ["scripts/fetch_eps_annual.py"]], True, True),
        (3, "검증·계산", [["scripts/validate_universe_api.py"],
                          ["scripts/fetch_consensus.py"],
                          ["scripts/build_valuation.py"],
                          ["scripts/apply_triple_cross.py"],
                          ["scripts/fetch_financials.py"],
                          ["scripts/build_research_pack.py"],
                          ["scripts/fetch_mezzanine.py"],
                          ["scripts/ai_stage.py", "targets"]], False, True),
        (4, "시장 지수", [["scripts/fetch_kr.py"], ["scripts/fetch_us.py"]], True, False),
        (5, "검증", [["scripts/verify_data.py"], ["scripts/check_golden_matrix.py"],
                     ["-m", "pytest", "tests/", "-q"]], False, True),
    ]
    for n, title, cmds, par, fatal in steps:
        if n >= a.start:
            stage(n, title, cmds, par, fatal)
    print(f"\n완료 · {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
