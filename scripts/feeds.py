"""외부 피드 어댑터 — KRX 공식 OpenAPI · KIS · OpenDART.

호출자는 도메인 언어로만 요청한다. 재시도·백오프·속도 제한·토큰 캐시는 전부
이 모듈 뒤에 있다.

■ 왜 모았나 — 속도 제한은 전역 속성인데 코드에는 국소적으로 흩어져 있었다

    이관 전에는 KRX/KIS/DART 호출이 스크립트마다 따로 구현돼 있었고, 각자
    자기 sleep 상수와 자기 워커 수를 들고 있었다. 그런데 호출 속도 제한은
    **계정·IP 단위의 전역 속성**이다. 두 스크립트를 동시에 돌리면 실제 호출률은
    두 배가 되지만 어느 쪽도 그 사실을 모른다.

    2026-08-13 KRX IP 1일 차단(이용약관 제10조 제2호)과 그 직후 DART
    ConnectionReset이 둘 다 "이 스크립트 하나만 보면 안전해 보이는" 코드에서
    나왔다. 속도 제한을 지킬 자리가 코드에 존재하지 않았던 게 원인이다.

■ 두 겹으로 막는다

    1. **프로세스 안** — 피드별 전역 제한기 하나. 워커를 몇 개로 늘리든
       총 호출률의 상한이 변하지 않는다.
    2. **프로세스 사이** — 피드별 하트비트 락파일. 다른 페치가 같은 피드를
       때리고 있으면 시작을 거부한다. 크래시 시 120초 뒤 자동 해제.

■ 속도 상한을 정한 근거 (이관 전 실효값을 그대로 보존한다)

    KRX  워커 4개 x 각자 sleep 0.3초 → 실효 간격 0.075초. 전역 제한기를 0.3으로
         두면 일별 수집이 4배 느려지므로 0.075로 맞췄다. 상한(13.3 req/s)은
         이관 전과 동일하고, 달라진 건 **워커 수를 늘려도 상한이 안 오른다**는 점.
    KIS  순차 0.25초. 병렬 호출 시 차단 이력.
    DART 순차 0.15~0.2초가 흩어져 있었다 → 보수적으로 0.2. 8워커로 때렸다가
         ConnectionReset을 맞은 적이 있어 **동시성은 허용하지 않는다**.

    네이버는 이미 `naver_consensus.py`라는 공유 모듈 뒤에 있어 여기 포함하지 않는다.
"""
import atexit
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / ".cache"
LOCK_DIR = CACHE_DIR / "_locks"

os.environ.setdefault("PYTHONUTF8", "1")


# ------------------------------------------------------------------ 자격증명

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
load_env(ROOT.parent / ".env")        # 워크스페이스 공용 .env

KRX_KEY = os.environ.get("KRX_API_KEY")
DART_KEY = os.environ.get("DART_API_KEY")

# 시세·재무 **조회**는 실전 전용 키를 쓴다. KIS_APP_KEY는 모의투자 매매용이라
# 조회 목적에 맞지 않고(모의 키로 실전 서버를 호출하면 500), 무엇보다 둘 다
# 인증에는 성공하기 때문에 잘못 고르면 오류 없이 **다른 데이터**가 돌아온다.
KIS_KEY = os.environ.get("KIS_REAL_APP_KEY") or os.environ.get("KIS_APP_KEY")
KIS_SECRET = os.environ.get("KIS_REAL_APP_SECRET") or os.environ.get("KIS_APP_SECRET")
KIS_BASE = os.environ.get("KIS_REAL_BASE_URL") or os.environ.get("KIS_BASE_URL")

# 어느 계정으로 붙었는지. 캐시 파일명에 박혀서 실전/모의 데이터가 섞이지 않는다.
KIS_ACCOUNT = "paper" if "openapivts" in (KIS_BASE or "") else "real"

KRX_BASE = "http://data-dbg.krx.co.kr/svc/apis/"
DART_BASE = "https://opendart.fss.or.kr/api"


def require(*names) -> None:
    """필요한 자격증명이 없으면 **무엇이** 없는지 말하며 종료."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        sys.exit(f"[ERROR] 자격증명 없음: {', '.join(missing)}\n"
                 f"        {ROOT / '.env'} 또는 {ROOT.parent / '.env'} 를 확인하세요.")


# ------------------------------------------------------------------ 속도 제한

KRX_MIN_INTERVAL = 0.075     # 이관 전 실효값 (워커 4 x sleep 0.3)
KIS_MIN_INTERVAL = 0.25
DART_MIN_INTERVAL = 0.20

LOCK_STALE_SECONDS = 120     # 하트비트가 이보다 낡으면 죽은 프로세스로 본다


class _Limiter:
    """피드 하나의 호출 간격을 프로세스 전역에서 강제한다 (스레드 안전).

    호출마다 락파일 하트비트를 갱신하므로, 정상 실행 중에는 락이 절대 낡지 않고
    프로세스가 죽으면 LOCK_STALE_SECONDS 안에 자동으로 풀린다.
    """

    def __init__(self, name: str, min_interval: float):
        self.name = name
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self._path = LOCK_DIR / f"{name}.lock"
        self._held = False
        self._beat = 0.0

    # -- 프로세스 사이 --------------------------------------------------
    def _acquire(self):
        if self._held:
            return
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                info = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                info = {}
            age = time.time() - info.get("heartbeat", 0)
            if info.get("pid") != os.getpid() and age < LOCK_STALE_SECONDS:
                sys.exit(
                    f"[ERROR] {self.name} 피드를 이미 다른 프로세스가 쓰고 있습니다 "
                    f"(pid {info.get('pid')}, {age:.0f}초 전 활동).\n"
                    f"        동시에 돌리면 실제 호출률이 두 배가 되어 차단됩니다. "
                    f"끝난 뒤 다시 실행하세요.\n"
                    f"        그 프로세스가 이미 죽었다면 {LOCK_STALE_SECONDS}초 뒤 자동 해제됩니다 "
                    f"(또는 {self._path} 삭제).")
        self._write_beat()
        self._held = True
        atexit.register(self._release)

    def _write_beat(self):
        try:
            self._path.write_text(
                json.dumps({"pid": os.getpid(), "feed": self.name,
                            "heartbeat": time.time()}), encoding="utf-8")
            self._beat = time.time()
        except OSError:
            pass          # 락은 보조 장치다. 쓰기 실패로 페치를 막지 않는다.

    def _release(self):
        try:
            if self._held and self._path.exists():
                info = json.loads(self._path.read_text(encoding="utf-8"))
                if info.get("pid") == os.getpid():
                    self._path.unlink()
        except Exception:
            pass

    # -- 프로세스 안 ----------------------------------------------------
    def wait(self):
        with self._lock:
            self._acquire()
            gap = time.time() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            self._last = time.time()
            if self._last - self._beat > 10:
                self._write_beat()


KRX = _Limiter("krx", KRX_MIN_INTERVAL)
KIS = _Limiter("kis", KIS_MIN_INTERVAL)
DART = _Limiter("dart", DART_MIN_INTERVAL)


# ------------------------------------------------------------------ HTTP

def _request(url, headers=None, data=None, method=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get(limiter, url, headers=None, timeout=30, retry=3, backoff=0.8,
         data=None, method=None):
    """속도 제한 + 재시도. 모든 피드 호출이 이 한 곳을 지난다."""
    last = None
    for attempt in range(retry):
        limiter.wait()
        try:
            return _request(url, headers, data, method, timeout)
        except Exception as e:
            last = e
            # 지수 백오프. 마지막 시도 뒤에는 자지 않는다.
            if attempt < retry - 1:
                time.sleep(backoff * (attempt + 1))
    raise last


def _get_json(limiter, url, headers=None, **kw):
    return json.loads(_get(limiter, url, headers, **kw).decode("utf-8"))


# ------------------------------------------------------------------ KRX

def krx(svc: str, bas_dd: str, retry: int = 3) -> list:
    """KRX 공식 OpenAPI 일별 조회 → OutBlock_1 행 목록.

        svc     "sto/stk_bydd_trd" (KOSPI) · "sto/ksq_bydd_trd" (KOSDAQ)
        bas_dd  YYYYMMDD. 휴장일이면 빈 목록.
    """
    require("KRX_KEY")
    d = _get_json(KRX, f"{KRX_BASE}{svc}?basDd={bas_dd}",
                  {"AUTH_KEY": KRX_KEY}, retry=retry)
    return d.get("OutBlock_1") or []


def short_code(isu_cd: str) -> str:
    """KRX 표준코드(KR7005930003) → 단축코드(005930)."""
    return isu_cd[3:9] if len(isu_cd) > 9 else isu_cd


# ------------------------------------------------------------------ KIS

def kis_token_path() -> Path:
    return CACHE_DIR / f"_kis_token_{KIS_ACCOUNT}.json"


def kis_token() -> str:
    """24h 유효. 재발급은 분당 제한(403)이 있어 반드시 캐싱한다."""
    require("KIS_KEY", "KIS_SECRET", "KIS_BASE")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = kis_token_path()
    if path.exists():
        c = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - c.get("issued", 0) < 20 * 3600:
            return c["token"]
    body = json.dumps({"grant_type": "client_credentials",
                       "appkey": KIS_KEY, "appsecret": KIS_SECRET}).encode()
    for attempt in range(5):
        try:
            raw = _get(KIS, KIS_BASE + "/oauth2/tokenP", data=body, method="POST",
                       headers={"content-type": "application/json"}, retry=1)
            t = json.loads(raw).get("access_token")
            if t:
                path.write_text(json.dumps({"token": t, "issued": time.time()}),
                                encoding="utf-8")
                return t
        except Exception as e:
            print(f"  토큰 재시도 {attempt+1}/5 ({repr(e)[:60]})", file=sys.stderr)
            time.sleep(20)      # 분당 제한이라 짧게 재시도해도 소용없다
    sys.exit("[ERROR] KIS 토큰 발급 실패")


def kis_quarterly_ratios(code: str, token: str) -> dict:
    """종목 하나의 분기 EPS/BPS 시계열 → {stac_yymm: {eps, bps}}. 1콜에 30행(≈7년).

    **값은 전부 당해 누적이다** (202606 = 상반기 누적, 분기 단독 아님).
    TTM 환산은 ttm.py 가 한다.
    """
    require("KIS_KEY", "KIS_SECRET", "KIS_BASE")
    q = f"FID_DIV_CLS_CODE=1&fid_cond_mrkt_div_code=J&fid_input_iscd={code}"
    h = {"authorization": f"Bearer {token}", "appkey": KIS_KEY,
         "appsecret": KIS_SECRET, "content-type": "application/json",
         "tr_id": "FHKST66430300"}
    out = _get_json(
        KIS, f"{KIS_BASE}/uapi/domestic-stock/v1/finance/financial-ratio?{q}", h
    ).get("output") or []
    return {o["stac_yymm"]: {"eps": o.get("eps"), "bps": o.get("bps")}
            for o in out if o.get("stac_yymm")}


def kis_ratio_cache_path(account: str = None) -> Path:
    """분기 재무비율 캐시 경로.

    **폴백하지 않는다.** 예전에는 `_real` → `_paper` → 무접미 순으로 훑었는데,
    실전 캐시가 없으면 모의투자 계정의 작은 데이터셋으로 조용히 내려앉아
    그 결과가 그대로 4팩터 모집단이 됐다. 오류도 경고도 없었다.
    계정을 명시적으로 받고, 없으면 부르는 쪽이 실패하게 둔다.
    """
    return CACHE_DIR / f"_kis_ratio_q_{account or KIS_ACCOUNT}.json"


# ------------------------------------------------------------------ DART

def dart_bytes(path: str, **params) -> bytes:
    require("DART_KEY")
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{DART_BASE}/{path}?crtfc_key={DART_KEY}" + (f"&{qs}" if qs else "")
    return _get(DART, url, {"User-Agent": "Mozilla/5.0"}, timeout=25)


def dart_json(path: str, **params) -> dict:
    """OpenDART JSON 엔드포인트. status != 000 이어도 그대로 돌려준다 —
    '013 조회된 데이터 없음'은 정상 경로라서 호출자가 판단해야 한다."""
    return json.loads(dart_bytes(path, **params).decode("utf-8"))


# ------------------------------------------------------------------ 캐시

def cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def load_cache(name: str, default=None):
    p = CACHE_DIR / name
    if not p.exists():
        return {} if default is None else default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def save_cache(name: str, data) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / name).write_text(json.dumps(data, ensure_ascii=False),
                                  encoding="utf-8")
