"""월별 PER/PBR 매트릭스 (TTM 기준) — KRX 공식 OpenAPI + KIS 재무비율

pykrx 스크래핑을 대체하는 공식 경로. 2026-08-13 KRX IP 차단 이후 전환.

■ 산식
    PER = 당일 종가 / TTM EPS      (최근 4개 분기 합산 주당순이익)
    PBR = 당일 종가 / BPS          (최근 공시된 주당순자산)

■ KRX 표시값과 다르다 (의도된 차이)
    KRX/네이버 PER은 **직전 확정 결산** 기준이라 연 1회(5월)만 갱신된다.
    2026-08-13 실측으로 확인: 58개월 오차표에서 4월→5월에만 계단이 있고
    8월(반기)·11월(3분기)엔 변화가 없었다. 즉 KRX는 분기를 반영하지 않는다.
    이 스크립트는 분기 실적을 반영하는 TTM을 쓴다 — 실적이 무너진 기업이
    작년 EPS 때문에 싸 보이는 착시를 없애기 위함이다. 그래서 사이트 표시값이
    네이버·KRX와 다를 수 있고, 이는 버그가 아니다.

■ 공시 시차 (look-ahead 방지)
    분기 실적은 분기말 이후에 공시된다. 실제 공시 시점 이전 날짜에 그 실적을
    쓰면 미래 정보를 과거에 반영하는 것이 되어 스크리너 결과가 부풀려진다.
    법정 기한을 그대로 적용한다: 분기보고서 45일, 사업보고서 90일.
        2026-03 결산 → 2026-05-15 이후에만 사용
        2025-12 결산 → 2026-03-31 이후에만 사용

■ 호출량
    KRX  : 60개월 x 2시장 = 120콜
    KIS  : 종목당 1콜 (분기 30행 = 약 7년치를 한 번에 받음)
    DART : 사용 안 함
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_DIR = ROOT / "data" / "matrix"
CACHE_DIR = ROOT / "data" / ".cache"
UNIVERSE_PATH = ROOT / "data" / "universe.json"

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(ROOT / ".env")
load_env(ROOT.parent / ".env")

KRX_KEY = os.environ.get("KRX_API_KEY")
# 시세·재무 조회는 실전 전용 키(KIS_REAL_*)를 쓴다. KIS_APP_KEY는 모의투자 매매용이라
# 조회 목적에 맞지 않는다(모의 키로 실전 서버를 호출하면 500). 없으면 기존 키로 폴백.
KIS_KEY = os.environ.get("KIS_REAL_APP_KEY") or os.environ.get("KIS_APP_KEY")
KIS_SECRET = os.environ.get("KIS_REAL_APP_SECRET") or os.environ.get("KIS_APP_SECRET")
KIS_BASE = os.environ.get("KIS_REAL_BASE_URL") or os.environ.get("KIS_BASE_URL")
if not (KRX_KEY and KIS_KEY and KIS_SECRET and KIS_BASE):
    sys.stderr.write("[ERROR] KRX_API_KEY / KIS_REAL_APP_KEY / KIS_REAL_APP_SECRET / "
                     "KIS_REAL_BASE_URL 필요.\n")
    sys.exit(2)

KRX_BASE = "http://data-dbg.krx.co.kr/svc/apis/"
KRX_SLEEP = 0.3
KRX_WORKERS = 4           # 일별 수집 동시성. 보수적으로 — 지속 부하 차단 이력 있음.
KIS_SLEEP = 0.25          # KIS는 순차 호출만. 병렬로 때리면 막힌다(오늘 DART에서 겪음).
LOOKBACK_MONTHS = 60
_SRV = "real" if "openapivts" not in (KIS_BASE or "") else "paper"
TOKEN_PATH = CACHE_DIR / f"_kis_token_{_SRV}.json"   # 서버별 분리 (토큰 혼용 방지)
RATIO_PATH = CACHE_DIR / f"_kis_ratio_q_{_SRV}.json"
CLOSE_PATH = CACHE_DIR / "_krx_close_monthly.json"
DAILY_PATH = CACHE_DIR / "_krx_close_daily.json"
SHRS_PATH = CACHE_DIR / "_krx_shares_monthly.json"

QUARTER_LAG_DAYS = 45     # 분기보고서 법정 제출기한
ANNUAL_LAG_DAYS = 90      # 사업보고서 법정 제출기한


# ------------------------------------------------------------------ 공통

def _amt(s):
    s = str(s if s is not None else "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _jget(url, headers, timeout=30, retry=3, backoff=0.8):
    last = None
    for attempt in range(retry):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(backoff * (attempt + 1))
    raise last


# ------------------------------------------------------------- KRX 종가

def krx(svc: str, bas_dd: str):
    d = _jget(f"{KRX_BASE}{svc}?basDd={bas_dd}", {"AUTH_KEY": KRX_KEY})
    return d.get("OutBlock_1") or []


def short_code(isu_cd: str) -> str:
    return isu_cd[3:9] if len(isu_cd) > 9 else isu_cd


def resolve_trading_day(d: datetime, max_back: int = 10):
    for _ in range(max_back):
        ds = d.strftime("%Y%m%d")
        try:
            if krx("sto/stk_bydd_trd", ds):
                return ds
        except Exception as e:
            print(f"    [WARN] {ds}: {e}", file=sys.stderr)
        d -= timedelta(days=1)
        time.sleep(KRX_SLEEP)
    return None


def fetch_closes_daily(months: int, refresh: bool, workers: int = KRX_WORKERS):
    """일별 종가를 모두 받아 **월평균**으로 집계.

    월 1일치(15일) 샘플만 쓰면 그날의 급등락이 5년 평균에 그대로 실린다. 일별을
    평균 내면 그 노이즈가 사라진다. 다만 일별 원본을 그대로 저장하면 종목당 관측이
    58 -> 1,230개가 되어 매트릭스가 32MB가 되고, stock.js가 이 파일을 통째로
    내려받는 구조라 웹에서 감당이 안 된다. 그래서 **원본은 캐시(gitignore)에만 두고
    커밋되는 매트릭스는 월평균 58개 값**으로 유지한다.

    반환 형식은 fetch_closes()와 동일: ({basDd: {code: 종가}}, [basDd...])
    여기서 basDd는 각 월의 마지막 거래일이고 값은 그 달의 평균 종가다.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw = {}
    if DAILY_PATH.exists() and not refresh:
        raw = json.loads(DAILY_PATH.read_text(encoding="utf-8"))
        print(f"  일별 캐시 {len(raw)}일")

    end = datetime.now()
    start = (end - timedelta(days=31 * months)).replace(day=1)
    day = start
    todo = []
    while day <= end:
        if day.weekday() < 5:                     # 주말 제외 (공휴일은 빈 응답으로 걸러짐)
            ds = day.strftime("%Y%m%d")
            if ds not in raw:
                todo.append(ds)
        day += timedelta(days=1)
    print(f"  수집 대상 {len(todo)}일 (보유 {len(raw)}일)")

    t0 = time.time()
    done = 0
    lock = threading.Lock()

    def one_day(ds):
        """하루치(두 시장) 종가. 워커 안에서는 순차 — 동시성은 날짜 단위로만 준다."""
        c = {}
        for svc in ("sto/stk_bydd_trd", "sto/ksq_bydd_trd"):
            try:
                for r in krx(svc, ds):
                    px = _amt(r.get("TDD_CLSPRC"))
                    if px:
                        c[short_code(r["ISU_CD"])] = px
            except Exception as e:
                print(f"    [WARN] {ds} {svc}: {e}", file=sys.stderr)
            time.sleep(KRX_SLEEP)
        return ds, c

    def record(res):
        nonlocal done
        ds, c = res
        with lock:
            raw[ds] = c                            # 휴장일은 {} 로 기록해 재조회 방지
            done += 1
            if done % 100 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"  [{done:>4}/{len(todo)}] 경과 {el:.0f}s "
                      f"· ETA {el/done*(len(todo)-done):.0f}s", flush=True)
                DAILY_PATH.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    # KRX 공식 OpenAPI는 키 인증 방식이라 동시 호출이 정상 사용이다. 다만 오늘
    # DART에서 "짧은 벤치마크는 멀쩡했는데 수천 콜 지속 부하에서 차단"을 겪었으므로
    # 워커는 보수적으로 잡는다(기본 4 → 순차 대비 약 4배).
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(one_day, todo):
            record(res)
    DAILY_PATH.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    # 월평균 집계.
    # 단, **가장 최근 달은 평균이 아니라 최신 거래일 종가**를 쓴다.
    # 5년 평균에는 월평균이 옳지만(특정일 노이즈 제거), "현재 PER"에는 틀리다.
    # 카드가 '현재가 = 최신 종가'와 'PER = 월평균 기반'을 나란히 보여주면
    # 사용자가 현재가÷EPS로 검산할 때 맞지 않는다(2026-08-13 실측: 괴리 중앙 2.6%,
    # 오킨스전자 18.3%). 과거는 집계, 현재는 실시간 — 실무 표준과도 같다.
    by_month = {}
    for ds, c in raw.items():
        if not c:
            continue
        by_month.setdefault(ds[:6], []).append((ds, c))
    out, dates = {}, []
    months_sorted = sorted(by_month)[-months:]
    latest_ym = months_sorted[-1] if months_sorted else None
    for ym in months_sorted:
        days = by_month[ym]
        last_ds = max(d for d, _ in days)
        if ym == latest_ym:
            out[last_ds] = dict(dict(days)[last_ds])   # 최신 달 = 최신 거래일 종가
        else:
            acc, cnt = {}, {}
            for _, c in days:
                for code, px in c.items():
                    acc[code] = acc.get(code, 0.0) + px
                    cnt[code] = cnt.get(code, 0) + 1
            out[last_ds] = {code: acc[code] / cnt[code] for code in acc}
        dates.append(last_ds)
    if latest_ym:
        print(f"  최신 달({latest_ym})은 월평균 대신 최신 거래일 종가 사용", flush=True)
    print(f"  → {len(dates)}개월 (월평균, 거래일 중앙 "
          f"{sorted(len(v) for v in by_month.values())[len(by_month)//2]}일)")
    return out, sorted(dates)


def fetch_closes(months: int, refresh: bool):
    """{basDd: {code: 종가}} — 캐시 사용."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = {}
    if CLOSE_PATH.exists() and not refresh:
        cache = json.loads(CLOSE_PATH.read_text(encoding="utf-8"))

    end_dt = datetime.now()
    targets = [(end_dt - timedelta(days=30 * i)).replace(day=15) for i in range(months)]
    targets.reverse()

    dates, seen_months = [], set()
    for i, t in enumerate(targets):
        ym = t.strftime("%Y%m")
        if ym in seen_months:
            continue
        seen_months.add(ym)
        hit = next((d for d in cache if d.startswith(ym)), None)
        if hit:
            dates.append(hit)
            continue
        ds = resolve_trading_day(t)
        if not ds:
            print(f"  [{i+1:>2}/{months}] {ym} 거래일 없음", flush=True)
            continue
        c = {}
        for svc in ("sto/stk_bydd_trd", "sto/ksq_bydd_trd"):
            try:
                for r in krx(svc, ds):
                    px = _amt(r.get("TDD_CLSPRC"))
                    if px:
                        c[short_code(r["ISU_CD"])] = px
            except Exception as e:
                print(f"    [WARN] {ds} {svc}: {e}", file=sys.stderr)
            time.sleep(KRX_SLEEP)
        if c:
            cache[ds] = c
            dates.append(ds)
            CLOSE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"  [{i+1:>2}/{months}] {ds} · {len(c)}종목", flush=True)

    return {d: cache[d] for d in dates}, sorted(dates)


# ------------------------------------------------------------- KIS 재무비율

def kis_token() -> str:
    """24h 유효. 재발급은 분당 제한(403)이 있어 반드시 캐싱한다."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        c = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        if time.time() - c.get("issued", 0) < 20 * 3600:
            return c["token"]
    body = json.dumps({"grant_type": "client_credentials",
                       "appkey": KIS_KEY, "appsecret": KIS_SECRET}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(KIS_BASE + "/oauth2/tokenP", data=body,
                                         headers={"content-type": "application/json"},
                                         method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                t = json.loads(r.read()).get("access_token")
            if t:
                TOKEN_PATH.write_text(json.dumps({"token": t, "issued": time.time()}),
                                      encoding="utf-8")
                return t
        except Exception as e:
            print(f"  토큰 재시도 {attempt+1}/5 ({repr(e)[:60]})", file=sys.stderr)
            time.sleep(20)
    sys.exit("[ERROR] KIS 토큰 발급 실패")


def fetch_ratios(codes, token, refresh: bool):
    """{code: {stac_yymm: {eps, bps}}} — 분기(누적) 시계열. 종목당 1콜."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if RATIO_PATH.exists() and not refresh:
        data = json.loads(RATIO_PATH.read_text(encoding="utf-8"))
        print(f"  캐시 {len(data)}종목")

    todo = [c for c in codes if c not in data]
    print(f"  신규 조회 {len(todo)}종목")
    H = {"authorization": f"Bearer {token}", "appkey": KIS_KEY,
         "appsecret": KIS_SECRET, "content-type": "application/json",
         "tr_id": "FHKST66430300"}
    t0 = time.time()
    for i, code in enumerate(todo):
        q = f"FID_DIV_CLS_CODE=1&fid_cond_mrkt_div_code=J&fid_input_iscd={code}"
        try:
            out = _jget(f"{KIS_BASE}/uapi/domestic-stock/v1/finance/financial-ratio?{q}",
                        H).get("output") or []
        except Exception:
            out = []
        if out:
            data[code] = {o["stac_yymm"]: {"eps": o.get("eps"), "bps": o.get("bps")}
                          for o in out if o.get("stac_yymm")}
        time.sleep(KIS_SLEEP)
        if (i + 1) % 50 == 0 or i + 1 == len(todo):
            el = time.time() - t0
            print(f"  [{i+1:>4}/{len(todo)}] KIS · 경과 {el:.0f}s "
                  f"· ETA {el/(i+1)*(len(todo)-i-1):.0f}s", flush=True)
            RATIO_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    RATIO_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ------------------------------------------------------------- TTM 계산

def available_from(stac: str) -> date:
    """해당 결산 실적을 실제로 알 수 있게 되는 날짜 (법정 제출기한)."""
    y, m = int(stac[:4]), int(stac[4:6])
    if m == 12:
        return date(y, 12, 31) + timedelta(days=ANNUAL_LAG_DAYS)
    # 분기말 = 해당 월의 말일
    nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
    qend = date(nm_y, nm_m, 1) - timedelta(days=1)
    return qend + timedelta(days=QUARTER_LAG_DAYS)


def _ref(series: dict, stac: str):
    """과거 참조값. KIS는 **데이터가 없는 기간을 0.0으로 채운다**(상장 전 등).

    0을 유효값으로 받으면 TTM = 0 - 0 + 당해누적 = 당해누적 이 되어, TTM이 아닌
    값이 조용히 TTM 자리에 들어간다(카카오뱅크·케이카에서 확인). 정확히 0이면
    결측으로 본다 — 손익분기 0원인 진짜 사례는 사실상 없다.
    """
    v = _amt((series.get(stac) or {}).get("eps"))
    return None if (v is None or v == 0) else v


def ttm_eps(series: dict, stac: str):
    """TTM EPS = 직전 연간 - 전년 동기 누적 + 당해 누적 (= 최근 4개 분기). Q4면 연간.

    계산 불가면 None을 돌려준다. 연간 EPS로 폴백하지 않는다 — TTM 시계열에 연간
    값이 섞이면 5년 평균이 두 기준의 혼합이 되어 팩터가 오염된다.
    """
    y, m = int(stac[:4]), int(stac[4:6])
    cur = _amt((series.get(stac) or {}).get("eps"))
    if cur is None:
        return None
    if m == 12:
        return cur
    prev_annual = _ref(series, f"{y-1}12")
    prev_same = _ref(series, f"{y-1}{m:02d}")
    if prev_annual is None or prev_same is None:
        return None
    return prev_annual - prev_same + cur


def pick_stac(series: dict, ds: str):
    """ds 시점에 공시되어 있는 가장 최근 결산기."""
    d = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    best = None
    for stac in series:
        if len(str(stac)) != 6:
            continue
        try:
            if available_from(stac) <= d:
                if best is None or stac > best:
                    best = stac
        except Exception:
            continue
    return best


def fetch_shares(dates, refresh: bool):
    """월별 상장주식수 {basDd: {code: 주식수}}. 자주 안 바뀌므로 월 1회면 충분."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = {}
    if SHRS_PATH.exists() and not refresh:
        cache = json.loads(SHRS_PATH.read_text(encoding="utf-8"))
    todo = [d for d in dates if d not in cache]
    if todo:
        print(f"  상장주식수 수집 {len(todo)}개월 (보유 {len(cache)})")
    for i, ds in enumerate(todo):
        s = {}
        for svc in ("sto/stk_bydd_trd", "sto/ksq_bydd_trd"):
            try:
                for r in krx(svc, ds):
                    n = _amt(r.get("LIST_SHRS"))
                    if n:
                        s[short_code(r["ISU_CD"])] = n
            except Exception as e:
                print(f"    [WARN] {ds} {svc}: {e}", file=sys.stderr)
            time.sleep(KRX_SLEEP)
        if s:
            cache[ds] = s
        if (i + 1) % 20 == 0 or i + 1 == len(todo):
            print(f"  [{i+1:>3}/{len(todo)}] 주식수", flush=True)
            SHRS_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    SHRS_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {d: cache[d] for d in dates if d in cache}


def adjust_closes(closes, dates, shares):
    """원주가 → 수정주가.

        수정주가(t) = 원주가(t) x 상장주식수(t) / 상장주식수(최신)

    KRX가 주는 TDD_CLSPRC는 그날 실제 체결가(원주가)라 액면분할·무상증자 지점에서
    계단처럼 끊긴다. 반면 KIS EPS/BPS는 **현재 주식수 기준으로 소급 조정**된 값이다.
    두 기준이 어긋나면 분할 이전 구간의 PER이 통째로 부풀려져 "과거보다 지금이 싸다"는
    가짜 신호가 난다(2026-08-13 실측: 40%+ 급락 100건 중 95건에서 PER이 주가와
    동일 비율로 붕괴. SK텔레콤·에코프로·동원산업 등).

    이 식은 액면분할·무상증자·유상증자를 모두 올바르게 처리한다 — 결과적으로
    PER(t) = 시가총액(t) / 순이익(t) 과 같아지기 때문이다.
    """
    if not shares:
        print("  [WARN] 상장주식수 없음 → 원주가 그대로 사용(분할 종목 왜곡 주의)",
              file=sys.stderr)
        return closes
    latest = dates[-1]
    base = shares.get(latest, {})
    out, adjusted = {}, 0
    for ds in dates:
        s = shares.get(ds, {})
        row = {}
        for code, px in closes.get(ds, {}).items():
            n_t, n_0 = s.get(code), base.get(code)
            if n_t and n_0 and n_0 > 0:
                f = n_t / n_0
                if abs(f - 1.0) > 0.01:
                    adjusted += 1
                row[code] = px * f
            else:
                row[code] = px
        out[ds] = row
    print(f"  수정주가 보정 적용: {adjusted:,}건 (주식수 변동 구간)")
    return out


def build(closes, dates, ratios):
    per, pbr = {}, {}
    skipped, skipped_codes = 0, set()
    for ds in dates:
        for code, px in closes[ds].items():
            series = ratios.get(code)
            if not series:
                continue
            stac = pick_stac(series, ds)
            if not stac:
                continue
            eps = ttm_eps(series, stac)
            if eps is None:
                # 상장/분할 직후라 1년 전 비교분기가 없는 경우가 대부분.
                # 연간으로 대체하지 않고 결측으로 남긴다(기준 혼합 방지).
                skipped += 1
                skipped_codes.add(code)
            else:
                per.setdefault(code, {})[ds] = round(px / eps, 2) if eps > 0 else 0.0
            bps = _amt((series.get(stac) or {}).get("bps"))
            if bps and bps > 0:
                pbr.setdefault(code, {})[ds] = round(px / bps, 2)
    if skipped:
        print(f"  TTM 계산 불가 → 결측 처리: {skipped:,}건 / {len(skipped_codes)}종목 "
              f"(상장·분할 직후 등)")
    return per, pbr


# ------------------------------------------------------------------ main

def resolve_codes(args, universe_codes, all_codes):
    if args.all:
        return sorted(all_codes)
    return sorted(universe_codes & all_codes) if universe_codes else sorted(all_codes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="KRX 전 종목 (기본: universe)")
    ap.add_argument("--months", type=int, default=LOOKBACK_MONTHS)
    ap.add_argument("--daily", action="store_true",
                    help="일별 종가를 모두 받아 월평균으로 집계 (특정일 노이즈 제거)")
    ap.add_argument("--krx-workers", type=int, default=KRX_WORKERS,
                    help=f"일별 종가 동시 수집 수 (기본 {KRX_WORKERS})")
    ap.add_argument("--refresh-close", action="store_true", help="종가 캐시 무시")
    ap.add_argument("--refresh-ratio", action="store_true", help="KIS 캐시 무시")
    ap.add_argument("--replace", action="store_true",
                    help="정식 경로(per_monthly.json)에 기록. 기본은 *_ttm.json")
    args = ap.parse_args()

    print(f"[matrix-kis] TTM PER/PBR ({args.months}개월)")
    print("  PER = 종가 / TTM EPS · PBR = 종가 / BPS")
    print(f"  공시 시차: 분기 {QUARTER_LAG_DAYS}일 · 연간 {ANNUAL_LAG_DAYS}일\n")

    if args.daily:
        print(f"[1/3] KRX 일별 종가 → 월평균 (워커 {args.krx_workers})")
        closes, dates = fetch_closes_daily(args.months, args.refresh_close,
                                           workers=args.krx_workers)
    else:
        print("[1/3] KRX 월별 종가 (매월 15일 근처 1일 샘플)")
        closes, dates = fetch_closes(args.months, args.refresh_close)
    if not dates:
        sys.exit("[ERROR] 종가 수집 실패")
    all_codes = {c for m in closes.values() for c in m}
    print(f"  → {len(dates)}개월 · 누적 {len(all_codes)}종목")
    shares = fetch_shares(dates, args.refresh_close)
    closes = adjust_closes(closes, dates, shares)
    print()

    uni_codes = set()
    if UNIVERSE_PATH.exists():
        u = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
        uni_codes = {s["code"] for s in (u.get("stocks") or []) if s.get("code")}
    codes = resolve_codes(args, uni_codes, all_codes)
    print(f"[2/3] KIS 재무비율 · 대상 {len(codes)}종목")
    ratios = fetch_ratios(codes, kis_token(), args.refresh_ratio)
    print(f"  → {len(ratios)}종목 확보\n")

    print("[3/3] 매트릭스 조립")
    per, pbr = build(closes, dates, ratios)
    print(f"  PER {len(per)}종목 · PBR {len(pbr)}종목")

    suffix = "" if args.replace else "_ttm"
    meta = {
        "months": args.months,
        "basis": "TTM",
        "source": "KRX OpenAPI(종가) + KIS 재무비율(EPS/BPS)",
        "per_formula": "종가 / TTM EPS (최근 4분기 합산)",
        "pbr_formula": "종가 / BPS (최근 공시)",
        "disclosure_lag_days": {"quarter": QUARTER_LAG_DAYS, "annual": ANNUAL_LAG_DAYS},
        "note": "KRX/네이버 표시값은 직전 확정 결산 기준(연 1회 갱신)이라 값이 다르다. 의도된 차이.",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    for nm, mat in (("per", per), ("pbr", pbr)):
        p = MATRIX_DIR / f"{nm}_monthly{suffix}.json"
        p.write_text(json.dumps({"meta": {**meta, "ticker_count": len(mat)}, "matrix": mat},
                                ensure_ascii=False), encoding="utf-8")
        print(f"  → {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
