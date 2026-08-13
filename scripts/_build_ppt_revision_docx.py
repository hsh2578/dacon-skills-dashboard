# -*- coding: utf-8 -*-
"""팀원 전달용 'PPT 수정 요청서' .docx 생성 (학교 종합설계 발표용·대시보드 중심·존댓말)."""
import os, sys
os.environ.setdefault("PYTHONUTF8", "1")
sys.stdout.reconfigure(encoding="utf-8")

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT = "맑은 고딕"
ACCENT = RGBColor(0x1A, 0x4D, 0xCC)
DARK = RGBColor(0x22, 0x22, 0x22)
MUTED = RGBColor(0x66, 0x66, 0x66)
RED = RGBColor(0xC0, 0x1B, 0x1B)
GREEN = RGBColor(0x05, 0x96, 0x69)

doc = Document()
style = doc.styles["Normal"]
style.font.name = FONT
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def _set_font(run, size=10.5, bold=False, color=DARK, font=FONT):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), font)


def para(text="", size=10.5, bold=False, color=DARK, space_after=4, space_before=0,
         align=None, font=FONT, indent=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(space_before)
    if align:
        p.alignment = align
    if indent is not None:
        p.paragraph_format.left_indent = Inches(indent)
    if text:
        r = p.add_run(text)
        _set_font(r, size=size, bold=bold, color=color, font=font)
    return p


def runs(p, parts):
    for text, kw in parts:
        r = p.add_run(text)
        _set_font(r, **kw)
    return p


def shade_para(p, hex_color):
    pPr = p._element.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    pPr.append(shd)


def heading(num, text, color=ACCENT):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(f"{num}  {text}")
    _set_font(r, size=14, bold=True, color=color)
    pPr = p._element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "CCCCCC")
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


def code_block(lines):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.1)
    shade_para(p, "F2F4F7")
    for i, ln in enumerate(lines):
        r = p.add_run(ln + ("\n" if i < len(lines) - 1 else ""))
        _set_font(r, size=9.5, bold=False, color=RGBColor(0x33, 0x33, 0x33),
                  font="Consolas")
    return p


def bullet(parts, indent=0.25):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(indent)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run("• ")
    _set_font(r, size=10.5, bold=True, color=ACCENT)
    if isinstance(parts, str):
        parts = [(parts, {})]
    for text, kw in parts:
        r = p.add_run(text)
        _set_font(r, **kw)
    return p


# ============ 표지 ============
para("PER · PBR Lens — 발표 PPT 수정 요청서", size=20, bold=True, color=DARK, space_after=4)
para("산업경영공학 종합설계 · 수업 발표(10분) 슬라이드 보완 사항",
     size=11, color=MUTED, space_after=2)
para("발표 PPT 잘 만들어 주셔서 감사합니다. 아래는 함께 보완하면 좋을 사항들을 정리한 내용입니다.",
     size=10.5, color=DARK, space_after=2)
para("핵심은 '실제 작동하는 대시보드' + '4팩터 알고리즘' + '에이전트의 저평가 진단'을 "
     "잘 보여드리는 것입니다.", size=10.5, bold=True, color=ACCENT, space_after=14)

p = para("", space_after=2)
shade_para(p, "EEF3FF")
runs(p, [
    ("[가장 먼저 봐주셨으면 하는 것]  ", {"size": 10.5, "bold": True, "color": ACCENT}),
    ("① 대시보드 실제 화면 충분히 보여주기  ② 신경망 그림 → 실제 아키텍처로 교체  "
     "③ 4팩터 알고리즘 명확히  ④ 와이지엔터를 '저평가원인→촉매→순위' 스토리로 재구성",
     {"size": 10, "color": DARK}),
])

# ============ 0. 즉시 수정 ============
heading("⛔ 0.", "먼저 바로잡을 부분 (오타 · 오류)", color=RED)
tbl = doc.add_table(rows=1, cols=3)
tbl.style = "Light Grid Accent 1"
tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
hdr = tbl.rows[0].cells
for c, t in zip(hdr, ["위치", "현재", "이렇게 바꿔 주세요"]):
    c.text = ""
    rr = c.paragraphs[0].add_run(t)
    _set_font(rr, size=10, bold=True, color=DARK)
rows = [
    ("표지·목차 제목", "PER/PBR/LEANS", "PER/PBR/LENS (사이트명이 PER·PBR Lens입니다)"),
    ("Page 3 우측 '대시보드 설계 구조'", "신경망(Feed-forward) 그림", "딥러닝이 아니므로 아래 실제 아키텍처로 교체"),
    ("본문 헤더 번호", "03~15, 11·12 중복", "목차(01~09)에 맞춰 다시 매겨 주세요"),
]
for r0 in rows:
    cells = tbl.add_row().cells
    for c, t in zip(cells, r0):
        c.text = ""
        rr = c.paragraphs[0].add_run(t)
        _set_font(rr, size=9.5, color=DARK)

para("▶ Page 3 신경망 그림 대신 넣을 실제 아키텍처입니다 (이대로 그려 주시면 됩니다):",
     size=10, bold=True, color=DARK, space_before=8, space_after=2)
code_block([
    "[로컬 Python 파이프라인]                  [정적 호스팅]",
    " fetch_*.py  (시장·universe·컨센서스)",
    "      ↓                                   GitHub Pages",
    " apply_triple_cross.py → data/*.json  →   (서버 0원,",
    " (4팩터 → Top10 후보)    commit/push        API키 노출 0)",
    "      ↓                                        ↓",
    " AI 에이전트 → ai_notes.json               정적 대시보드 (PER·PBR Lens)",
    "",
    "* 외부 API 키 없이 누구나 바로 접속해 확인 가능한 정적 호스팅 구조입니다.",
])

# ============ 1. 대시보드 중심 ============
heading("🔵 1.", "대시보드(결과물)를 충분히 보여주기 — 발표의 본체")
p = para("", space_after=4)
runs(p, [
    ("종합설계 발표에서 가장 중요하게 평가받는 부분은 ", {"size": 10.5, "color": DARK}),
    ("'실제로 작동하는 산출물'", {"size": 10.5, "bold": True, "color": ACCENT}),
    ("이라고 생각합니다. 현재 PPT에는 폰 목업 1장(Page 9)만 있어서, 대시보드 3개 섹션을 "
     "실제 화면 캡처로 충분히 보여주시면 좋겠습니다.", {"size": 10.5, "color": DARK}),
])
para("[신규/보강 슬라이드] 제목 예시: \"PER·PBR Lens 대시보드 — 3개 섹션\"",
     size=10, bold=True, color=DARK, space_before=4, space_after=2)
code_block([
    "Section 1  시장 지수      KOSPI·KOSDAQ·S&P500 + 과거 평균 대비 ±1σ 밴드",
    "Section 2  Top 10        4팩터로 뽑은 저평가 후보 + AI 순위 카드",
    "Section 3  종목 검색      아무 종목이나 PER/PBR 60개월 시계열 차트",
    "",
    "+ 종목 상세 페이지(stock.html): 시그널 카드 + AI 분석 + PER/PBR 차트",
])
bullet([("실제 사이트 화면을 그대로 캡처해서 넣어 주세요. ", {"size": 10.5, "bold": True, "color": DARK}),
        ("데스크톱(1440)/모바일(390) 두 화면이 함께 있으면 '반응형'도 어필됩니다.",
         {"size": 10.5, "color": DARK})])
bullet([("가능하면 발표 중 사이트를 직접 라이브 시연하면 좋습니다. ",
         {"size": 10.5, "bold": True, "color": DARK}),
        ("정적 호스팅이라 인터넷만 되면 즉시 열립니다. 가장 확실한 한 방입니다.",
         {"size": 10.5, "color": DARK})])
p = para("", space_after=8)
p.paragraph_format.left_indent = Inches(0.25)
runs(p, [("사이트 주소: ", {"size": 9.5, "bold": True, "color": MUTED}),
         ("https://hsh2578.github.io/dacon-skills-dashboard/", {"size": 9.5, "color": ACCENT})])

# ============ 2. 알고리즘 ============
heading("🟡 2.", "4팩터 알고리즘 — 발표의 알맹이 (전용 2장으로 보강)")
p = para("", space_after=6)
runs(p, [
    ("산업경영공학 발표인 만큼 ", {"size": 10.5, "color": DARK}),
    ("방법론(어떻게 계산하는가)이 가장 중요", {"size": 10.5, "bold": True, "color": RED}),
    ("하다고 생각합니다. 현재 PPT는 '다차원 Z-Score'로만 표현되어 다소 부실해 보입니다. "
     "아래처럼 파이프라인 1장 + 설계의도·계산예시 1장으로 나눠 보여주시면 좋겠습니다.",
     {"size": 10.5, "color": DARK}),
])

para("[알고리즘 슬라이드 ①]  5단계 정량 파이프라인",
     size=11, bold=True, color=ACCENT, space_before=4, space_after=2)
code_block([
    "[0] Universe 정제",
    "    시총 3,000억+ 보통주 (우선주·리츠·스팩 제외)",
    "    + 5년간 적자분기 ≤ 4Q + Forward PER·컨센 목표가 보유  →  303종목",
    "",
    "[1] 4팩터 raw 계산  (종목별, 큰 값일수록 더 매력적)",
    "  Value  ① s1_per = (5Y평균 PER − 현재 PER) / 5Y평균 PER",
    "         ② s1_pbr = (5Y평균 PBR − 현재 PBR) / 5Y평균 PBR",
    "  Growth ③ s3_per = (현재 PER − Forward PER) / 현재 PER",
    "         ④ upside = (컨센 목표가 − 현재가) / 현재가",
    "",
    "[2] Rank → Z-Score 정규화",
    "    각 팩터를 universe 내 순위(rank)로 변환 후 Z-Score(평균0·표준편차1)",
    "",
    "[3] 그룹 합산   value_raw = z①+z②   growth_raw = z③+z④",
    "",
    "[4] Re-Z (그룹 간 분포 일치)",
    "    value_score = Z(value_raw)   growth_score = Z(growth_raw)",
    "",
    "[5] 가중 합산 → 후보 선정",
    "    total = value_score × 0.60 + growth_score × 0.40",
    "    → 내림차순 상위 10 = 정량 후보 (quant_rank)",
])

para("[알고리즘 슬라이드 ②]  설계 의도 + 실제 계산 예시 (와이지엔터)",
     size=11, bold=True, color=ACCENT, space_before=8, space_after=2)
bullet([("왜 Rank → Z-Score를 쓰나요? ", {"size": 10.5, "bold": True, "color": DARK}),
        ("원시 비율은 극단값(outlier) 한두 종목에 휘둘립니다. 순위로 바꾸면 분포가 균일해지고, "
         "Z-Score로 평균0·표준편차1을 맞추면 단위·스케일이 전혀 다른 4팩터를 공정하게 합산할 수 "
         "있습니다. (임의 절단(winsorize)이 필요 없습니다.)", {"size": 10.5, "color": DARK})])
bullet([("왜 Value 0.6 > Growth 0.4 인가요? ", {"size": 10.5, "bold": True, "color": DARK}),
        ("1차 목적이 '저평가' 발굴이라 가치 비중을 높였습니다. 성장은 회복 탄력을 보조하는 "
         "역할입니다.", {"size": 10.5, "color": DARK})])
para("▼ 실제 계산 예시 (와이지엔터)", size=10, bold=True, color=DARK,
     space_before=4, space_after=2)
code_block([
    "Value_score = +1.49     Growth_score = +1.94",
    "total = 0.60 × 1.49 + 0.40 × 1.94 = 1.67   →  정량 후보 #2",
    "",
    "→ 이어서 2단계(에이전트): 저평가 원인=일시적 + 촉매 명확  →  AI #1 로 승격",
])
p = para("", space_after=8)
shade_para(p, "EEF3FF")
runs(p, [
    ("2단계 랭킹 한 줄 정의:  ", {"size": 10, "bold": True, "color": ACCENT}),
    ("1단계 Top 10 후보 선정 = 정량 100% (4팩터, 그 내부 가중치가 Value 0.6·Growth 0.4) / "
     "2단계 화면 순위(ai_rank) = 정성 100% (에이전트가 '저평가 해소 가능성'으로 재배열, "
     "정량 점수는 섞지 않고 동점일 때만 tiebreak).", {"size": 10, "color": DARK}),
])

# ============ 3. 핵심 논리 ============
heading("🟠 3.", "저평가 진단 논리 — '60/40'과 '일시적/구조적' 표현 보완")
para("우리 시스템의 차별점인데 '+3.5~−2.0 점수표'라는 기계적 표현으로만 나와서, 추론 과정이 잘 "
     "드러나지 않습니다. 아래처럼 보완하면 좋겠습니다.", size=10.5, color=DARK, space_after=6)

bullet([("(a) '60% 정량 + 40% AI 정성 융합' 표현 보완 ",
         {"size": 10.5, "bold": True, "color": DARK}),
        ("(Page 3·5·6·7·8·11)", {"size": 9.5, "color": MUTED})])
p = para("", space_after=2)
p.paragraph_format.left_indent = Inches(0.5)
runs(p, [("· 현재 표현: ", {"size": 10, "bold": True, "color": RED}),
         ("\"60% 정량 + 40% AI 정성을 가중 융합\"", {"size": 10, "color": DARK})])
p = para("", space_after=2)
p.paragraph_format.left_indent = Inches(0.5)
runs(p, [("· 권장 표현: ", {"size": 10, "bold": True, "color": GREEN}),
         ("'Top10 후보 선정 = 정량 100%, 화면 순위 = 정성 100%'의 2단계 구조입니다. "
          "60/40은 정량 단계 '내부'의 Value/Growth 비율일 뿐, 정량과 정성을 60:40으로 섞는 "
          "것이 아닙니다.", {"size": 10, "color": DARK})])
p = para("", space_after=8)
p.paragraph_format.left_indent = Inches(0.5)
runs(p, [("· 이유: ", {"size": 9.5, "bold": True, "color": MUTED}),
         ("'60% 정량 + 40% 정성 융합'으로 쓰면 'AI 가중치가 40%냐'는 질문에 답이 꼬입니다. "
          "정량(후보 선정)과 정성(순위 결정)은 섞이지 않고 단계가 분리돼 있습니다.",
          {"size": 9.5, "color": MUTED})])

bullet([("(b) '일시적 vs 구조적' 저평가 판별을 결과로 보여주기",
         {"size": 10.5, "bold": True, "color": DARK})])
p = para("", space_after=8)
p.paragraph_format.left_indent = Inches(0.5)
runs(p, [("Page 4는 문제로 '원인이 일시적인지 구조적인지 못 읽는다'를 제기하는데, 해결 슬라이드에서 "
          "이를 받지 못하고 있습니다. 에이전트가 저평가 원인을 'TEMPORARY(일시적)/STRUCTURAL(구조적)'"
          "으로 판별하고, 대시보드에 초록=일시적 / 빨강=구조적 색으로 표시한다는 점을 화면 캡처로 "
          "보여주시면 좋겠습니다.", {"size": 10, "color": DARK})])

# ============ 4. 와이지엔터 ============
heading("🟢 4.", "와이지엔터 사례 재구성 (Page 14·15) — 발표의 클라이맥스")
p = para("", space_after=6)
runs(p, [
    ("지금은 정량 수치·매크로 내용만 있습니다. ", {"size": 10.5, "color": DARK}),
    ("'왜 저평가 → 어떻게 해소 → 그래서 1위'", {"size": 10.5, "bold": True, "color": ACCENT}),
    (" 스토리로 바꾸면 좋겠습니다. 아래는 실제 데이터 그대로라 사실 검증이 끝난 내용입니다 "
     "(대시보드 종목 상세 화면을 함께 띄우면 완벽합니다).", {"size": 10.5, "color": DARK}),
])
code_block([
    "#1 와이지엔터테인먼트  (정량 후보 #2 → AI 최종 #1 승격)",
    "",
    "[1단계 저평가 원인 진단]",
    "  BLACKPINK 투어 MD 부진·앨범 지연으로 컨센 하향",
    "  + 엔터 섹터 센티먼트 위축",
    "  → 판정: 일시적(TEMPORARY)   [출처: WebSearch·2026-04]",
    "",
    "[2단계 '이 악재는 풀리는가?' 촉매 점검]",
    "  · 1Q26 흑자전환 (영업익 95.3억, 매출 +14.7%)",
    "  · BIGBANG 20주년 'REBORN' 월드투어 + 신앨범",
    "  · BABYMONSTER 5대륙 월드투어 (전작 30만 관객 → 확대)",
    "  · 6년 만의 신인 보이그룹 9월 데뷔 + 차기 걸그룹",
    "  → 단일 IP 의존 약점을 신규 IP 파이프라인으로 해소",
    "",
    "[3단계 최종 판정]",
    "  단기 노이즈 < 해소 촉매  →  quant #2 를 AI #1 로 승격",
    "  (정량 Z=+1.67 / Value +1.49 · Growth +1.94)",
])
p = para("", space_after=10)
shade_para(p, "EEF3FF")
runs(p, [
    ("발표 멘트 예시:  ", {"size": 10, "bold": True, "color": ACCENT}),
    ("\"숫자만 보면 #2였지만, 에이전트가 '저평가가 일시적이고 풀릴 촉매가 명확하다'고 "
     "읽어 #1로 올렸습니다.\"", {"size": 10, "color": DARK}),
])

# ============ 5. 슬라이드 통폐합 ============
heading("✂️ 5.", "중복 슬라이드 정리 제안 (16장 → 약 12~13장)")
para("같은 사실(303 universe / 60·40 / Value Trap / 비용 0원)이 7장에 걸쳐 반복되고 있습니다. "
     "10분 발표에는 다소 많아 보여서, 아래 슬라이드는 정리하면 좋겠습니다.",
     size=10.5, color=DARK, space_after=6)
tbl2 = doc.add_table(rows=1, cols=3)
tbl2.style = "Light Grid Accent 1"
tbl2.alignment = WD_TABLE_ALIGNMENT.CENTER
for c, t in zip(tbl2.rows[0].cells, ["슬라이드", "겹치는 부분", "제안"]):
    c.text = ""
    rr = c.paragraphs[0].add_run(t)
    _set_font(rr, size=10, bold=True, color=DARK)
cut_rows = [
    ("Page 5 (IBB/MMD/MDL)", "Page 4 문제점과 내용 중복", "삭제 또는 4에 흡수"),
    ("Page 6 (기회 배경/성장)", "Page 3 + 4와 거의 동일", "삭제 권장"),
    ("Page 11 (가치창출 4요소)", "Page 3 Exec Summary와 같은 4포인트", "삭제 또는 3과 통합"),
    ("Page 10 (비용/응답 4분면)", "추상적이고 메시지가 약함", "삭제 또는 아키텍처에 흡수"),
    ("Page 13 (3-Track)", "실제 시스템에 없는 발표용 내러티브", "삭제 권장"),
    ("Page 15 (과열요인 YG 요약)", "Page 14 YG와 중복", "14로 통합"),
]
for r0 in cut_rows:
    cells = tbl2.add_row().cells
    for c, t in zip(cells, r0):
        c.text = ""
        rr = c.paragraphs[0].add_run(t)
        _set_font(rr, size=9.5, color=DARK)

para("▶ 정리 후 권장 구성입니다 (대시보드 + 알고리즘 중심, 약 13장):",
     size=10, bold=True, color=DARK, space_before=8, space_after=2)
code_block([
    "1 표지    2 목차    3 문제 (일시적 vs 구조적 저평가, 코리아 디스카운트)",
    "4 4팩터 알고리즘 ① 5단계 파이프라인          (보강)",
    "5 4팩터 알고리즘 ② 설계의도 + 계산예시(YG)   (보강)",
    "6 실제 아키텍처 (현 Page 3 교체분 — 정적호스팅·비용0)",
    "7 대시보드 화면 ① 시장 지수",
    "8 대시보드 화면 ② Top 10 + AI 순위 카드      (핵심)",
    "9 대시보드 화면 ③ 종목 검색·PER/PBR 차트",
    "10 와이지엔터 클라이맥스: 원인→촉매→순위      (재구성)",
    "11 (선택) 결론·의의·한계·향후   12 Q&A",
])

# ============ 6. 자잘 ============
heading("🩶 6.", "그 외 사소한 부분")
bullet([("Page 12 Two-Track / Page 13 3-Track: ", {"size": 10.5, "bold": True, "color": DARK}),
        ("실제 구현된 개념이 아니라 발표용 내러티브입니다. '분석 관점'임을 명시하거나 톤을 낮추는 "
         "것이 좋겠습니다(질문받으면 방어가 어렵습니다).", {"size": 10.5, "color": DARK})])
bullet([("슬라이드 텍스트가 다소 빽빽합니다. ", {"size": 10.5, "bold": True, "color": DARK}),
        ("장당 핵심 1줄 + 말로 설명하는 구조가 좋겠습니다. 10분 안에 다 읽기 어렵습니다.",
         {"size": 10.5, "color": DARK})])

# ============ 요약 ============
heading("✅", "정리")
p = para("", space_after=4)
shade_para(p, "F2F4F7")
runs(p, [
    ("디자인은 정말 좋습니다. 여기에 ", {"size": 10.5, "color": DARK}),
    ("(1) 대시보드 실제 화면 충분히 보여주기, (2) 신경망 그림 → 실제 아키텍처 교체, "
     "(3) 4팩터 알고리즘 명확히, (4) 와이지엔터를 '저평가원인→촉매→순위' 스토리로 재구성, "
     "(5) 중복 슬라이드 정리",
     {"size": 10.5, "bold": True, "color": ACCENT}),
    (" 까지 더해지면 '무엇을 만들었는지'가 훨씬 분명해질 것 같습니다. 고생 많으셨습니다!",
     {"size": 10.5, "color": DARK}),
])

out = "PPT_수정요청_PER-PBR-Lens.docx"
doc.save(out)
print("saved:", os.path.abspath(out))
