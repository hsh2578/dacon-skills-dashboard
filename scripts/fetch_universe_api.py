"""universe 1단계 재구축 — KRX 공식 OpenAPI (pykrx 대체)

기존 `fetch_universe.py`는 pykrx(data.krx.co.kr 스크래핑) 기반이라 2026-08-13
IP 차단을 유발했다. 이 스크립트는 KRX 공식 OpenAPI만 쓴다.

동일성 검증 완료(2026-08-13): 기준일 20260424로 돌렸을 때 1단계 통과 816종목으로
기존 universe.json 기록과 정확히 일치했고, 종목별 시가총액도 비율 1.000으로 동일했다.

필터 (기존 룰 그대로)
    시가총액 >= MIN_MARKET_CAP_억 (기본 2,000억)
    보통주만 — 종목코드 끝자리 0 (우선주는 5/7/9)
    스팩·리츠 이름 패턴 제외

출력은 기존 fetch_universe.py와 같은 스키마로 data/universe.json에 쓴다
(stocks / passed / excluded / meta). 후속 단계(5Y 검증·컨센서스)가 그대로 이어진다.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "universe.json"

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


sys.path.insert(0, str(Path(__file__).resolve().parent))
from feeds import krx, short_code  # noqa: E402,F401
from ttm import amount as _amt  # noqa: E402

MIN_MARKET_CAP_억 = 2000

SPAC_PATTERN = re.compile(r"스팩|SPAC|기업인수목적", re.IGNORECASE)
REIT_PATTERN = re.compile(r"리츠|REIT|부동산투자", re.IGNORECASE)


def resolve_business_date(max_back: int = 10):
    """가장 최근 영업일. KRX OpenAPI는 T+1이라 오늘 데이터는 보통 없다."""
    d = datetime.now()
    for _ in range(max_back):
        ds = d.strftime("%Y%m%d")
        try:
            if krx("sto/stk_bydd_trd", ds):
                return ds
        except Exception as e:
            print(f"  [WARN] {ds}: {e}", file=sys.stderr)
        d -= timedelta(days=1)
    return None


def collect(bas_dd: str):
    rows = []
    for svc, market in (("sto/stk_bydd_trd", "KOSPI"), ("sto/ksq_bydd_trd", "KOSDAQ")):
        for r in krx(svc, bas_dd):
            cap = _amt(r.get("MKTCAP"))
            close = _amt(r.get("TDD_CLSPRC"))
            if cap is None:
                continue
            rows.append({
                "code": short_code(r["ISU_CD"]),
                "name": (r.get("ISU_NM") or "").strip(),
                "market": market,
                "market_cap_억": round(cap / 100_000_000, 1),
                "close": close,
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-cap", type=int, default=MIN_MARKET_CAP_억,
                    help=f"최소 시가총액(억원, 기본 {MIN_MARKET_CAP_억})")
    ap.add_argument("--date", default=None, help="기준일 YYYYMMDD (기본: 최근 영업일)")
    ap.add_argument("--dry-run", action="store_true", help="파일 쓰지 않고 결과만 출력")
    args = ap.parse_args()

    bas_dd = args.date or resolve_business_date()
    if not bas_dd:
        sys.exit("[ERROR] 영업일 확인 실패")
    print(f"[universe] KRX 공식 OpenAPI · 기준일 {bas_dd} · 시총 {args.min_cap:,}억+\n")

    rows = collect(bas_dd)
    print(f"  전 종목 {len(rows)}")

    universe, ex_pref, ex_spac, ex_reit = [], [], [], []
    below = 0
    for r in rows:
        if (r["market_cap_억"] or 0) < args.min_cap:
            below += 1
            continue
        if r["code"][-1] != "0":
            ex_pref.append(r)
            continue
        if SPAC_PATTERN.search(r["name"]):
            ex_spac.append(r)
            continue
        if REIT_PATTERN.search(r["name"]):
            ex_reit.append(r)
            continue
        universe.append(r)

    universe.sort(key=lambda x: -(x["market_cap_억"] or 0))
    print(f"  시총 미달 제외 {below}")
    print(f"  우선주 {len(ex_pref)} · 스팩 {len(ex_spac)} · 리츠 {len(ex_reit)} 제외")
    print(f"  → 1단계 통과 {len(universe)}종목")
    print(f"     상위: {', '.join(r['name'] for r in universe[:5])}")

    if args.dry_run:
        print("\n  (--dry-run: 파일 미기록)")
        return

    prev_meta = {}
    if OUT.exists():
        try:
            prev_meta = json.loads(OUT.read_text(encoding="utf-8")).get("meta", {})
        except Exception:
            pass

    out = {
        "meta": {
            **{k: v for k, v in prev_meta.items()
               if k in ("validation",)},  # 후속 단계가 덮어쓸 항목만 보존
            "min_market_cap_억": args.min_cap,
            "source": "KRX 공식 OpenAPI (data-dbg.krx.co.kr)",
            "base_date": bas_dd,
            "filter_excluded": {
                "preferred": len(ex_pref),
                "reit": len(ex_reit),
                "spac": len(ex_spac),
            },
            "count": len(universe),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "price_reference_date": bas_dd,
            "price_updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "stocks": universe,
        "passed": universe,
        "excluded": {
            "preferred": ex_pref,
            "reit": ex_reit,
            "spac": ex_spac,
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n  → {OUT.relative_to(ROOT)}")
    print("  ※ 다음 단계: 5Y PER 검증 → 컨센서스(Forward PER·목표주가)")


if __name__ == "__main__":
    main()
