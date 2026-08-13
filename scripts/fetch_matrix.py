"""월별 PER + PBR 매트릭스 페치 → data/matrix/{per,pbr}_monthly.json

universe 검증과 점수 계산에 공통 사용.

기본은 **증분**: 기존 파일에 이미 있는 달은 건너뛰고 없는 달만 페치한다.
`--full` 시에만 60개월 전량 재수집.

2026-08-13 사고 이후 필수가 된 안전장치 3종:
  1. 증분 — 전량 재수집(180+ 요청)이 KRX 대량조회 탐지에 걸려 IP가 1일 차단됐다.
  2. throttle + 재시도 — 호출 사이 SLEEP_SEC, 실패 시 백오프 재시도.
  3. write 가드 — 결과가 기존보다 나빠지면 저장 거부. 기존 매트릭스에 **병합**하므로
     일부 달이 실패해도 이미 있던 달은 절대 사라지지 않는다.
     (사고 당시엔 45/60이 실패했는데도 그대로 덮어써서 15개월치가 소실됐다.)
"""
import json
import os
import sys
import time
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


PROJECT = Path(__file__).resolve().parent.parent
MATRIX_DIR = PROJECT / "data" / "matrix"
MATRIX_DIR.mkdir(parents=True, exist_ok=True)

_load_env(PROJECT / ".env")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    sys.stderr.write("[ERROR] KRX_ID / KRX_PW 미설정.\n")
    sys.exit(2)

import pandas as pd
from pykrx import stock

LOOKBACK_MONTHS = 60
SLEEP_SEC = 1.6   # 호출 간 간격. 줄이면 KRX 대량조회 탐지에 걸린다.
MAX_RETRY = 3

PER_PATH = MATRIX_DIR / "per_monthly.json"
PBR_PATH = MATRIX_DIR / "pbr_monthly.json"


def _load_matrix(path: Path) -> dict:
    """기존 매트릭스 {ticker: {date: value}} (없거나 깨졌으면 빈 dict)"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("matrix", {})
    except Exception:
        return {}


def _all_dates(matrix: dict) -> set:
    return {d for dates in matrix.values() for d in dates}


def _fundamental(ds: str, market: str, retry: int = MAX_RETRY):
    """재시도 + 백오프. 최종 실패 시 마지막 예외를 올린다."""
    last = None
    for attempt in range(retry):
        try:
            df = stock.get_market_fundamental_by_ticker(ds, market=market)
            if df is not None and not df.empty and "PER" in df.columns:
                return df
            last = RuntimeError("빈 응답 또는 PER 컬럼 없음 (차단 의심)")
        except Exception as e:
            last = e
        if attempt < retry - 1:
            time.sleep(SLEEP_SEC * (attempt + 2))
    raise last


def _resolve_business_date(d: datetime, max_back: int = 7) -> str:
    for _ in range(max_back):
        ds = d.strftime("%Y%m%d")
        try:
            df = _fundamental(ds, "KOSPI", retry=1)
            if (df["PER"] != 0).any():
                return ds
        except Exception:
            pass
        d -= timedelta(days=1)
        time.sleep(SLEEP_SEC)
    return d.strftime("%Y%m%d")


def fetch(months: int = LOOKBACK_MONTHS, full: bool = False):
    """PER + PBR 매트릭스 페치 (한 번 호출에 둘 다 받음).

    full=False면 기존 매트릭스에 없는 달만 페치해 **병합**한다.
    반환: (per_matrix, pbr_matrix, failed_dates)
    """
    per_matrix = {} if full else _load_matrix(PER_PATH)
    pbr_matrix = {} if full else _load_matrix(PBR_PATH)
    have_months = {d[:6] for d in _all_dates(per_matrix)}

    end_dt = datetime.now()
    targets = []
    for i in range(months):
        targets.append((end_dt - timedelta(days=30 * i)).replace(day=15))
    targets.reverse()

    todo = [t for t in targets if t.strftime("%Y%m") not in have_months]
    print(f"  보유 {len(have_months)}개월 · 페치 대상 {len(todo)}개월", flush=True)
    if not todo:
        print("  → 신규 달 없음 (증분 스킵)", flush=True)
        return per_matrix, pbr_matrix, []

    failed = []
    t0 = time.time()
    for i, target in enumerate(todo):
        ds = _resolve_business_date(target)
        got = False
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = _fundamental(ds, market)
                for ticker, row in df.iterrows():
                    per_matrix.setdefault(ticker, {})[ds] = row["PER"]
                    pbr_matrix.setdefault(ticker, {})[ds] = row["PBR"]
                got = True
            except Exception as e:
                print(f"    [WARN] {ds} {market} 실패: {e}", file=sys.stderr)
            time.sleep(SLEEP_SEC)
        if not got:
            failed.append(ds)
        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (len(todo) - i - 1)
        print(f"  [{i+1:>2}/{len(todo)}] {ds}  경과 {elapsed:.0f}s · ETA {eta:.0f}s",
              flush=True)
    return per_matrix, pbr_matrix, failed


def _trim(matrix: dict, keep: int) -> dict:
    """롤링 윈도우 — 최근 keep개 날짜만 남기고 오래된 달 제거."""
    dates = sorted(_all_dates(matrix))
    if len(dates) <= keep:
        return matrix
    drop = set(dates[:-keep])
    return {t: {d: v for d, v in dd.items() if d not in drop}
            for t, dd in matrix.items()}


def main():
    full = "--full" in sys.argv
    mode = "전체 재수집" if full else "증분"
    print(f"[matrix] PER + PBR 월별 매트릭스 페치 ({LOOKBACK_MONTHS}개월 × 2시장, {mode})\n")

    before = len(_all_dates(_load_matrix(PER_PATH)))
    per_matrix, pbr_matrix, failed = fetch(full=full)

    per_matrix = _trim(per_matrix, LOOKBACK_MONTHS)
    pbr_matrix = _trim(pbr_matrix, LOOKBACK_MONTHS)
    after = len(_all_dates(per_matrix))

    print(f"\n  PER 매트릭스: {len(per_matrix)}개 종목 · {after}개월 (이전 {before}개월)")
    print(f"  PBR 매트릭스: {len(pbr_matrix)}개 종목")

    # write 가드 — 결과가 기존보다 나빠지면 저장하지 않는다
    if after < before:
        sys.stderr.write(
            f"[ERROR] 월 개수 감소 ({before} → {after}). 대량 실패로 판단해 저장하지 않습니다.\n"
            "        기존 파일을 보존합니다. KRX 차단 여부를 먼저 확인하세요.\n")
        sys.exit(1)

    out = {
        "meta": {
            "months": LOOKBACK_MONTHS,
            "ticker_count": len(per_matrix),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        },
        "matrix": per_matrix,
    }
    PER_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    out["matrix"] = pbr_matrix
    out["meta"]["ticker_count"] = len(pbr_matrix)
    PBR_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    print(f"\n  → data/matrix/per_monthly.json")
    print(f"  → data/matrix/pbr_monthly.json")

    if failed:
        sys.stderr.write(
            f"\n[ERROR] 수집 실패 월: {', '.join(failed)}\n"
            "        성공분은 병합 저장했으나 최신 달이 비었을 수 있어 파이프라인을 중단합니다.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
