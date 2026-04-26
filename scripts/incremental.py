"""증분 갱신 헬퍼.

기존 JSON 의 마지막 날짜를 기준으로 신규 fetch 범위와 병합 로직을 제공.
- 매번 (마지막 날짜 - REDO_DAYS) 부터 fetch → 최근 N일 정정 자동 반영
- 새 값이 기존 값보다 우선 (덮어쓰기)
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

REDO_DAYS_DEFAULT = 30


def read_existing(json_path: Path) -> Optional[dict]:
    if not json_path.exists():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_incremental_start(json_path: Path, redo_days: int = REDO_DAYS_DEFAULT,
                           fallback_years: int = 10) -> str:
    """증분 갱신 시작일 (YYYYMMDD).

    기존 데이터 있으면 (마지막 날짜 - redo_days), 없으면 (오늘 - fallback_years년 30일).
    """
    existing = read_existing(json_path)
    if existing and existing.get("dates"):
        last = existing["dates"][-1]
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d")
            return (last_dt - timedelta(days=redo_days)).strftime("%Y%m%d")
        except Exception:
            pass
    return (datetime.now() - timedelta(days=365 * fallback_years + 30)).strftime("%Y%m%d")


def merge_timeseries(old: Optional[dict], new: dict, series_fields: Iterable[str]) -> dict:
    """기존 + 새 시계열 데이터 병합. dates 기준 dict 인덱싱 후 새 값 우선.

    series_fields: 병합할 일자별 배열 필드 (예: ['per', 'pbr', 'close']).
    'dates' 외 비-시계열 필드는 new 의 값으로 그대로 덮어씀.
    """
    if not old or not old.get("dates"):
        return new

    fields = list(series_fields)
    table = {}
    for i, dt in enumerate(old.get("dates", [])):
        row = {}
        for f in fields:
            arr = old.get(f) or []
            row[f] = arr[i] if i < len(arr) else None
        table[dt] = row
    for i, dt in enumerate(new.get("dates", [])):
        row = {}
        for f in fields:
            arr = new.get(f) or []
            row[f] = arr[i] if i < len(arr) else None
        table[dt] = row

    sorted_dates = sorted(table.keys())
    merged = dict(new)
    merged["dates"] = sorted_dates
    for f in fields:
        merged[f] = [table[dt].get(f) for dt in sorted_dates]
    return merged


def regenerate_stocks_manifest(stocks_dir: Path) -> int:
    """data/stocks/ 의 모든 종목 JSON 을 스캔해서 _index.json 매니페스트 생성.

    Returns: 매니페스트에 들어간 종목 수.
    """
    if not stocks_dir.exists():
        return 0

    def _last_non_null(arr):
        if not arr:
            return None
        for v in reversed(arr):
            if v is not None:
                return v
        return None

    items = []
    for p in sorted(stocks_dir.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        per = None
        for v in reversed(d.get("per") or []):
            if v is not None and v > 0:
                per = v
                break
        items.append({
            "code": p.stem,
            "name": d.get("name", p.stem),
            "market": d.get("market", "KR"),
            "per": per,
            "pbr": _last_non_null(d.get("pbr") or []),
            "close": _last_non_null(d.get("close") or []),
            "market_cap": _last_non_null(d.get("market_cap") or []),
            "market_cap_unit": d.get("market_cap_unit", ""),
            "price_unit": d.get("price_unit", ""),
            "fwd_per": (d.get("forward") or {}).get("per_forward"),
            "fwd_year": (d.get("forward") or {}).get("year_estimate"),
            "updated_at": d.get("updated_at"),
        })

    out = stocks_dir / "_index.json"
    out.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return len(items)


def diff_summary(old: Optional[dict], new: dict) -> dict:
    """병합 전 old, 병합 후 new (또는 단순 신규)의 행 수/마지막 날짜 비교."""
    old_n = len(old.get("dates", [])) if old else 0
    old_last = old["dates"][-1] if (old and old.get("dates")) else None
    new_n = len(new.get("dates", []))
    new_last = new["dates"][-1] if new.get("dates") else None
    return {
        "old_count": old_n, "new_count": new_n, "added": new_n - old_n,
        "old_last": old_last, "new_last": new_last,
    }
