"""TTM(최근 4개 분기) 판정 — KIS 재무비율 시계열의 단일 해석기.

이 모듈은 **순수 함수만** 담는다. 네트워크·파일·환경변수를 건드리지 않으므로
테스트에서 그대로 부를 수 있다 (tests/test_ttm.py).

■ 왜 별도 모듈인가
    이전에는 `fetch_matrix_kis.py`와 `validate_universe_api.py`가 각자 복제본을
    들고 있었다. 아래 세 불변식은 전부 실제 사고를 겪고 나서 추가된 것인데,
    복제된 상태에서는 한쪽만 고쳐도 아무 신호가 나지 않는다 — 유니버스 통과
    기준과 PER 매트릭스가 서로 다른 잣대로 계산된 채 사이트에 올라간다.
    그래서 정의를 한 곳으로 모았다.

■ 불변식 셋 (임의로 완화하지 말 것)
    1. **0 = 결측.** KIS는 데이터가 없는 기간(상장 전 등)을 `0.0`으로 채운다.
       이를 유효값으로 받으면 TTM = 0 - 0 + 당해누적 = 당해누적 이 되어, TTM이
       아닌 값이 조용히 TTM 자리에 앉는다 (카카오뱅크·케이카에서 실측 확인).
       EPS가 정확히 0.00원인 진짜 사례는 사실상 없다.
    2. **연간 폴백 금지.** TTM을 못 구하면 None이다. 연간 EPS로 대신하면 5년
       평균이 두 기준의 혼합이 되어 s1_per 팩터가 오염된다.
    3. **공시 시차.** 분기보고서 45일 · 사업보고서 90일. 실제 공시 전 날짜에
       그 실적을 쓰면 미래 정보를 과거에 반영하는 셈이라(look-ahead) 스크리너
       성과가 부풀려진다.

■ 용어
    stac  KIS의 `stac_yymm` — 결산 연월 6자리 문자열. 예: "202603" = 2026년 1분기 누적.
          KIS의 분기 값은 전부 **당해 누적**이다 (202606 = 상반기 누적, 분기 단독 아님).
    series  {stac: {"eps": ..., "bps": ...}} 형태의 종목별 시계열.
"""
from datetime import date, timedelta

QUARTER_LAG_DAYS = 45     # 분기보고서 법정 제출기한
ANNUAL_LAG_DAYS = 90      # 사업보고서 법정 제출기한


def amount(s):
    """KIS 문자열 금액 → float. 빈 값·"-"·파싱 실패는 None."""
    s = str(s if s is not None else "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def stacs(series: dict) -> list:
    """series의 유효한 결산기 목록 (오름차순). 6자리가 아닌 키는 버린다."""
    return sorted(str(k) for k in series if len(str(k)) == 6 and str(k).isdigit())


def available_from(stac: str) -> date:
    """해당 결산 실적을 실제로 알 수 있게 되는 날짜 (법정 제출기한).

        202512 (사업보고서) → 2026-03-31 이후
        202603 (분기보고서) → 2026-05-15 이후
    """
    y, m = int(stac[:4]), int(stac[4:6])
    if m == 12:
        return date(y, 12, 31) + timedelta(days=ANNUAL_LAG_DAYS)
    # 분기말 = 해당 월의 말일
    qend = date(y, m + 1, 1) - timedelta(days=1)
    return qend + timedelta(days=QUARTER_LAG_DAYS)


def latest_due_stac(today: date) -> str:
    """today 기준 공시 기한이 지난 가장 최근 결산기 (12월 결산 기준).

        2026-11-23 → "202609"   (3분기 기한 11-14 경과)
        2026-11-10 → "202606"
    캐시 신선도 판정용: 이 분기가 없는 캐시는 다시 받아야 한다.
    """
    y, m = today.year, (today.month - 1) // 3 * 3   # 이미 지난 가장 최근 분기말 월 (0 = 전년 12월)
    for _ in range(8):
        if m <= 0:
            y, m = y - 1, m + 12
        stac = f"{y}{m:02d}"
        m -= 3
        if available_from(stac) <= today:
            return stac
    raise ValueError(today)


def _ref(series: dict, stac: str, field: str = "eps"):
    """과거 참조값. 불변식 1(0 = 결측)이 적용되는 유일한 지점."""
    v = amount((series.get(stac) or {}).get(field))
    return None if (v is None or v == 0) else v


def ttm_eps(series: dict, stac: str, field: str = "eps"):
    """TTM EPS = 직전 연간 − 전년 동기 누적 + 당해 누적 (= 최근 4개 분기).

    stac이 12월이면 그 자체가 연간이므로 그대로 쓴다.
    계산에 필요한 값이 없으면 **None** — 연간으로 폴백하지 않는다(불변식 2).

    당해 누적(cur)에도 불변식 1이 똑같이 적용된다. 분리 이전 코드는 과거 참조값에만
    0-필러 규칙을 걸고 cur은 원값으로 받았는데, 그러면 (a) Q4의 0.00이 "EPS 0원"으로
    통과해 PER 자리에 0이 들어가고 (b) 분기의 0.00이 "당해 이익 0원"으로 취급되어
    TTM = 직전연간 − 전년동기 라는 엉뚱한 값이 나온다. 같은 필러를 위치에 따라 다르게
    읽을 이유가 없어 규칙을 일치시켰다.
    """
    y, m = int(stac[:4]), int(stac[4:6])
    cur = _ref(series, stac, field)
    if cur is None:
        return None
    if m == 12:
        return cur
    prev_annual = _ref(series, f"{y-1}12", field)
    prev_same = _ref(series, f"{y-1}{m:02d}", field)
    if prev_annual is None or prev_same is None:
        return None
    return prev_annual - prev_same + cur


def bps_at(series: dict, stac: str):
    """해당 결산기의 BPS. 재고량 개념이라 TTM 합산 대상이 아니다 — 시점값 그대로.

    PBR의 분모. 0 이하면 자본잠식이거나 결측이므로 None.
    """
    v = amount((series.get(stac) or {}).get("bps"))
    return v if (v is not None and v > 0) else None


def latest_annual_eps(series: dict):
    """가장 최근 **확정 결산**(12월) EPS. 없으면 None.

    s3_per(Growth 팩터)의 기준선으로 쓴다. 네이버 forward_per는 "직전 결산 PER →
    추정 PER"이라는 같은 잣대 안의 값인데, 우리 current_per는 TTM이라 그대로 빼면
    기준이 섞인다 — 대주전자재료에서 부호가 반전됐다(+0.348 vs 실제 −0.238).
    """
    for stac in sorted((s for s in stacs(series) if s.endswith("12")), reverse=True):
        v = _ref(series, stac)
        if v is not None:
            return v
    return None


def disclosed_stac(series: dict, as_of: str):
    """`as_of`(YYYYMMDD) 시점에 이미 공시되어 있는 가장 최근 결산기. 불변식 3.

    공시 전 실적은 후보에서 아예 빠지므로, 이 함수를 거친 stac만 쓰면
    look-ahead가 구조적으로 불가능하다.
    """
    d = date(int(as_of[:4]), int(as_of[4:6]), int(as_of[6:8]))
    best = None
    for stac in stacs(series):
        try:
            if available_from(stac) <= d and (best is None or stac > best):
                best = stac
        except ValueError:
            continue          # 3/6/9/12 이외의 월 — KIS에선 나오지 않지만 방어
    return best


def recent_stacs(series: dict, n: int) -> list:
    """최근 n개 결산기 (내림차순). 유니버스 5Y 실적 검증용."""
    return sorted(stacs(series), reverse=True)[:n]
