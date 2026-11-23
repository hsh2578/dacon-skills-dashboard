"""universe 종목들의 네이버 Wisereport 컨센서스 페치 → universe.json 갱신

ThreadPoolExecutor(3)으로 병렬, 차단 회피용 약간 sleep.
목표가 없는 종목, 내년(FY1) 추정 EPS 없는 종목(EPS 스냅샷 기준)은 universe에서 제외.
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
MIN_TARGET_RATIO = 0.60  # 최종 종목 중 목표가 보유 비율 — 평소 ~90% (2026-11-23 실측: FY1 보유 종목 기준)

# 연간 EPS 스냅샷 (fetch_eps_annual.py). s3 성장 팩터의 원천.
EPS_SNAPSHOT_GLOB = "eps_annual_*.json"
EPS_SNAPSHOT_MAX_DAYS = 14


def forward_eps(eps: dict, today) -> tuple:
    """연간 EPS {'2025/12': x, ...} → (fy0_eps, fwd_eps, basis).

    FY0 = 직전 결산(today.year-1) 실적, FY1/FY2 = 내년·내후년 추정.
      fwd = (FY1 + FY2) / 2, FY2 없으면 FY1.  FY1 없으면 fwd=None → universe 제외.
    연도를 고정하지 않으므로 해가 바뀌면 자동으로 다음 해 추정치로 넘어간다.
    """
    y = today.year
    fy0, fy1, fy2 = (eps.get(f"{y + k}/12") for k in (-1, 1, 2))
    if fy1 is None:
        return fy0, None, None
    if fy2 is None:
        return fy0, fy1, f"{y + 1}E"
    return fy0, (fy1 + fy2) / 2, f"avg({y + 1}E,{y + 2}E)"


def load_eps_snapshot():
    files = sorted((PROJECT / "data" / "consensus").glob(EPS_SNAPSHOT_GLOB))
    if not files:
        sys.exit("[consensus] EPS 스냅샷 없음 — 먼저 python scripts/fetch_eps_annual.py")
    f = files[-1]
    age = (datetime.now() - datetime.strptime(f.stem[-8:], "%Y%m%d")).days
    if age > EPS_SNAPSHOT_MAX_DAYS:
        sys.exit(f"[consensus] EPS 스냅샷이 {age}일 묵음({f.name}) — fetch_eps_annual.py 재실행")
    return f.name, json.loads(f.read_text(encoding="utf-8"))


def fetch_one(code: str) -> tuple:
    try:
        data = fetch_naver_data(code)
        time.sleep(PER_THREAD_DELAY)
        return code, data
    except Exception as e:
        return code, {"error": str(e)[:200]}


def main():
    snap_name, snap = load_eps_snapshot()   # 없거나 묵었으면 페치 전에 멈춘다
    base = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    universe_in = base.get("validated") or base.get("passed") or base.get("stocks") or []   # 단계 키 (2026-11-24): stage1 = 1단계 · validated = 실적 검증 · final(=passed=stocks) = 최종. 각 단계는 자기 키에만 쓴다 — 재실행이 이미 줄어든 목록을 다시 검증하지 않게.

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
        if not p or not p.get("avg_target_price"):
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
        # 2026-11-23 목표가는 점수에서 뺐다 → 목표가 없다고 제외하지 않는다(표시용으로만 저장).
        # 유니버스 판정은 아래 EPS 스냅샷(FY1)이 맡는다.
        if not (target_price and target_price > 0) or "error" in consensus:
            # 못 받았으면 직전 값 승계(표시용 목표가 유지). 없으면 목표가 없이 통과.
            kept = _carry(s)
            if kept:
                final.append(kept)
                carried += 1
                continue
            if "error" in consensus:
                excluded_no_forward.append({**s, "reason": f"FETCH_ERROR(목표가만 없음): {consensus['error']}"})
            else:
                excluded_no_target.append({**s, "reason": "NO_TARGET_PRICE(통과, 표시만 없음)"})
            final.append({**s, "avg_target_price": None, "broker_count": None,
                          "consensus_at": now.isoformat(timespec="seconds"), "consensus_carried": False})
            continue

        final.append({
            **s,
            "forward_per": round(forward_per, 2) if forward_per else None,
            "forward_pbr": fwd_data.get("pbr_forward"),
            "forward_eps": fwd_data.get("eps_forward"),
            "fwd_year": fwd_data.get("year_estimate"),
            "avg_target_price": int(target_price) if target_price else None,
            "broker_count": cons_summary.get("broker_count"),
            "consensus_score": cons_summary.get("consensus_score"),
            "consensus_at": now.isoformat(timespec="seconds"),
            "consensus_carried": False,
        })

    # FY1(내년) 추정 EPS 없으면 제외 — s3 성장 팩터를 계산할 수 없다.
    kept, excluded_no_fy1 = [], []
    for s in final:
        eps = (snap.get(s["code"]) or {}).get("eps") or {}
        fy0, fwd, basis = forward_eps(eps, now)
        if not fwd or fwd <= 0:
            excluded_no_fy1.append({**s, "reason": "NO_FY1_EPS" if fwd is None else "FWD_EPS_NONPOSITIVE"})
            continue
        kept.append({**s, "fy0_eps": fy0, "fwd_eps": round(fwd, 2),
                     "fwd_basis": basis, "eps_snapshot": snap_name})
    final = kept

    # 목표가 보유율 가드 (2026-11-24) — 목표가를 표시용으로 바꾸자 스로틀이 '종목 탈락'이 아니라
    # '목표가만 조용히 빔'으로 바뀌었다 (실측: 283종목 중 29개만 보유). 보유율이 낮으면 기록 거부.
    with_target = sum(1 for s in final if s.get("avg_target_price"))
    if final and with_target < len(final) * MIN_TARGET_RATIO:
        sys.exit(f"[ERROR] 목표가 보유 {with_target}/{len(final)} ({with_target/len(final):.0%}) — "
                 f"임계 {MIN_TARGET_RATIO:.0%} 미만. 네이버 스로틀 의심. universe.json 그대로 둠. 잠시 뒤 재실행.")

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
        "excluded_no_fy1_eps": len(excluded_no_fy1),
        "eps_snapshot": snap_name,
        "carried_from_previous": carried,
        "consensus_fetched_at": now.isoformat(timespec="seconds"),
    })
    base.setdefault("excluded", {}).update({
        "no_forward_per": excluded_no_forward,
        "no_target_price": excluded_no_target,
        "no_fy1_eps": excluded_no_fy1,
    })

    UNIVERSE.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  === 컨센서스 검증 결과 ===")
    print(f"  입력 universe:           {len(universe_in):>4}개")
    print(f"  ├─ 조회 실패:            {len(excluded_no_forward):>4}개")
    print(f"  ├─ 목표가 없음(통과):    {len(excluded_no_target):>4}개")
    print(f"  ├─ 내년 EPS 추정 없음:   {len(excluded_no_fy1):>4}개  ({snap_name})")
    print(f"  ├─ 직전 값 승계:         {carried:>4}개"
          + (f"  (이번 페치에서 못 받음, {CARRY_MAX_DAYS}일 이내 값)" if carried else ""))
    print(f"  └─ 최종 universe:        {len(final):>4}개")
    if carried > len(final) * 0.2:
        print(f"\n  [WARN] 승계 비율이 {carried/len(final):.0%}입니다 — 네이버가 "
              f"제대로 응답하지 않고 있을 수 있습니다.", file=sys.stderr)


if __name__ == "__main__":
    main()
