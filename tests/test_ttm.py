"""ttm.py 회귀 테스트.

픽스처는 **실제 KIS 응답**이다 (data/.cache/_kis_ratio_q_real.json 발췌).
지어낸 값을 쓰지 않는 이유: 여기서 막으려는 버그들이 전부 "KIS가 실제로 이런 걸
돌려준다"는 사실을 몰라서 났기 때문이다. 대표적으로 카카오뱅크(323410)는 전 구간
EPS/BPS가 "0.00" 문자열로 채워져 돌아온다.

    python -m pytest tests/ -q
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ttm  # noqa: E402


# 삼성전자(005930) 실제 값 발췌 — 정상 시계열
SAMSUNG = {
    "202312": {"eps": "2131.00", "bps": "52002.00"},
    "202403": {"eps": "975.00", "bps": "53339.00"},
    "202406": {"eps": "2394.00", "bps": "55011.00"},
    "202409": {"eps": "3834.00", "bps": "55376.00"},
    "202412": {"eps": "4950.00", "bps": "57981.00"},
    "202503": {"eps": "1186.00", "bps": "59059.00"},
    "202506": {"eps": "1920.00", "bps": "58135.00"},
    "202509": {"eps": "3701.00", "bps": "60632.00"},
    "202512": {"eps": "6564.00", "bps": "63997.00"},
    "202603": {"eps": "6993.00", "bps": "71907.00"},
}

# 카카오뱅크(323410) 실제 값 발췌 — KIS가 전 구간을 0.00 필러로 채운 케이스
KAKAOBANK = {
    "202312": {"eps": "0.00", "bps": "0.00"},
    "202403": {"eps": "0.00", "bps": "0.00"},
    "202406": {"eps": "0.00", "bps": "0.00"},
    "202409": {"eps": "0.00", "bps": "0.00"},
    "202412": {"eps": "0.00", "bps": "0.00"},
    "202503": {"eps": "0.00", "bps": "0.00"},
}


# --------------------------------------------------------------- 기본 산식

def test_ttm은_직전연간_빼기_전년동기_더하기_당해누적():
    # 2026 1Q: 6564 - 1186 + 6993
    assert ttm.ttm_eps(SAMSUNG, "202603") == 12371.0


def test_ttm은_최근_4개_분기와_같다():
    """정의 검증 — 202506 TTM은 2025년 3~4Q + 2026년 1~2Q 가 아니라
    직전 연간(202412) − 전년 동기(202406) + 당해(202506) 이다."""
    assert ttm.ttm_eps(SAMSUNG, "202506") == 4950.0 - 2394.0 + 1920.0


def test_4분기_결산은_연간값_그대로():
    assert ttm.ttm_eps(SAMSUNG, "202512") == 6564.0
    assert ttm.ttm_eps(SAMSUNG, "202412") == 4950.0


def test_이익이_급증해도_TTM은_연간보다_클_수_있다():
    """2026 1Q 누적(6993)이 2025 연간(6564)을 넘는 실제 사례.
    '분기 누적이 연간보다 크면 버그'라는 착각을 막는다."""
    assert ttm.ttm_eps(SAMSUNG, "202603") > ttm.ttm_eps(SAMSUNG, "202512")


# ------------------------------------------------- 불변식 1: 0 = 결측

def test_전년동기가_0필러면_결측():
    """이 규칙이 없으면 TTM = 0 - 0 + 당해누적 = 당해누적 이 되어
    TTM이 아닌 값이 조용히 TTM 자리에 앉는다."""
    s = dict(SAMSUNG, **{"202503": {"eps": "0.00", "bps": "59059.00"}})
    assert ttm.ttm_eps(s, "202603") is None


def test_직전연간이_0필러면_결측():
    s = dict(SAMSUNG, **{"202512": {"eps": "0.00", "bps": "63997.00"}})
    assert ttm.ttm_eps(s, "202603") is None


def test_당해누적이_0필러여도_결측():
    """과거값에만 규칙을 걸고 당해값은 원값으로 받으면
    TTM = 직전연간 − 전년동기 라는 엉뚱한 값이 나온다."""
    s = dict(SAMSUNG, **{"202603": {"eps": "0.00", "bps": "71907.00"}})
    assert ttm.ttm_eps(s, "202603") is None


def test_4분기_0필러도_결측():
    """Q4는 조기 반환 경로라 규칙을 빠뜨리기 쉽다. 0으로 나가면 PER 자리에 0이 박힌다."""
    assert ttm.ttm_eps(KAKAOBANK, "202412") is None


def test_전구간_0필러_종목은_모든_분기가_결측():
    assert all(ttm.ttm_eps(KAKAOBANK, s) is None for s in ttm.stacs(KAKAOBANK))


def test_진짜_적자는_결측이_아니다():
    """0-필러 규칙이 음수 EPS까지 삼키면 안 된다 — 적자 분기 판정이 무력화된다."""
    s = dict(SAMSUNG, **{"202603": {"eps": "-500.00", "bps": "71907.00"}})
    assert ttm.ttm_eps(s, "202603") == 6564.0 - 1186.0 - 500.0


# ------------------------------------------- 불변식 2: 연간 폴백 금지

def test_과거가_없으면_연간으로_폴백하지_않는다():
    """상장 직후 종목. 연간값이 TTM 시계열에 섞이면 5년 평균이 두 기준의
    혼합이 되어 s1_per 팩터가 오염된다."""
    ipo = {"202512": {"eps": "800.00", "bps": "9000.00"},
           "202603": {"eps": "250.00", "bps": "9200.00"}}
    assert ttm.ttm_eps(ipo, "202603") is None          # 202503·202412 없음
    assert ttm.ttm_eps(ipo, "202512") == 800.0         # Q4는 연간 그대로라 가능


def test_빈_시계열은_결측():
    assert ttm.ttm_eps({}, "202603") is None


# --------------------------------------------- 불변식 3: 공시 시차

def test_사업보고서는_90일_뒤부터():
    assert ttm.available_from("202512") == date(2026, 3, 31)
    # 윤년이 끼면 달력상 하루 당겨진다 — 법정 기한이 "90일"이라 이게 맞다.
    assert ttm.available_from("202312") == date(2024, 3, 30)


def test_분기보고서는_45일_뒤부터():
    assert ttm.available_from("202603") == date(2026, 5, 15)   # 3/31 + 45
    assert ttm.available_from("202606") == date(2026, 8, 14)   # 6/30 + 45
    assert ttm.available_from("202609") == date(2026, 11, 14)  # 9/30 + 45


def test_공시_전날에는_직전_결산을_쓴다():
    """2026-05-14는 1분기 공시 하루 전 → 2025 사업보고서가 최신."""
    assert ttm.disclosed_stac(SAMSUNG, "20260514") == "202512"
    assert ttm.disclosed_stac(SAMSUNG, "20260515") == "202603"


def test_과거_시점에는_그_시점_기준_결산만():
    """look-ahead 방지의 핵심 — 2024-06-01에는 2024 1Q(5/15 공시)까지만 보인다.
    3/29는 2023 사업보고서(3/30) 하루 전이라 픽스처 범위에서 볼 수 있는 게 없다."""
    assert ttm.disclosed_stac(SAMSUNG, "20240601") == "202403"
    assert ttm.disclosed_stac(SAMSUNG, "20240330") == "202312"
    assert ttm.disclosed_stac(SAMSUNG, "20240329") is None


def test_시계열보다_이른_시점이면_없음():
    assert ttm.disclosed_stac(SAMSUNG, "20200101") is None


# ----------------------------------------------------------- 부속 함수

def test_직전_확정결산_EPS는_12월만_본다():
    """s3_per 기준선. 분기값을 집으면 네이버 forward_per와 잣대가 어긋나
    부호가 뒤집힌다(대주전자재료 사례)."""
    assert ttm.latest_annual_eps(SAMSUNG) == 6564.0


def test_직전_확정결산_EPS도_0필러를_건너뛴다():
    s = dict(SAMSUNG, **{"202512": {"eps": "0.00", "bps": "63997.00"}})
    assert ttm.latest_annual_eps(s) == 4950.0          # 202412로 후퇴


def test_확정결산이_없으면_None():
    assert ttm.latest_annual_eps(KAKAOBANK) is None


def test_bps는_시점값이며_0이하는_결측():
    assert ttm.bps_at(SAMSUNG, "202603") == 71907.0
    assert ttm.bps_at(KAKAOBANK, "202412") is None
    assert ttm.bps_at({"202512": {"bps": "-100.00"}}, "202512") is None


def test_금액_파서():
    assert ttm.amount("1,234.50") == 1234.5
    assert ttm.amount("-2048.00") == -2048.0
    assert ttm.amount("-") is None
    assert ttm.amount("") is None
    assert ttm.amount(None) is None
    assert ttm.amount("N/A") is None


def test_결산기_목록은_6자리_숫자만():
    s = {"202512": {}, "2025": {}, "bad": {}, "202603": {}}
    assert ttm.stacs(s) == ["202512", "202603"]


def test_최근_결산기는_내림차순():
    assert ttm.recent_stacs(SAMSUNG, 3) == ["202603", "202512", "202509"]
