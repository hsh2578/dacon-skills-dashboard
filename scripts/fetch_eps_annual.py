"""universe 종목(1단계 통과 stocks, 없으면 passed)의 연간 EPS 실적·추정치(FY-2 ~ FY+2)를 네이버 Wisereport에서 받아 날짜별 스냅샷으로 저장.

    python scripts/fetch_eps_annual.py            # data/consensus/eps_annual_YYYYMMDD.json
같은 날 다시 돌리면 받은 종목은 건너뛴다(이어받기). 날짜별로 남기므로 추정치 변화 추적에 쓸 수 있다.
"""
import io, json, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "consensus" / f"eps_annual_{date.today():%Y%m%d}.json"
BASE = "https://navercomp.wisereport.co.kr/v2/company"
H = {"User-Agent": "Mozilla/5.0"}
WORKERS, DELAY = 3, 0.2   # fetch_consensus.py 와 같은 강도 (2026-11-23 458종목 97초, 실패 0)
_local = threading.local()


def fetch(code):
    """{'2024/12': eps, ..., '2028/12': eps|None} — 열 이름의 (E)는 키에서 떨어지므로 추정 여부는 연도로 판단."""
    if not hasattr(_local, "s"):          # 스레드마다 세션 하나
        _local.s = requests.Session()
    s = _local.s
    p = s.get(f"{BASE}/c1010001.aspx", params={"cmp_cd": code}, headers=H, timeout=15).text
    enc = re.search(r"encparam\s*:\s*'([^']+)'", p).group(1)
    cid = re.search(r"id\s*:\s*'([^']+)'", p)
    r = s.get(f"{BASE}/ajax/cF1001.aspx", timeout=15,
              params={"cmp_cd": code, "fin_typ": 0, "freq_typ": "Y", "encparam": enc,
                      "id": cid.group(1) if cid else ""},
              headers={**H, "Referer": f"{BASE}/c1010001.aspx?cmp_cd={code}"})
    df = pd.read_html(io.StringIO(r.text))[1]
    years = [str(c[-1] if isinstance(c, tuple) else c)[:7] for c in df.columns]
    row = df[df.iloc[:, 0].astype(str).str.startswith("EPS")].iloc[0]
    return {y: (None if pd.isna(v) else float(v)) for y, v in zip(years[1:], row.iloc[1:])}


def main():
    doc = json.load(open(ROOT / "data/universe.json", encoding="utf-8"))
    uni = doc.get("stage1") or doc.get("stocks") or doc["passed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {}
    todo = [st for st in uni if st["code"] not in done or "error" in done[st["code"]]]
    print(f"[eps] {len(todo)}종목 (보유 {len(uni) - len(todo)}) · 스레드 {WORKERS}")

    def one(st):
        try:
            r = {"name": st["name"], "mcap": st["market_cap_억"], "eps": fetch(st["code"])}
        except Exception as e:
            r = {"name": st["name"], "mcap": st["market_cap_억"], "error": repr(e)[:120]}
        time.sleep(DELAY)
        return st["code"], r

    with ThreadPoolExecutor(WORKERS) as ex:
        for i, (c, r) in enumerate(ex.map(one, todo), 1):
            done[c] = r
            if i % 50 == 0:
                print(f"  [{i}/{len(todo)}]", flush=True)
                OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    err = sum("error" in v for v in done.values())
    print(f"DONE {len(done)} · 오류 {err} → {OUT}")
    if err > len(done) * 0.1:
        sys.exit("[ERROR] 오류 10% 초과 — 네이버 스로틀 의심. 잠시 뒤 다시 실행하면 오류 종목만 다시 받는다.")


if __name__ == "__main__":
    main()
