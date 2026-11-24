"""Top N 종목 자료 묶음 → data/research/{code}.json  (에이전트가 WebSearch 전에 먼저 Read 한다)

왜: 이 환경의 WebSearch 는 미국 중심이라 한국 중소형주 근거가 잘 안 잡힌다. 해소 근거의 상당수는
    공시 그 자체(공급계약·자사주 소각·밸류업·잠정실적)라서 공식 출처를 코드로 받아 주는 편이 정확하다.

  dart      최근 365일 DART 주요사항보고·거래소공시 (공시명·날짜·접수번호) ← DART list API
  news      최근 1년 네이버 뉴스 — 제목에 종목명 있는 기사만, 최신순 + 관련도순(굵직한 옛 사건) 합침, 월 12건 상한
  telegram  최근 1년 텔레그램 증권 채널 언급 — 종목명이 앞부분에 나오는 글만, 월 10건 상한 (로컬 DB)
  (2026-11-24 수정: grounding.get_news_context 는 display=10 최신순이라 '90일'이 실제로는 최근 일주일이었다.
   텔레그램도 limit 30 이라 같았다. 주가가 왜 빠졌는지는 몇 달 전 사건에 있으므로 1년을 실제로 덮게 했다.)
  reports   최근 1년 증권사 리포트(최대 40건) (증권사·목표가·본문 앞부분) ← 네이버증권 API
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


NEWS_NOISE = ("52주", "[리스트]", "최저가", "최고가", "마법공식", "테마 동향", "테마동향", "상승랠리", "옥석 가리기")


def _strip(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>|&quot;|&amp;|&lt;|&gt;|&apos;", " ", t or "")).strip()


def _thin(items, per_month):
    """월별 상한 — 최근 며칠이 1년 몫을 다 채우지 않게."""
    out, cnt = [], {}
    for x in sorted(items, key=lambda x: x["date"], reverse=True):
        m = x["date"][:7]
        if cnt.get(m, 0) < per_month:
            cnt[m] = cnt.get(m, 0) + 1
            out.append(x)
    return out


def stock_news(code, days=365, max_pages=40):
    """네이버증권 종목 뉴스 피드 (네이버가 종목에 붙인 기사 — 검색어 매칭보다 정확). 중소형주는 1년을 덮는다."""
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    out = []
    for pg in range(1, max_pages + 1):
        r = requests.get(f"https://m.stock.naver.com/api/news/stock/{code}?pageSize=20&page={pg}",
                         headers={**H, "Referer": "https://m.stock.naver.com/"}, timeout=10)
        r.raise_for_status()
        its = [i for g in r.json() for i in g.get("items", [])]
        for it in its:
            t = it.get("datetime") or ""
            if t[:8] >= cut:
                out.append({"date": f"{t[:4]}-{t[4:6]}-{t[6:8]}", "src": it.get("officeName"),
                            "title": _strip(it.get("titleFull") or it.get("title")),
                            "text": _strip(it.get("body"))[:220], "url": it.get("mobileNewsUrl")})
        if len(its) < 20 or (its and (its[-1].get("datetime") or "")[:8] < cut):
            break
    return out


def news(name, code=None, days=365, per_month=12):
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and sec):
        sys.exit("[ERROR] NAVER_CLIENT_ID/SECRET 없음")
    hd = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec}
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = stock_news(code, days) if code else []
    seen = {x["title"] for x in out}
    out = [x for x in out if not any(n in x["title"] for n in NEWS_NOISE)]
    from email.utils import parsedate_to_datetime
    # 대형주는 최신순 1,000건이 하루 치라 관련도순 보조 쿼리로 몇 달 전 굵직한 사건을 건진다
    for q, sort, pages in ((name, "date", 10), (name, "sim", 3), (f"{name} 주가 하락", "sim", 2),
                           (f"{name} 실적", "sim", 2), (f"{name} 목표주가", "sim", 1)):
        for start in range(1, pages * 100, 100):
            r = requests.get("https://openapi.naver.com/v1/search/news.json", headers=hd, timeout=10,
                             params={"query": q, "display": 100, "start": start, "sort": sort})
            r.raise_for_status()   # 조용히 빈 값으로 굳히지 않는다
            its = r.json().get("items") or []
            old = 0
            for it in its:
                d = parsedate_to_datetime(it["pubDate"]).strftime("%Y-%m-%d")
                title = _strip(it.get("title"))
                if d < cut:
                    old += 1
                    continue
                if name not in title or title in seen or any(n in title for n in NEWS_NOISE):
                    continue
                seen.add(title)
                url = it.get("originallink") or it.get("link") or ""
                out.append({"date": d, "src": re.sub(r"^https?://([^/]+).*", r"", url), "title": title,
                            "text": _strip(it.get("description"))[:220], "url": url})
            if len(its) < 100 or (sort == "date" and old == len(its)):
                break
    return _thin(out, per_month)


def telegram(name, code, days=365, per_month=10):
    ctx = G.get_channel_context(name, code, days=days, limit=2000)
    items = [x for x in _items(ctx) if name in x["text"][:150] and len(x["text"]) > 60]
    return _thin(items, per_month)


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


def reports(code, days=365):
    try:
        items = requests.get(f"{NV}/api/stockSecurity/researches/v2/company?itemCodes={code}&index=0&size=40",
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
    try:
        tg = telegram(name, code)
    except Exception as e:
        tg = {"error": repr(e)[:120]}
    doc = {"code": code, "name": name, "built_at": datetime.now().isoformat(timespec="seconds"),
           "dart": dart(code), "news": news(name, code), "telegram": tg,
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
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        docs = list(ex.map(lambda c: pack(names.get(c, c), c), codes))
    for c, d in zip(codes, docs):
        (OUT / f"{c}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {c} {d['name']:<12} {d['counts']}")
        if d["counts"]["dart"] == 0 and d["counts"]["news"] == 0:
            empty.append(c)
    if len(empty) > len(codes) // 2:   # 절반 넘게 공시·뉴스 0건이면 키·네트워크 문제 — 빈 묶음으로 분석하면 안 된다
        sys.exit(f"[ERROR] {len(empty)}/{len(codes)}종목이 공시·뉴스 0건 — DART/NAVER 키·네트워크 확인")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
