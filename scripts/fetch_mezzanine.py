"""메자닌(CB·BW·EB) 오버행 — 한국 중소형주 할인의 큰 이유 (2026-11-24).

    python scripts/fetch_mezzanine.py            # triple_cross.json top
    python scripts/fetch_mezzanine.py --codes 237690,080580

DART 주요사항 API(전환사채권·신주인수권부사채권·교환사채권 발행결정)에서 최근 5년 발행분을 받아
'아직 행사 가능하고(행사기간·만기 안 지남) 행사가가 지금 주가의 130% 이하'인 물량의 주식 비중을 더한다.
  · 상한 추정이다 — 발행 뒤 전환·상환·행사가 조정(리픽싱)은 이 API 에 없다. 이미 전환된 분은 주식 수 증가(희석 관문)에도 잡힌다.
  · EB 는 자사주를 내주는 것이라 주식 수는 그대로지만 시장에 풀리는 물량이라 오버행에 넣는다.
출력: data/mezzanine.json  {code: {overhang_pct, items:[…], as_of}}
"""
import argparse, json, os, re, sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import feeds  # noqa: E402

OUT = ROOT / "data" / "mezzanine.json"
KINDS = {"cvbdIsDecsn.json": "CB", "bdwtIsDecsn.json": "BW", "exbdIsDecsn.json": "EB"}
NEAR = 1.3


def _num(v):
    s = re.sub(r"[^\d.\-]", "", str(v or ""))
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def _date(v):
    m = re.findall(r"\d+", str(v or ""))
    try:
        return date(int(m[0]), int(m[1]), int(m[2])) if len(m) >= 3 else None
    except ValueError:
        return None


def fetch(code, corp, price, today):
    items = []
    for ep, kind in KINDS.items():
        j = feeds.dart_json(ep, corp_code=corp, bgn_de=(today - timedelta(days=365 * 5)).strftime("%Y%m%d"),
                            end_de=today.strftime("%Y%m%d"))
        if j.get("status") not in ("000", "013"):
            raise RuntimeError(f"{code} {ep} status={j.get('status')} {j.get('message')}")   # 조용히 0 으로 굳히지 않는다
        for x in j.get("list") or []:
            if kind == "EB":
                # 교환 대상이 다른 회사 주식이면(코오롱인더 EB → 우리금융지주, HD현대 EB → 자회사) 이 회사 물량이 아니다
                tgt, me = str(x.get("extg") or ""), str(x.get("corp_name") or "")
                if tgt and me and me[:2] not in tgt and "자기" not in tgt:
                    continue
            px = _num(x.get("cv_prc") or x.get("ex_prc"))
            pct = _num(x.get("cvisstk_tisstk_vs") or x.get("nstk_isstk_tisstk_vs") or x.get("extg_tisstk_vs"))
            end = _date(x.get("cvrqpd_edd") or x.get("exrqpd_edd") or x.get("expd_edd") or x.get("bd_mtd"))
            mat = _date(x.get("bd_mtd"))
            live = (end is None or end >= today) and (mat is None or mat >= today)
            near = bool(px and price and px <= price * NEAR)
            items.append({"kind": kind, "rcept_no": x.get("rcept_no"), "amount": _num(x.get("bd_fta")), "price": px,
                          "pct_of_shares": pct, "until": str(end) if end else None, "live": live, "near_money": near})
    live = [i for i in items if i["live"] and i["near_money"]]
    over = sum(i["pct_of_shares"] or 0 for i in live)
    # 비율이 공시에 없으면('-') 0 으로 굳히지 않고 표시한다
    return {"overhang_pct": round(over, 2), "unknown_pct": sum(1 for i in live if i["pct_of_shares"] is None), "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes")
    a = ap.parse_args()
    tc = json.load(open(ROOT / "data/screens/triple_cross.json", encoding="utf-8"))
    rows = {r["code"]: r for r in tc["all_ranked"]}
    codes = a.codes.split(",") if a.codes else [r["code"] for r in tc["top"]]
    cm = json.load(open(ROOT / "data/financials/_dart_corpmap.json", encoding="utf-8"))
    doc = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {}
    today = date.today()
    for c in codes:
        if not cm.get(c):
            continue
        d = fetch(c, cm[c], (rows.get(c) or {}).get("current_price"), today)
        doc[c] = {**d, "as_of": today.isoformat()}
        if d["overhang_pct"]:
            print(f"  {c} {(rows.get(c) or {}).get('name', '')} 오버행 {d['overhang_pct']}% "
                  f"({sum(1 for i in d['items'] if i['live'] and i['near_money'])}건)")
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[mezz] {len(codes)}종목 → {OUT}")


if __name__ == "__main__":
    main()
