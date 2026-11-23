"""Top N 종목 자료 묶음 → data/research/{code}.json  (에이전트가 WebSearch 전에 먼저 Read 한다)

왜: 이 환경의 WebSearch 는 미국 중심이라 한국 중소형주 근거가 잘 안 잡힌다. 해소 근거의 상당수는
    공시 그 자체(공급계약·자사주 소각·밸류업·잠정실적)라서 공식 출처를 코드로 받아 주는 편이 정확하다.

  dart      최근 365일 DART 주요사항보고·거래소공시 (공시명·날짜·접수번호) ← DART list API
  news      최근 90일 네이버 뉴스 (언론사·날짜·요약)         ← 〃
  telegram  최근 90일 텔레그램 증권 채널 언급                ← 〃 (로컬 DB)
  reports   최근 180일 증권사 리포트 (증권사·목표가·본문 앞부분) ← 네이버증권 API
  revisions FnGuide 당해 추정치 현재/1·3·6개월/1년 전          ← 리서치 리포트 에이전트 fnguide_data 재사용

    python scripts/build_research_pack.py            # triple_cross.json top
    python scripts/build_research_pack.py --codes 005930,000660

다른 폴더 모듈을 불러 쓴다(복사하지 않음 — 저쪽이 이미 테스트된 코드). 불러오기 실패·자료 전무는 조용히 넘기지 않고 멈춘다.
"""
import argparse, json, os, re, sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "research"
CONTEST = Path(r"C:/Users/hsh/Desktop/금융공모전/모의투자대회")
REPORT_AGENT = Path(r"C:/Users/hsh/Desktop/03_투자·코딩 프로젝트/vibecoding/주식 ai 리서치 리포트 에이전트/scripts")
NV = "https://stock.naver.com"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://stock.naver.com/"}

sys.path[:0] = [str(CONTEST), str(REPORT_AGENT), str(ROOT / "scripts")]
import feeds  # noqa: E402
try:
    from catalyst_engine import grounding as G   # noqa: E402
    import fnguide_data as FG                    # noqa: E402
except Exception as e:  # 저쪽 폴더가 옮겨지거나 바뀌면 여기서 바로 안다
    sys.exit(f"[ERROR] 외부 모듈 불러오기 실패 — {e}\n  {CONTEST}\n  {REPORT_AGENT}")


# 해소 판단과 무관한 일상 공시 — 대형주는 이것들이 50건 상한을 채워 공급계약·소각 공시를 밀어낸다
DART_NOISE = ("임원ㆍ주요주주", "소유상황보고", "주식등의대량보유", "최대주주등소유주식변동", "대규모기업집단",
              "기업설명회", "증권발행실적", "투자설명서", "일괄신고", "기타경영사항(자율공시)(제3자", "주주총회소집",
              "참고서류", "의결권대리행사", "자기주식처분결과", "동일인등출자", "특수관계인")


def _items(ctx, noise=()):
    return [{"date": (m.get("timestamp") or "")[:10], "src": m.get("channel_name") or m.get("source"),
             "text": re.sub(r"\s+", " ", m.get("text") or "")[:300]}
            for m in (ctx.get("today") or []) + (ctx.get("background") or [])
            if not any(n in (m.get("text") or "") for n in noise)]


def dart(code, days=365):
    """주요사항보고(B)·거래소공시(I)만 1년치. grounding 의 50건 상한은 대형주에서 한 달 치밖에 안 된다."""
    cmap = json.load(open(ROOT / "data/financials/_dart_corpmap.json", encoding="utf-8"))
    corp = cmap.get(code)
    if not corp:
        return []
    out = []
    for ty in ("B", "I"):
        j = feeds.dart_json("list.json", corp_code=corp, pblntf_ty=ty, page_count=100,
                            bgn_de=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
                            end_de=datetime.now().strftime("%Y%m%d"))
        for x in j.get("list") or []:
            if not any(n in x["report_nm"] for n in DART_NOISE):
                d = x["rcept_dt"]
                out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "src": "DART", "text": x["report_nm"].strip(),
                            "rcept_no": x["rcept_no"]})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def reports(code, days=180):
    try:
        items = requests.get(f"{NV}/api/stockSecurity/researches/v2/company?itemCodes={code}&index=0&size=15",
                             headers=H, timeout=15).json().get("items", [])
    except Exception as e:
        return {"error": repr(e)[:120]}
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for r in items:
        d = str(r.get("writeDate") or "")[:10].replace(".", "-")
        if d and d < cut:
            continue
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.get("content") or ""))
        out.append({"date": d, "broker": r.get("brokerName"), "title": r.get("title"),
                    "target": r.get("goalPrice"), "summary": body[:500]})
    return out


def revisions(code):
    """FnGuide cnsTrend — 열 순서는 현재·1개월·3개월·6개월·1년 전 (2026-11-23 디어유로 확인: 헤더 라벨이 한 칸 밀려 있음)."""
    try:
        p = FG.extract_init_payload(FG._fetch_page(code, "consensus"))
        t = p["cnsTrend"]
        year = (p.get("trendYYMM") or [{}])[0].get("YYMM_F")
    except Exception as e:
        return {"error": repr(e)[:120]}
    lab = ["now", "1m", "3m", "6m", "1y"]
    return {"fiscal_year": year,
            "rows": {r["ACC_NM"]: dict(zip(lab, (r.get(f"VAL{i}") for i in range(1, 6)))) for r in t.get("data", [])}}


def pack(name, code):
    g = {"news": G.get_news_context(name, code, days=90)}
    try:
        g["telegram"] = G.get_channel_context(name, code, days=90)
    except Exception as e:
        g["telegram"] = {"error": repr(e)[:120]}
    doc = {"code": code, "name": name, "built_at": datetime.now().isoformat(timespec="seconds"),
           "dart": dart(code), "news": _items(g["news"])[:30],
           "telegram": _items(g["telegram"])[:30] if "error" not in g["telegram"] else g["telegram"],
           "reports": reports(code), "revisions": revisions(code)}
    doc["counts"] = {k: (len(v) if isinstance(v, list) else 0) for k, v in doc.items()
                     if k in ("dart", "news", "telegram", "reports")}
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes")
    a = ap.parse_args()
    tc = json.load(open(ROOT / "data/screens/triple_cross.json", encoding="utf-8"))
    names = {r["code"]: r["name"] for r in tc["all_ranked"]}
    codes = a.codes.split(",") if a.codes else [r["code"] for r in tc["top"]]
    OUT.mkdir(parents=True, exist_ok=True)
    empty = []
    for c in codes:
        d = pack(names.get(c, c), c)
        (OUT / f"{c}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {c} {d['name']:<12} {d['counts']}")
        if d["counts"]["dart"] == 0 and d["counts"]["news"] == 0:
            empty.append(c)
    if len(empty) > len(codes) // 2:   # 절반 넘게 공시·뉴스 0건이면 키·네트워크 문제 — 빈 묶음으로 분석하면 안 된다
        sys.exit(f"[ERROR] {len(empty)}/{len(codes)}종목이 공시·뉴스 0건 — DART/NAVER 키·네트워크 확인")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
