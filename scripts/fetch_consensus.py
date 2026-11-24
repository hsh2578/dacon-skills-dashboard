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

# 네이버가 스로틀하면 컨센서스가 비어서 돌아온다. 그대로 반영하면 종목이
# universe에서 빠지고, 그 축소된 모집단으로 4팩터가 계산된다 — 조용한 붕괴다.
# 그래서 (a) 직전 값을 승계하고 (b) 총량이 크게 줄면 아예 쓰지 않는다.
CARRY_MAX_DAYS = 14      # 직전 컨센서스를 이 기간까지만 승계한다
MIN_RETAIN_RATIO = 0.80  # 직전 통과 종목 수의 이 비율 미만이면 기록 거부


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

    # 직전 컨센서스 — 이번 페치가 비면 승계 대상
    prev = {s["code"]: s for s in universe_in if s.get("avg_target_price")}
    now = datetime.now()

    def _carry(s):
        """직전 값이 아직 쓸 만하면 그대로 승계. 아니면 None."""
        p = prev.get(s["code"])
        if not p or not p.get("forward_per") or not p.get("avg_target_price"):
            return None
        stamp = p.get("consensus_at")
        if stamp:
            try:
                if (now - datetime.fromisoformat(stamp)).days > CARRY_MAX_DAYS:
                    return None      # 너무 낡았다 — 목표주가가 upside 팩터로 들어간다
            except ValueError:
                return None
        return {**s, **{k: p[k] for k in
                        ("forward_per", "forward_pbr", "forward_eps", "fwd_year",
                         "avg_target_price", "broker_count", "consensus_score")
                        if k in p},
                "consensus_at": stamp, "consensus_carried": True}

    # 분류: forward + target 둘 다 있어야 통과
    final = []
    excluded_no_forward = []
    excluded_no_target = []
    carried = 0

    for s in universe_in:
        code = s["code"]
        consensus = results.get(code) or {}
        fwd_data = consensus.get("forward") or {}
        cons_data = consensus.get("consensus") or {}
        cons_summary = cons_data.get("summary") or {}

        forward_per = fwd_data.get("per_forward")
        target_price = cons_summary.get("avg_target_price")
        ok = (forward_per and forward_per > 0 and target_price and target_price > 0
              and "error" not in consensus)

        if not ok:
            # 이번엔 못 받았다 → 직전 값 승계 시도. 네이버 스로틀 한 번에
            # 종목이 통째로 빠지는 걸 막는다.
            kept = _carry(s)
            if kept:
                final.append(kept)
                carried += 1
                continue
            if "error" in consensus:
                reason = f"FETCH_ERROR: {consensus['error']}"
            elif not forward_per or forward_per <= 0:
                reason = "NO_FORWARD_PER"
            else:
                reason = "NO_TARGET_PRICE"
            (excluded_no_target if reason == "NO_TARGET_PRICE"
             else excluded_no_forward).append({**s, "reason": reason})
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
            "consensus_at": now.isoformat(timespec="seconds"),
            "consensus_carried": False,
        })

    # 총량 가드 — 승계로도 못 메울 만큼 줄었으면 페치 자체가 실패한 것이다.
    # 축소된 모집단으로 4팩터를 돌리면 Top 20이 조용히 엉뚱해진다.
    if prev and len(final) < len(prev) * MIN_RETAIN_RATIO:
        sys.exit(
            f"[ERROR] 컨센서스 통과 {len(final)}종목 — 직전 {len(prev)}종목의 "
            f"{len(final)/len(prev):.0%}로 급감했습니다 (임계 {MIN_RETAIN_RATIO:.0%}).\n"
            f"        네이버 차단·구조 변경일 가능성이 큽니다. universe.json은 "
            f"그대로 두었습니다.\n"
            f"        시간을 두고 다시 실행하거나, naver_consensus.py 파싱을 "
            f"점검하세요.")

    # universe.json 갱신
    base["stocks"] = final
    base["passed"] = final
    base.setdefault("meta", {}).update({
        "final_count": len(final),
        "excluded_no_forward": len(excluded_no_forward),
        "excluded_no_target": len(excluded_no_target),
        "carried_from_previous": carried,
        "consensus_fetched_at": now.isoformat(timespec="seconds"),
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
    print(f"  ├─ 직전 값 승계:         {carried:>4}개"
          + (f"  (이번 페치에서 못 받음, {CARRY_MAX_DAYS}일 이내 값)" if carried else ""))
    print(f"  └─ 최종 universe:        {len(final):>4}개")
    if carried > len(final) * 0.2:
        print(f"\n  [WARN] 승계 비율이 {carried/len(final):.0%}입니다 — 네이버가 "
              f"제대로 응답하지 않고 있을 수 있습니다.", file=sys.stderr)


if __name__ == "__main__":
    main()
