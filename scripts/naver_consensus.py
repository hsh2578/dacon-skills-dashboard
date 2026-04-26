"""네이버 증권 Wisereport에서 Forward PER + 컨센서스 데이터 추출.

출처: navercomp.wisereport.co.kr/v2/company/c1010001.aspx (finsum_more 페이지)
이전 프로젝트(주식 ai 리서치/scripts/naver_finance.py)의 핵심부 포팅.
"""
import io
import requests
import pandas as pd
from typing import Dict

NAVER_WISEREPORT_URL = "https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _to_float(v, default=None):
    if v is None:
        return default
    try:
        s = (str(v).replace(",", "").replace("원", "")
             .replace("%", "").replace("억원", "").strip())
        if s.lower() == "nan":
            return default
        f = float(s)
        if f != f:
            return default
        return f
    except (ValueError, TypeError):
        return default


def _to_int(v, default=None):
    f = _to_float(v, default)
    if f is None:
        return default
    try:
        return int(f)
    except (ValueError, TypeError, OverflowError):
        return default


def _fetch_tables(code: str, timeout: int = 15):
    params = {"cmp_cd": code, "target": "finsum_more"}
    try:
        resp = requests.get(NAVER_WISEREPORT_URL, params=params,
                            headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return pd.read_html(io.StringIO(resp.text),
                            encoding="utf-8", displayed_only=False)
    except Exception:
        return None


def fetch_naver_data(code: str) -> Dict:
    """Wisereport에서 Forward + 컨센서스 한 번에 수집.

    Returns:
        {
          'forward': {year_actual, year_estimate, per_actual, per_forward,
                      pbr_actual, pbr_forward, eps_actual, eps_forward,
                      bps_actual, bps_forward, dps_actual, dps_forward,
                      dividend_yield_actual, dividend_yield_forward, ...},
          'consensus': {
            'summary': {broker_count, avg_target_price, avg_eps_forward,
                        avg_per_forward, consensus_score},
            'brokers': [{broker, date, target_price, prev_target,
                         change_pct, rating}, ...]
          }
        }
        실패 시 빈 forward/consensus 반환.
    """
    out = {"forward": {}, "consensus": {"summary": {}, "brokers": []}}
    tables = _fetch_tables(code)
    if not tables:
        return out

    if len(tables) >= 6:
        try:
            t = tables[5]
            fw = {
                "year_actual": str(t.columns[1]).replace("(A)", "").strip(),
                "year_estimate": str(t.columns[2]).replace("(E)", "").strip(),
            }
            row_map = {
                "PER": ("per_actual", "per_forward"),
                "PBR": ("pbr_actual", "pbr_forward"),
                "PCR": ("pcr_actual", "pcr_forward"),
                "EV/EBITDA": ("ev_ebitda_actual", "ev_ebitda_forward"),
                "EPS": ("eps_actual", "eps_forward"),
                "BPS": ("bps_actual", "bps_forward"),
                "현금DPS": ("dps_actual", "dps_forward"),
                "현금배당수익률": ("dividend_yield_actual", "dividend_yield_forward"),
            }
            for _, row in t.iterrows():
                label = str(row.iloc[0]).strip()
                if label not in row_map:
                    continue
                keys = row_map[label]
                va, ve = _to_float(row.iloc[1]), _to_float(row.iloc[2])
                if va is not None:
                    fw[keys[0]] = va
                if ve is not None:
                    fw[keys[1]] = ve
            out["forward"] = fw
        except Exception:
            pass

    if len(tables) >= 12:
        try:
            t = tables[11]
            if len(t) >= 2:
                row = t.iloc[1]
                out["consensus"]["summary"] = {
                    "broker_count": _to_int(row.iloc[1]),
                    "avg_target_price": _to_int(row.iloc[2]),
                    "avg_eps_forward": _to_int(row.iloc[3]),
                    "avg_per_forward": _to_float(row.iloc[4]),
                    "consensus_score": _to_int(row.iloc[5]),
                }
        except Exception:
            pass

    if len(tables) >= 13:
        try:
            t = tables[12]
            brokers = []
            for idx in range(len(t)):
                row = t.iloc[idx]
                broker = str(row.iloc[0]).strip() if row.iloc[0] else ""
                if not broker or broker in ("제공처", "nan"):
                    continue
                tgt = _to_int(row.iloc[2])
                if not tgt:
                    continue
                brokers.append({
                    "broker": broker,
                    "date": str(row.iloc[1]).strip(),
                    "target_price": tgt,
                    "prev_target": _to_int(row.iloc[3]),
                    "change_pct": _to_float(row.iloc[4]),
                    "rating": str(row.iloc[5]).strip() if len(row) > 5 else "",
                })
            out["consensus"]["brokers"] = brokers
        except Exception:
            pass

    return out


if __name__ == "__main__":
    import json
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "005930"
    print(json.dumps(fetch_naver_data(code), ensure_ascii=False, indent=2))
