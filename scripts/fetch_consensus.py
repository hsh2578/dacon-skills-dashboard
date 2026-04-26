"""universe 종목들의 네이버 Wisereport 컨센서스 페치 → universe.json 갱신

ThreadPoolExecutor(3)으로 병렬, 차단 회피용 약간 sleep.
컨센서스 없는 종목 (forward_per 또는 avg_target_price 미존재)은 universe에서 제외.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT / "scripts"
UNIVERSE = PROJECT / "data" / "universe.json"

sys.path.insert(0, str(SCRIPT_DIR))


def _load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_env(PROJECT / ".env")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from naver_consensus import fetch_naver_data  # noqa: E402

CONCURRENT_WORKERS = 3
PER_THREAD_DELAY = 0.2  # 스레드 내 sleep (네이버 차단 회피)


def fetch_one(code: str) -> tuple:
    try:
        data = fetch_naver_data(code)
        time.sleep(PER_THREAD_DELAY)
        return code, data
    except Exception as e:
        return code, {"error": str(e)[:200]}


def main():
    base = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    universe_in = base.get("passed") or base.get("stocks") or []

    print(f"[consensus] {len(universe_in)}개 종목 네이버 페치 시작 "
          f"(ThreadPool {CONCURRENT_WORKERS}, sleep {PER_THREAD_DELAY}s)")

    results = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as ex:
        futures = {ex.submit(fetch_one, s["code"]): s for s in universe_in}
        for i, fut in enumerate(as_completed(futures), 1):
            code, data = fut.result()
            results[code] = data
            if i % 30 == 0 or i == len(universe_in):
                elapsed = time.time() - t0
                eta = (elapsed / i) * (len(universe_in) - i)
                print(f"  [{i:>3}/{len(universe_in)}] 경과 {elapsed:.0f}s · ETA {eta:.0f}s",
                      flush=True)

    print(f"\n  페치 완료: {time.time() - t0:.0f}s")

    # 분류: forward + target 둘 다 있어야 통과
    final = []
    excluded_no_forward = []
    excluded_no_target = []

    for s in universe_in:
        code = s["code"]
        consensus = results.get(code) or {}
        if "error" in consensus:
            excluded_no_forward.append({**s, "reason": f"FETCH_ERROR: {consensus['error']}"})
            continue

        fwd_data = consensus.get("forward") or {}
        cons_data = consensus.get("consensus") or {}
        cons_summary = cons_data.get("summary") or {}

        forward_per = fwd_data.get("per_forward")
        target_price = cons_summary.get("avg_target_price")

        if not forward_per or forward_per <= 0:
            excluded_no_forward.append({**s, "reason": "NO_FORWARD_PER"})
            continue
        if not target_price or target_price <= 0:
            excluded_no_target.append({**s, "reason": "NO_TARGET_PRICE"})
            continue

        final.append({
            **s,
            "forward_per": round(forward_per, 2),
            "forward_pbr": fwd_data.get("pbr_forward"),
            "forward_eps": fwd_data.get("eps_forward"),
            "fwd_year": fwd_data.get("year_estimate"),
            "avg_target_price": int(target_price) if target_price else None,
            "broker_count": cons_summary.get("broker_count"),
            "consensus_score": cons_summary.get("consensus_score"),
        })

    # universe.json 갱신
    base["stocks"] = final
    base["passed"] = final
    base.setdefault("meta", {}).update({
        "final_count": len(final),
        "excluded_no_forward": len(excluded_no_forward),
        "excluded_no_target": len(excluded_no_target),
        "consensus_fetched_at": datetime.now().isoformat(timespec="seconds"),
    })
    base.setdefault("excluded", {}).update({
        "no_forward_per": excluded_no_forward,
        "no_target_price": excluded_no_target,
    })

    UNIVERSE.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  === 컨센서스 검증 결과 ===")
    print(f"  입력 universe:           {len(universe_in):>4}개")
    print(f"  ├─ Forward PER 없음:     {len(excluded_no_forward):>4}개")
    print(f"  ├─ 목표가 없음:          {len(excluded_no_target):>4}개")
    print(f"  └─ 최종 universe:        {len(final):>4}개")


if __name__ == "__main__":
    main()
