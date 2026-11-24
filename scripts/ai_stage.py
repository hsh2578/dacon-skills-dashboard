"""AI 정성 단계의 기계적인 부분 — 에이전트 실행 자체는 /update-data 가 Agent 도구로 한다.

    python scripts/ai_stage.py targets      # 다시 분석할 종목 고르기 → data/screens/_ai_targets.json
    python scripts/ai_stage.py merge        # data/screens/_ai/{code}.json → ai_notes.json (Top N 순서)
    python scripts/ai_stage.py apply-rank   # data/screens/_ranking.json 의 ai_rank 반영 + 판단 기록(judgments record)
    python scripts/ai_stage.py briefs       # briefer 가 _ai/{code}.json 에 쓴 briefing → ai_notes.json (순위 그대로). 없는 종목 목록 출력

briefing 은 ai_notes 안에 있으므로 재사용 종목은 직전 브리핑이 그대로 따라온다 — briefer 는 새로 분석한 종목만 돌면 된다.

targets 규칙 (2026-11-24 — 비용 효율화 + "사실이 바뀔 때만 판정 변경"):
  다시 분석 = Top N 신규 진입 · 직전 분석 이후 새 DART 공시/증권사 리포트 · 당해 EPS 추정치 1개월 변화 ±5% 이상
  재사용   = 위에 해당 없음 → 직전 ai_notes 를 _ai/{code}.json 으로 복사 (ranker 는 전체를 다시 본다)
"""
import json, os, shutil, sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / "data" / "screens"
AI = SC / "_ai"
RES = ROOT / "data" / "research"
JUDG = ROOT / "data" / "judgments" / "latest.json"
REVISION_THRESHOLD = 0.05


def _top():
    return json.load(open(SC / "triple_cross.json", encoding="utf-8"))["top"]


def _changed(code, since):
    """since(YYYYMMDD) 이후 새 사실이 있는지 — 자료 묶음 기준. 사유 목록 반환."""
    p = RES / f"{code}.json"
    if not p.exists():
        return ["자료 묶음 없음"]
    d = json.load(open(p, encoding="utf-8"))
    s = f"{since[:4]}-{since[4:6]}-{since[6:]}"
    why = []
    if any(x["date"] > s for x in d.get("dart") or []):
        why.append("새 공시")
    if any((x.get("date") or "") > s for x in d.get("reports") or [] if isinstance(x, dict)):
        why.append("새 리포트")
    eps = ((d.get("revisions") or {}).get("rows") or {}).get("EPS") or {}
    # '1개월 변화'는 직전 분석 이후 변화가 아니다 — 분석한 지 20일도 안 됐으면 이미 보고 판단한 변화다
    # (2026-11-24: 4일 만에 재실행했더니 18종목이 '추정치 변화'로 잡힘). ponytail: 분석 시점 EPS 를 기록해 비교하면 정확해진다
    fresh = (datetime.now() - datetime.strptime(since, "%Y%m%d")).days < 20
    try:
        if fresh:
            raise ValueError
        now, m1 = float(eps.get("now")), float(eps.get("1m"))
        if m1 and abs(now / m1 - 1) >= REVISION_THRESHOLD:
            why.append(f"추정치 {now / m1 - 1:+.0%}")
    except (TypeError, ValueError):
        pass
    return why


def targets():
    prev = json.load(open(JUDG, encoding="utf-8")) if JUDG.exists() else None
    prev_notes = {}
    if (SC / "ai_notes.json").exists():
        prev_notes = {i["code"]: i for i in json.load(open(SC / "ai_notes.json", encoding="utf-8"))["items"]}
    AI.mkdir(parents=True, exist_ok=True)
    analyze, reuse = [], []
    for r in _top():
        c = r["code"]
        if not prev or c not in prev_notes or c not in {i["code"] for i in prev["items"]}:
            analyze.append({"code": c, "name": r["name"], "why": ["신규 진입" if prev else "첫 실행"]})
            continue
        why = _changed(c, prev["date"])
        if why:
            analyze.append({"code": c, "name": r["name"], "why": why})
        else:
            reuse.append(c)
            notes = dict(prev_notes[c]["ai_notes"])
            p = AI / f"{c}.json"
            if not notes.get("briefing") and p.exists():   # 아직 ai_notes.json 에 병합 안 된 브리핑을 덮어쓰지 않는다 (2026-11-24 10종목 유실)
                old = json.load(open(p, encoding="utf-8"))["ai_notes"]
                if old.get("briefing") and old.get("generated_at") == notes.get("generated_at"):
                    notes["briefing"] = old["briefing"]
            p.write_text(json.dumps({"code": c, "name": r["name"], "ai_notes": notes},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"made_at": datetime.now().isoformat(timespec="seconds"), "previous": prev and prev["date"],
           "analyze": analyze, "reuse": reuse}
    (SC / "_ai_targets.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ai] 분석 {len(analyze)} · 재사용 {len(reuse)}")
    for a in analyze:
        print(f"  {a['code']} {a['name']:<12} {', '.join(a['why'])}")


def merge():
    items, missing = [], []
    for r in _top():
        p = AI / f"{r['code']}.json"
        if not p.exists():
            missing.append(r["code"])
            continue
        d = json.load(open(p, encoding="utf-8"))
        items.append({"code": r["code"], "name": r["name"], "quant_rank": r["rank"], "ai_notes": d["ai_notes"]})
    if missing:
        sys.exit(f"[ERROR] AI 결과 없음 {len(missing)}종목: {missing} — 에이전트를 다시 돌릴 것")
    doc = {"meta": {"generated_at": datetime.now().isoformat(timespec="seconds"), "count": len(items),
                    "framework": "v6 — cause_type 8분류 · expectation_gap(가격 가정 vs 증거) · 자료 묶음(DART·리포트·뉴스) 우선"},
           "items": items}
    (SC / "ai_notes.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ai] 병합 {len(items)}종목 → ai_notes.json")


def apply_rank():
    rk = json.load(open(SC / "_ranking.json", encoding="utf-8"))
    by = {x["code"]: x for x in rk["ranking"]}
    doc = json.load(open(SC / "ai_notes.json", encoding="utf-8"))
    miss = [i["code"] for i in doc["items"] if i["code"] not in by]
    if miss:
        sys.exit(f"[ERROR] ranker 결과에 없는 종목: {miss}")
    for i in doc["items"]:
        i["ai_rank"], i["rerank_reason"] = by[i["code"]]["ai_rank"], by[i["code"]].get("rerank_reason")
    doc["items"].sort(key=lambda i: i["ai_rank"])
    doc["meta"]["ranking"] = {"basis": rk.get("basis"), "ranked_at": rk.get("ranked_at")}
    (SC / "ai_notes.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ai] ai_rank 반영 {len(doc['items'])}종목")
    sys.path.insert(0, str(ROOT / "scripts"))
    import judgments
    judgments.record()


def briefs():
    doc = json.load(open(SC / "ai_notes.json", encoding="utf-8"))
    missing = []
    for i in doc["items"]:
        p = AI / f"{i['code']}.json"
        b = json.load(open(p, encoding="utf-8"))["ai_notes"].get("briefing") if p.exists() else None
        if b:
            i["ai_notes"]["briefing"] = b
        elif not i["ai_notes"].get("briefing"):
            missing.append(f"{i['code']} {i['name']}")
    (SC / "ai_notes.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ai] 브리핑 {len(doc['items']) - len(missing)}/{len(doc['items'])}")
    if missing:
        sys.exit("[ERROR] 브리핑 없음 — briefer 를 돌릴 것: " + ", ".join(missing))


if __name__ == "__main__":
    {"targets": targets, "merge": merge, "apply-rank": apply_rank, "briefs": briefs}[sys.argv[1]]()
