"""KOSPI / KOSDAQ 일별 PER/PBR/배당수익률/지수 종가 → JSON

기본 증분 갱신 (마지막 날짜 - 30일부터 fetch + 신규 일자만 추가).
--full 옵션 시 풀 10년 재수집.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


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


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_env(_PROJECT_ROOT / ".env")

if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    sys.stderr.write(
        "[ERROR] KRX_ID / KRX_PW 환경변수가 설정되지 않았습니다.\n"
        "        프로젝트 루트에 .env 파일을 만들고 KRX 계정을 입력하세요.\n"
        "        참고: .env.example\n"
    )
    sys.exit(2)

import pandas as pd
from pykrx import stock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from incremental import (read_existing, get_incremental_start,  # noqa: E402
                          merge_timeseries, diff_summary)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

INDICES = {"kospi": "1001", "kosdaq": "2001"}
SERIES_FIELDS = ["per", "pbr", "div_yield", "close"]


def _to_list(series, ndigits=2):
    return [None if pd.isna(v) else round(float(v), ndigits) for v in series]


def fetch_index(name: str, code: str, start: str, end: str) -> dict:
    df = stock.get_index_fundamental_by_date(start, end, code).reset_index()
    date_col = df.columns[0]
    df["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

    return {
        "name": name.upper(),
        "ticker": code,
        "frequency": "daily",
        "dates": df["date"].tolist(),
        "per": _to_list(df["PER"]),
        "pbr": _to_list(df["PBR"]),
        "div_yield": _to_list(df["배당수익률"]),
        "close": _to_list(df["종가"]),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="기존 데이터 무시하고 10년 풀 재수집")
    args = ap.parse_args()

    end_dt = datetime.now()
    end = end_dt.strftime("%Y%m%d")

    for name, code in INDICES.items():
        out = DATA_DIR / f"{name}.json"
        existing = None if args.full else read_existing(out)
        start = get_incremental_start(out) if not args.full else \
            (end_dt - timedelta(days=365 * 10 + 30)).strftime("%Y%m%d")

        mode = "FULL" if args.full or existing is None else "INCR"
        print(f"[{name}/{mode}] {start}~{end} fetching...", flush=True)
        new = fetch_index(name, code, start, end)
        merged = merge_timeseries(existing, new, SERIES_FIELDS)

        out.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        s = diff_summary(existing, merged)
        print(f"  → {out.name} ({s['new_count']}건, +{s['added']} added, last {s['new_last']})")


if __name__ == "__main__":
    main()
