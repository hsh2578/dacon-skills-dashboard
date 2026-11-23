"""AI 판단 기록 → 나중에 실제 수익률로 채점. (ai-hedge-fund 의 horizon 채점 · ai-berkshire thesis-tracker 참고)

    python scripts/judgments.py record     # ai_notes.json + 당일 시총을 data/judgments/{YYYYMMDD}.json 으로, latest.json 갱신
    python scripts/judgments.py grade      # 기록마다 1·3·6·12개월 뒤 수익률 → 그룹별 평균 (도래한 구간만)

왜: AI 단계(ai_rank·expectation_gap)는 웹 근거 기반이라 과거로 되돌려 백테스트할 수 없다.
    앞으로의 판단을 쌓아 채점하는 것이 AI 단계가 도움이 되는지 확인하는 유일한 방법이다.
    latest.json 은 다음 실행에서 resolution-scout 의 `previous` 입력이 된다(사실이 바뀔 때만 판정 변경).

수익률은 시총 비율(보통주+우선주가 아니라 해당 보통주 시총) — 분할·병합에 안전, 증자 희석은 반영 안 됨.
"""
import json, os, sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
J = ROOT / "data" / "judgments"
MCAP = ROOT / "data" / ".cache" / "_krx_mcap_daily.json"
HORIZONS = {"1m": 30, "3m": 91, "6m": 182, "12m": 365}


def _mcap():
    mc = json.load(open(MCAP, encoding="utf-8"))
    return mc, sorted(d for d, v in mc.items() if v)


def record(date=None):
    """date(YYYYMMDD)를 주면 그날 이전 마지막 거래일 시총으로 소급 기록 (latest.json 은 건드리지 않음)."""
    ai = json.load(open(ROOT / "data/screens/ai_notes.json", encoding="utf-8"))
    mc, days = _mcap()
    d0 = max(d for d in days if d <= date) if date else days[-1]
    rows = []
    for it in ai["items"]:
        n, r = it.get("ai_notes", {}), (it.get("ai_notes", {}).get("resolution") or {})
        uc = n.get("undervaluation_cause") or {}
        rows.append({"code": it["code"], "quant_rank": it.get("quant_rank"), "ai_rank": it.get("ai_rank"),
                     "cause_type": uc.get("cause_type"), "nature": uc.get("nature"),
                     "expectation_gap": r.get("expectation_gap"), "verdict_res": r.get("verdict"),
                     "verdict": n.get("verdict"), "evidence": r.get("evidence"),
                     "mcap0": mc[d0].get(it["code"])})
    doc = {"date": d0, "recorded_at": datetime.now().isoformat(timespec="seconds"), "items": rows}
    J.mkdir(parents=True, exist_ok=True)
    for p in (J / f"{d0}.json",) + (() if date else (J / "latest.json",)):
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[judgments] {d0} · {len(rows)}종목 기록")


def grade():
    from datetime import datetime as dt
    mc, days = _mcap()
    last = dt.strptime(days[-1], "%Y%m%d")
    groups = {}
    for p in sorted(J.glob("2*.json")):
        doc = json.load(open(p, encoding="utf-8"))
        d0 = dt.strptime(doc["date"], "%Y%m%d")
        for h, n in HORIZONS.items():
            if (last - d0).days < n:
                continue
            target = min((d for d in days if (dt.strptime(d, "%Y%m%d") - d0).days >= n), default=None)
            for it in doc["items"]:
                m0, m1 = it.get("mcap0"), (mc.get(target) or {}).get(it["code"])
                if not (m0 and m1):
                    continue
                ret = m1 / m0 - 1
                for key in (f"all", f"gap={it.get('expectation_gap')}", f"cause={it.get('cause_type')}",
                            f"ai_top10={bool(it.get('ai_rank') and it['ai_rank'] <= 10)}"):
                    groups.setdefault((h, key), []).append(ret)
    if not groups:
        print("[judgments] 아직 채점할 구간이 없습니다 (가장 이른 기록 + 1개월 이후부터).")
        return
    for (h, key), v in sorted(groups.items()):
        print(f"  {h:>3} {key:<32} n={len(v):>3}  평균 {sum(v) / len(v):+.2%}")
    print("  ※ 표본이 작을 때는 방향만 볼 것. 수치를 단정하지 말 것.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "grade"
    record(*sys.argv[2:3]) if cmd == "record" else grade()
