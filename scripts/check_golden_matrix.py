"""PER/PBR 매트릭스 회귀 검사 — 동결된 골든 스냅샷과 대조.

■ 왜 필요한가
    pykrx 이관 과정에서 매트릭스 버그가 7개 나왔다 (회계연도 경계, DART currency=USD,
    재시도 누락으로 61종목 유실, sj_div 혼동으로 롯데렌탈 PBR 154배, 우선주 주식수,
    KIS 0.00 필러, 원주가/조정EPS 불일치). **전부 pykrx 값과 손으로 대조해서** 찾았다.
    그 pykrx를 삭제했으므로 같은 종류의 버그가 다시 들어와도 탐지할 방법이 없다.
    verify_data.py는 신선도·커버리지만 보기 때문에 PBR이 154배여도 통과시킨다.

■ 왜 "과거 값은 불변"을 기준으로 삼는가
    일별 종가는 **원주가로** 저장하고 수정주가 보정은 사용 시점에 적용한다.
    따라서 과거 어느 달의 PER/PBR은 다음 두 경우에만 정당하게 바뀐다:
        (a) 그 종목에 주식수 변동(분할·증자)이 생겨 보정 계수가 전부 재계산됨
        (b) 기업이 과거 실적을 정정 공시함
    둘 다 드물고, 일어나면 **한 종목의 전 구간이 통째로** 움직인다. 반면 회귀는
    보통 특정 구간·특정 종목에서 값이 튀는 형태다. 그래서 "과거 값 변화"를
    기본 위반으로 잡고, 종목 전 구간이 같은 비율로 움직이면 분할로 분류해 따로 센다.

■ 비교에서 빼는 것
    스냅샷의 **마지막 달**. 그 달은 월평균이 아니라 최신 거래일 종가라서
    매 실행마다 정당하게 바뀐다 (fetch_matrix_kis.monthly_from_daily 참조).

    python scripts/check_golden_matrix.py --freeze   # 현재 출력을 골든으로 동결
    python scripts/check_golden_matrix.py            # 대조 (위반 시 exit 1)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_DIR = ROOT / "data" / "matrix"
GOLDEN_DIR = ROOT / "tests" / "golden"
GOLDEN_PATH = GOLDEN_DIR / "matrix.json"

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 상대 오차 허용치. 매트릭스는 소수 2자리 반올림이라 아주 작은 값에서는
# 반올림만으로도 비율이 크게 흔들린다 → 절대 오차도 함께 본다.
REL_TOL = 0.01
ABS_TOL = 0.02
# 종목의 과거 값 대부분이 같은 비율로 움직였다면 주식수 변동(분할)으로 본다.
SPLIT_CONSISTENCY = 0.90

# 실제로 버그를 냈던 종목은 반드시 포함한다 — 골든의 존재 이유다.
BUG_HISTORY = {
    "089860": "롯데렌탈 · sj_div 혼동으로 PBR 154배",
    "323410": "카카오뱅크 · KIS 0.00 필러",
    "381970": "케이카 · KIS 0.00 필러",
    "017670": "SK텔레콤 · 액면분할, 원주가/조정EPS 불일치",
    "086520": "에코프로 · 액면분할",
    "006040": "동원산업 · 액면분할",
    "005930": "삼성전자 · 이익 급증(분기누적 > 직전연간)",
    "000660": "SK하이닉스 · 이익 급증",
}
EXTRA_N = 22          # 시가총액 상위에서 추가로 채울 종목 수


SUFFIX = ""   # --suffix 로 바꾼다. fetch_matrix_kis 를 --replace 없이 돌리면 "_ttm".


def load_matrix(kind: str) -> dict:
    p = MATRIX_DIR / f"{kind}_monthly{SUFFIX}.json"
    if not p.exists():
        sys.exit(f"[ERROR] {p} 없음. fetch_matrix_kis.py 를 먼저 실행하세요.")
    return json.loads(p.read_text(encoding="utf-8"))["matrix"]


def pick_codes(per: dict) -> list:
    """버그 이력 종목 + 시총 상위. 이력 종목은 매트릭스에 있으면 무조건 넣는다."""
    codes = [c for c in BUG_HISTORY if c in per]
    uni_path = ROOT / "data" / "universe.json"
    if uni_path.exists():
        uni = json.loads(uni_path.read_text(encoding="utf-8"))
        ranked = sorted((s for s in (uni.get("passed") or []) if s.get("code") in per),
                        key=lambda s: -(s.get("market_cap") or s.get("market_cap_억") or 0))
        for s in ranked:
            if len(codes) >= len(BUG_HISTORY) + EXTRA_N:
                break
            if s["code"] not in codes:
                codes.append(s["code"])
    return sorted(codes)


def freeze():
    per, pbr = load_matrix("per"), load_matrix("pbr")
    codes = pick_codes(per)
    months = sorted({m for c in codes for m in per.get(c, {})})
    snap = {
        "meta": {
            "frozen_at": datetime.now().isoformat(timespec="seconds"),
            "codes": len(codes),
            "months": len(months),
            "last_month": months[-1] if months else None,
            "note": ("PER/PBR 회귀 기준선. 과거 값은 원칙적으로 불변이다 — "
                     "check_golden_matrix.py 상단 설명 참조."),
            "bug_history": {c: BUG_HISTORY[c] for c in codes if c in BUG_HISTORY},
        },
        "per": {c: per.get(c, {}) for c in codes},
        "pbr": {c: pbr.get(c, {}) for c in codes},
    }
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    size = GOLDEN_PATH.stat().st_size / 1024
    print(f"[golden] 동결 완료 — {len(codes)}종목 · 최대 {len(months)}개월 · {size:.0f}KB")
    print(f"  버그 이력 종목 {len(snap['meta']['bug_history'])}/{len(BUG_HISTORY)}개 포함")
    # 조용히 빠지면 "다 덮었다"고 오해하게 된다. 빠진 건 이름을 부른다.
    for c, why in BUG_HISTORY.items():
        if c not in codes:
            print(f"    ! {c} 미포함 (매트릭스에 값 없음) — {why}")
    print(f"  → {GOLDEN_PATH.relative_to(ROOT)}")


def _drift(old, new):
    """상대 오차. 반올림 잡음은 ABS_TOL로 흡수. 한쪽만 None(적자 전환 등)이면 변동으로 센다."""
    if old is None or new is None:
        return 0.0 if old is new else float("inf")
    if abs(new - old) <= ABS_TOL:
        return 0.0
    if old == 0:
        return float("inf")
    return abs(new - old) / abs(old)


def compare(kind: str, golden: dict, cur: dict, cutoff: str, problems: list, notes: list):
    changed_codes, dropped, split_like = [], [], []
    for code, g_series in golden.items():
        if not g_series:
            # 동결 시점에 이미 값이 없던 종목(전 구간 결측). 지킬 과거가 없다.
            continue
        c_series = cur.get(code)
        if not c_series:
            dropped.append(code)
            continue
        ratios, diffs, missing = [], [], 0
        for m, gv in g_series.items():
            if m >= cutoff:          # 마지막 달은 최신 종가라 정당하게 변한다
                continue
            if m not in c_series:
                missing += 1
                continue
            cv = c_series[m]
            d = _drift(gv, cv)
            if d > REL_TOL:
                diffs.append((m, gv, cv, d))
                if gv and cv is not None:
                    ratios.append(cv / gv)
        if missing:
            problems.append(f"{kind} {code}: 과거 {missing}개월이 사라짐")
        if not diffs:
            continue
        # 전 구간이 거의 같은 비율로 움직였으면 주식수 변동(분할)으로 본다
        uniform = (len(ratios) >= 3
                   and (max(ratios) - min(ratios)) / max(abs(max(ratios)), 1e-9) < (1 - SPLIT_CONSISTENCY))
        target = split_like if uniform else changed_codes
        target.append((code, diffs, ratios))

    if dropped:
        problems.append(f"{kind}: 골든 종목 {len(dropped)}개가 매트릭스에서 사라짐 "
                        f"({', '.join(dropped[:6])})")
    for code, diffs, _ in changed_codes:
        worst = max(diffs, key=lambda x: x[3])
        problems.append(
            f"{kind} {code}: 과거 {len(diffs)}개월 값 변동 "
            f"(최대 {worst[0]} {worst[1]} → {worst[2]}, {worst[3]:.1%})"
            + (f"  ※ {BUG_HISTORY[code]}" if code in BUG_HISTORY else "")
        )
    for code, diffs, ratios in split_like:
        f = sum(ratios) / len(ratios)
        notes.append(f"{kind} {code}: 전 구간 균일 변동 x{f:.4f} ({len(diffs)}개월) "
                     f"— 주식수 변동(분할·증자)으로 보임")


def check():
    if not GOLDEN_PATH.exists():
        sys.exit(f"[ERROR] {GOLDEN_PATH} 없음. --freeze 로 먼저 동결하세요.")
    snap = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    meta = snap.get("meta", {})
    cutoff = meta.get("last_month") or "99999999"

    print(f"[golden] 기준선 {meta.get('frozen_at')} · {meta.get('codes')}종목")
    print(f"  비교 구간: {cutoff} 이전 (마지막 달은 최신 종가라 제외)\n")

    problems, notes = [], []
    compare("PER", snap["per"], load_matrix("per"), cutoff, problems, notes)
    compare("PBR", snap["pbr"], load_matrix("pbr"), cutoff, problems, notes)

    if notes:
        print("  참고 (정상 변화로 분류):")
        for n in notes:
            print(f"    - {n}")
    if problems:
        print("\n[golden] 과거 값이 바뀌었습니다 — 회귀일 수 있습니다:", file=sys.stderr)
        for p in problems:
            print(f"  X {p}", file=sys.stderr)
        print("\n  의도한 변경이라면 --freeze 로 기준선을 다시 동결하세요.", file=sys.stderr)
        sys.exit(1)
    print("\n[golden] OK — 과거 값 변동 없음")


def main():
    global SUFFIX
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true",
                    help="현재 매트릭스를 골든 기준선으로 동결")
    ap.add_argument("--suffix", default="",
                    help="정식 경로 대신 per_monthly{suffix}.json 을 본다 (예: _ttm). "
                         "정식 파일을 덮어쓰기 전에 후보를 먼저 검사할 때 쓴다.")
    args = ap.parse_args()
    SUFFIX = args.suffix
    if args.freeze:
        freeze()
    else:
        check()


if __name__ == "__main__":
    main()
