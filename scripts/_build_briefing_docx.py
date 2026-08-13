"""DACON 제출작 — 팀원 브리핑용 Word 문서 생성 (1회용 스크립트)."""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

tc = json.load(open("data/screens/triple_cross.json", encoding="utf-8"))
ai = json.load(open("data/screens/ai_notes.json", encoding="utf-8"))
top_by_code = {t["code"]: t for t in tc["top"]}

doc = Document()
for s in doc.styles:
    try:
        s.font.name = "맑은 고딕"
        s.element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    except Exception:
        pass

for section in doc.sections:
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)


def H1(text, size=22):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size); r.font.bold = True
    r.font.color.rgb = RGBColor(0x0c, 0x0a, 0x09)
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(8)


def H2(text, size=14):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size); r.font.bold = True
    r.font.color.rgb = RGBColor(0x1c, 0x1f, 0x24)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)


def H3(text, size=12):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size); r.font.bold = True
    r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)


def P(text, size=10.5, bold=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    if bold:
        r.font.bold = True
    p.paragraph_format.space_after = Pt(4)


def BULLET(text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    r = p.add_run(text)
    r.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(2)


def TABLE(headers, rows, col_widths=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        run = hdr[i].paragraphs[0].add_run(h)
        run.font.bold = True
        run.font.size = Pt(10)
    for r, row in enumerate(rows):
        cells = t.rows[r + 1].cells
        for i, val in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(val))
            run.font.size = Pt(9.5)
    if col_widths:
        for row in t.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Cm(w)


# 1. 표지
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = title.add_run("PER · PBR Lens")
r.font.size = Pt(32); r.font.bold = True
r.font.color.rgb = RGBColor(0x0c, 0x0a, 0x09)
sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("한국 주식 시계열 가치 평가 + 4팩터 스크리너")
r.font.size = Pt(14); r.font.color.rgb = RGBColor(0x57, 0x53, 0x4e)
doc.add_paragraph()
hint = doc.add_paragraph()
hint.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = hint.add_run("DACON 월간 해커톤 — 투자 데이터를 시각화하라\nSkills 기반 대시보드 설계 출품작")
r.font.size = Pt(11); r.font.color.rgb = RGBColor(0x57, 0x53, 0x4e)

doc.add_paragraph()
prize = doc.add_paragraph()
prize.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = prize.add_run("최종 1등 수상")
r.font.size = Pt(18); r.font.bold = True
r.font.color.rgb = RGBColor(0xe3, 0x1b, 0x1b)
doc.add_paragraph(); doc.add_paragraph()
lb = doc.add_paragraph()
lb.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = lb.add_run("라이브 사이트\nhttps://hsh2578.github.io/dacon-skills-dashboard/\n\nGitHub 저장소\nhttps://github.com/hsh2578/dacon-skills-dashboard")
r.font.size = Pt(11)
doc.add_page_break()

# 2. 한 줄 요약
H1("1. 한 줄 요약 — 이게 뭔가요")
P("DACON 월간 해커톤 · 투자 데이터를 시각화하라 · Skills 기반 대시보드 설계 부문 최종 1등 수상작.", size=11, bold=True)
P(" ")
P("PER · PBR Lens는 한국 주식의 가치투자를 위한 정적 웹 대시보드입니다. KOSPI · KOSDAQ · S&P 500의 60개월 PER/PBR 시계열을 평균±1σ 밴드와 함께 보여주고, 시가총액 3,000억 이상 보통주 303종목 중에서 4팩터 정량 분석 + AI 정성 분석(2단계 랭킹)으로 \"지금 저평가됐고 회복할 가능성이 큰\" Top 10 종목을 골라 카드 UI로 제시합니다.", size=11)
P(" ")
P("한 마디로: \"한국 주식의 PER · PBR 시계열을 한 곳에서 보고, AI가 가치투자 후보를 추려주는 정적 대시보드\".", size=11, bold=True)

H2("왜 이 프로젝트인가")
BULLET("한국 웹에 개별 종목의 PER · PBR 시계열 차트를 정리한 곳이 거의 없다는 시장 갭에서 출발")
BULLET("시장 지수와 개별 종목 300+를 같은 스케일의 60개월 시계열 + 평균±1σ 밴드로 비교 가능")
BULLET("그 위에 4팩터 Z-Score 가치투자 스크리너 + AI 서브에이전트 정성 분석을 결합")
BULLET("Skills.md 명세 기반 대시보드 자동 생성을 실증")

H2("주요 링크")
TABLE(
    ["항목", "주소"],
    [
        ["라이브 사이트", "https://hsh2578.github.io/dacon-skills-dashboard/"],
        ["GitHub 저장소", "https://github.com/hsh2578/dacon-skills-dashboard (public)"],
        ["배포 방식", "GitHub Pages (master 브랜치 root, 정적 호스팅)"],
    ],
    col_widths=[3.5, 12.5],
)
doc.add_page_break()

# 3. 공모전 정보
H1("2. 공모전 정보")
H2("주최 / 주제")
P("DACON 월간 해커톤 — \"투자 데이터를 시각화하라 · Skills 기반 대시보드 설계\"")

H2("일정")
TABLE(
    ["단계", "기한"],
    [
        ["기획서 PDF 제출", "2026-04-30 09:59"],
        ["Skills.md 패키지 .zip 제출", "2026-05-07"],
        ["최종 웹 URL 제출", "2026-05-14"],
        ["1차 대중 투표", "2026-05-14 ~ 2026-05-18"],
        ["2차 내부 심사", "2026-05-18 ~ 2026-05-22"],
    ],
    col_widths=[6, 7],
)

H2("평가 기준 (100점)")
TABLE(
    ["항목", "배점", "핵심"],
    [
        ["범용성", "25", "universe 확장성, 다른 시장·자산 클래스 적용 가능성"],
        ["Skills.md 설계", "25", "Skills.md 명세에 부합하는 룰북 설계 품질"],
        ["대시보드 자동 생성", "25", "Skills.md → 데이터·UI 자동 생성 흐름"],
        ["바이브코딩 활용", "15", "AI 에이전트 · LLM 활용 깊이"],
        ["실용성·창의성", "10", "실제 투자자가 쓸 만한가, 새로운가"],
    ],
    col_widths=[4.5, 1.8, 9.5],
)

H2("결정적 설계 원칙")
P("외부 API 사용 시 심사자가 별도 키 없이 결과를 봐야 함", bold=True)
P("→ 정적 호스팅 채택: 로컬에서 데이터 페치 후 JSON으로 commit, GitHub Pages가 정적으로 서빙. 사이트는 단 한 번의 API 호출도 하지 않음.")
doc.add_page_break()

# 4. 무엇을 만들었나
H1("3. 무엇을 만들었나 — 큰 그림")
H2("아키텍처")
P("로컬 Python 파이프라인이 데이터를 수집·계산하고 JSON으로 commit하면, GitHub Pages가 자동 배포하여 정적 사이트가 그 JSON을 fetch해 그립니다.")
P(" ")
P("  [로컬 Python]", bold=True)
P("     ├─ scripts/fetch_*.py — 시장 지수·universe·매트릭스·컨센서스 수집")
P("     ├─ scripts/apply_triple_cross.py — 4팩터 Z-Score → Top 10 후보")
P("     └─ .claude/agents/ — AI 정성 분석 + ranker 재순위")
P("  → data/*.json commit → GitHub Pages 자동 배포 → [정적 사이트]")

H2("사이트 구성 — 3-Section 단일 페이지 + 종목 상세")
TABLE(
    ["영역", "내용"],
    [
        ["Section 1 — 시장 지수", "KOSPI · KOSDAQ · S&P 500의 PER/PBR/배당수익률/종가를 60개월 시계열 + 평균±1σ 밴드로 표시. 한국은 일별, 미국은 월별."],
        ["Section 2 — Top 10", "4팩터 정량 후보 + AI 재순위로 선정된 가치투자 Top 10을 카드 UI로. 각 카드에 시그널 점수, 투자 포인트, 리스크, 저평가 원인, AI 종합 평가 모두 표시."],
        ["Section 3 — 종목 검색", "universe 303종목 어느 것이든 검색해 60개월 PER · PBR 차트와 통계 · 컨센서스를 볼 수 있음. 30개씩 페이지네이션."],
        ["종목 상세 페이지", "stock.html?code=051500 형식. 시그널 카드 + AI 분석 전체 + PER/PBR/시가총액/주가 4개 차트."],
    ],
    col_widths=[4, 12],
)

H2("핵심 기능 흐름 (사용자 관점)")
BULLET("① 메인 진입 시 KOSPI/KOSDAQ/S&P 500 시계열 비교 차트로 시장 위치 파악")
BULLET("② Top 10 영역에서 4팩터 점수가 높은 저평가 후보 카드를 본다")
BULLET("③ 각 카드의 \"AI 분석 보기\"를 펼치면 정성 모멘텀·리스크·\"왜 저평가인가\" 진단까지 확인")
BULLET("④ 관심 종목 클릭 → 종목 상세 페이지에서 PER/PBR 60개월 시계열·통계·전체 AI 분석 확인")
BULLET("⑤ 또는 검색 영역에서 universe의 어떤 종목이든 PER · PBR 차트로 검증")
doc.add_page_break()

# 5. 핵심 알고리즘
H1("4. 핵심 알고리즘 — 6단계")
H2("Step 1 · Universe 필터링")
P("시가총액 3,000억 이상 보통주만 (우선주·리츠·스팩 제외). 5Y PER 검증(적자분기 ≤ 4Q)으로 신뢰성 확보. Forward PER + 컨센서스 목표가 보유 종목만 통과. → 약 303종목.")

H2("Step 2 · 4팩터 raw 계산")
TABLE(
    ["팩터", "그룹", "공식", "의미"],
    [
        ["s1_per", "Value", "(avg_5y_per − cur) / avg_5y_per", "5년 평균 대비 현재 PER이 얼마나 싼가"],
        ["s1_pbr", "Value", "(avg_5y_pbr − cur) / avg_5y_pbr", "5년 평균 대비 현재 PBR이 얼마나 싼가"],
        ["s3_per", "Growth", "(cur − fwd) / cur", "현재 PER 대비 Forward PER이 얼마나 개선될 것인가"],
        ["upside", "Growth", "(target − cur) / cur", "컨센서스 목표가 대비 상승여력"],
    ],
    col_widths=[2.0, 1.8, 5.0, 7.0],
)

H2("Step 3 · Rank → Z-Score 정규화")
P("각 팩터를 universe 303개 내에서 rank로 변환한 뒤 Z-Score로 정규화. 결측치는 skipna.")

H2("Step 4 · 그룹 합산 → 재 Z-Score")
P("Value = s1_per_z + s1_pbr_z,  Growth = s3_per_z + upside_z 로 합산 후 다시 Z-Score로 정규화.")

H2("Step 5 · 가중 합산 → Top 10 후보")
P("total_score = Value × 0.60 + Growth × 0.40", bold=True)
P("Value 60% / Growth 40% 가중치로 합산. 상위 10종목이 정량 후보. 이 단계까지는 100% 객관·재현 가능.")

H2("Step 6 · AI 정성 분석 → ranker 재순위")
P("AI 서브에이전트가 WebSearch로 정성 모멘텀과 리스크를 조사하고, \"저평가 해소 가능성\" 기준으로 Top 10 순서를 재배열합니다. 4팩터 정량 점수는 변경하지 않습니다.", bold=True)
doc.add_page_break()

# 6. 2단계 랭킹
H1("5. 2단계 랭킹 — 본 프로젝트의 핵심 차별점")
P("\"4팩터로 싼 종목 10개를 뽑은 다음, AI가 그 10개의 순위를 다시 매긴다.\" 두 단계를 명확히 분리한 것이 이 프로젝트의 가장 큰 설계 결정입니다.", size=11)

TABLE(
    ["단계", "역할", "결과 필드"],
    [
        ["4팩터 정량", "후보 선정 — Top 10에 누가 들어오는가", "quant_rank (1~10)"],
        ["AI ranker", "재순위 — 저평가가 해소될 가능성이 큰 순서", "ai_rank (1~10, 화면 표시)"],
    ],
    col_widths=[3.5, 9.0, 3.5],
)

H2("왜 두 단계인가")
BULLET("정량 점수만 보면 모든 종목이 \"왜 싼지\"를 가리지 못한다 → Value Trap(영원히 싼 종목)을 거를 수 없다")
BULLET("AI가 처음부터 종목을 고르면 객관성·재현성이 사라진다 → 평가자가 검증 불가")
BULLET("정량으로 후보 풀을 객관 보장 + AI는 그 안에서 순서만 재배열 = 두 가지 장점 모두 확보")

H2("AI ranker의 판단 축")
P("ranker는 다음 룰을 순서대로 적용해 각 종목의 rerank_score를 계산합니다. 새 사실을 만들지 않고 기존 ai_notes의 출처 태그된 정보만 종합합니다.")
TABLE(
    ["룰", "판단 기준", "점수 가중"],
    [
        ["§4.1 저평가 해소 촉매", "investment_points에 6개월 내 구체적 촉매(날짜·수치 명시)가 몇 건인가", "+3.5 / +2.5 / +1 / −2"],
        ["§4.2 이익 회복 가시성", "실제 분기 실적 턴어라운드·가이던스 상향이 출처와 함께 확인되는가", "+2.5 / +1 / +0.5 / −1.5"],
        ["§4.3 저평가의 정당성", "undervaluation_cause.nature: TEMPORARY 인지 STRUCTURAL 인지", "+1 / −2 / 추가 −1"],
        ["§4.4 단기 노이즈 보정", "TEMPORARY인데 단기 센티 노이즈가 있을 때 강한 촉매면 면제", "0 또는 −0.5"],
        ["§4.5 절대 밸류 페널티", "risks의 [정량] 항목에 \"현재 PER 절대치 매우 높음\" 명시 시", "−0.5"],
        ["§4.6 보조 지표", "evidence_strength · verdict 톤 · risk_level", "미세 가중"],
        ["§4.7 정렬·동점", "내림차순. 동점은 quant_rank가 앞선 종목 우선", "tiebreak"],
    ],
    col_widths=[4.0, 8.5, 3.5],
)

H2("\"왜 저평가인가\" 항목 — undervaluation_cause")
P("각 종목 카드에 \"왜 시장이 이 종목을 싸게 보는가\"를 한 줄로 직접 분석한 항목이 있습니다. nature 필드로 그 원인의 성격을 분류합니다.")
TABLE(
    ["nature", "의미", "시각 표시", "ranker 점수 영향"],
    [
        ["TEMPORARY (일시적)", "단기 비용·일정 지연·센티먼트 위축 — 시간이 지나면 해소 가능", "초록 보더·배지", "+1"],
        ["STRUCTURAL (구조적)", "점유율 잠식·산업 사양화·추세적 가이던스 하향 — 회복 어려움 (Value Trap)", "빨강 보더·배지", "−2 (HIGH 동반 시 추가 −1)"],
    ],
    col_widths=[3.5, 7.0, 2.5, 3.0],
)
doc.add_page_break()

# 7. AI 서브에이전트
H1("6. AI 서브에이전트 — Skills.md 영역의 핵심")
P("정성 분석은 4종의 AI 서브에이전트가 파이프라인으로 처리합니다. 모두 .claude/agents/ 디렉토리의 룰북(YAML frontmatter + 시스템 프롬프트)으로 정의되어, Claude Agent SDK로 호출됩니다. DACON 제출용으로 동일 룰을 6섹션 표준 포맷으로도 정리한 것이 skills/agents/ 폴더입니다.")

TABLE(
    ["에이전트", "역할", "도구", "주요 산출"],
    [
        ["fundamental-analyst", "정성 모멘텀 분석", "WebSearch · Read", "CATALYST_NEAR_TERM, THESIS_DRIVER, RECENT_EARNINGS, UNDERVALUATION_CAUSE"],
        ["risk-analyst", "정성 리스크 분석", "WebSearch · Read", "EXECUTION_RISK, SENTIMENT_RISK, COMPETITIVE_RISK, MACRO_EXPOSURE"],
        ["synthesizer", "두 분석을 종목별 통합", "Read", "ai_notes 객체 (one_liner, investment_points, risks, undervaluation_cause, verdict, evidence_strength, risk_level)"],
        ["ranker (portfolio_ranker)", "10종목 재순위", "Read · model=sonnet", "ai_rank, rerank_reason (저평가 해소 가능성)"],
    ],
    col_widths=[4.0, 3.5, 2.5, 6.0],
)

H2("환각 방지 — 출처 태그 강제")
P("모든 정성 항목 끝에 출처 태그를 의무화하여 LLM 환각을 차단합니다.", bold=True)
TABLE(
    ["태그", "의미"],
    [
        ["[출처: WebSearch · YYYY-MM]", "WebSearch로 확인한 외부 사실 (날짜 명시)"],
        ["확인 필요", "검색 결과가 1년 이상 오래된 경우"],
        ["[정량]", "4팩터 정량 점수에서 인용 (새 수치 생성 금지)"],
    ],
    col_widths=[6.0, 10.0],
)
P(" ")
P("출처 태그가 없는 항목은 출력 금지. 학습 데이터에 있는 사실을 추측으로 인용하는 것도 금지. WebSearch 결과만 사용. 이 규칙으로 \"출처 검증 가능한 정성 분석\"이라는 신뢰도를 확보했습니다.")
doc.add_page_break()

# 8. 데이터·기술
H1("7. 데이터 출처와 기술 스택")
H2("데이터 출처")
TABLE(
    ["데이터", "출처", "용도"],
    [
        ["KOSPI / KOSDAQ 일별 PER · PBR", "KRX (pykrx)", "시장 지수 차트 + universe 시가총액"],
        ["Forward PER · 컨센서스 목표가", "Naver Wisereport", "4팩터 Growth 그룹 + upside 계산"],
        ["S&P 500 월별 PER · PBR · 배당수익률 · 종가", "multpl.com + yfinance", "미국 시장 비교 차트"],
        ["정성 모멘텀·리스크·저평가 원인", "WebSearch (Claude Agent SDK)", "AI 서브에이전트가 매 갱신마다 조사"],
    ],
    col_widths=[6.0, 5.0, 5.0],
)

H2("기술 스택")
TABLE(
    ["영역", "사용 기술"],
    [
        ["데이터 파이프라인", "Python · pandas · pykrx · BeautifulSoup · requests"],
        ["프론트엔드", "Vanilla JS (프레임워크 없음) · HTML5 · CSS3 · Plotly.js 2.35"],
        ["디자인", "Pretendard (CDN, SIL OFL) · JetBrains Mono · CSS Variables 토큰화"],
        ["AI", "Claude Agent SDK — 서브에이전트 (model: sonnet/opus)"],
        ["호스팅", "GitHub Pages (master / root, 정적)"],
        ["빌드", "없음 (정적 파일 그대로 서빙). 캐시버스터로 ?v=N · ?t=Date.now() 처리"],
    ],
    col_widths=[3.5, 12.5],
)

H2("운영 — /update-data 슬래시 커맨드")
P("Claude Code 슬래시 커맨드 한 줄로 전체 파이프라인을 실행합니다.")
TABLE(
    ["명령", "내용", "소요"],
    [
        ["/update-data", "시장 지수 + 매트릭스 + Top 10 점수 + 일별 풀 + AI 정성 (universe 제외)", "약 12분"],
        ["/update-data --full", "위 + universe 재구축 (5Y PER 검증 · 컨센서스 재수집)", "약 30분"],
        ["/update-data --skip-ai", "AI 분석 건너뜀 (정량 데이터만)", "약 10분"],
    ],
    col_widths=[5.0, 8.5, 2.5],
)
P("운영 빈도는 평소 주 1회. AI 정성 분석은 매번 새 WebSearch 결과를 반영하므로 며칠 사이 AI 순위가 흔들릴 수 있어 빈도를 주 1회로 두는 게 정착된 운영 정책입니다.")
doc.add_page_break()

# 9. 현재 Top 10
H1("8. 현재 Top 10 (2026-05-20 기준)")
P("데이터는 매 갱신마다 바뀌므로 아래는 발표 시점의 스냅샷입니다. quant_rank는 4팩터 정량 순위, ai_rank는 AI 재순위(화면에 표시되는 메인 순위).")

rows = []
for it in ai["items"]:
    code = it["code"]
    t = top_by_code.get(code, {})
    name = t.get("name", "?")
    per = t.get("current_per")
    pbr = t.get("cur_pbr")
    fwd = t.get("forward_per")
    nat = it["ai_notes"]["undervaluation_cause"]["nature"]
    rows.append([
        it["ai_rank"],
        "q{}".format(it["quant_rank"]),
        name,
        "{:.1f}".format(per) if per else "-",
        "{:.2f}".format(pbr) if pbr else "-",
        "{:.1f}".format(fwd) if fwd else "-",
        "{:.2f}".format(t.get("total_score", 0)),
        "일시적" if nat == "TEMPORARY" else "구조적",
    ])

TABLE(
    ["AI순", "정량순", "종목명", "PER", "PBR", "Fwd", "4팩터 Z", "저평가 성격"],
    rows,
    col_widths=[1.4, 1.4, 4.2, 1.4, 1.4, 1.4, 1.6, 2.2],
)

P(" ")
H3("관전 포인트")
BULLET("AI 1위 와이지엔터(정량 2위 → AI 1위): BIGBANG 20주년 + BABYMONSTER 월드투어 + 1Q 흑자전환. 강한 촉매가 단기 노이즈 압도")
BULLET("AI 2위 카카오(정량 3위 → AI 2위): 1Q 영업이익 +66% 역대 최대 + 챗GPT 카카오 1,100만 가입")
BULLET("AI 10위 골프존(정량 4위 → AI 10위): 국내 가맹망 포화 · ROE 회귀 = STRUCTURAL Value Trap → 4팩터로는 싸 보였지만 AI가 회복 어려움으로 판정해 최하위로 강등")
BULLET("정량으로는 비슷한 점수지만 AI가 \"왜 싼지\"를 봐서 순위를 의미 있게 다르게 매긴 것이 본 시스템의 가치")
doc.add_page_break()

# 10. 디자인
H1("9. 디자인 시스템")
H2("톤 — 퀀트 리서치 리포트체")
BULLET("이모지 미사용 (검색 input의 아이콘 텍스트 하나만 예외)")
BULLET("명사형 단정문, 평서형 종결. 감정 어휘 · 1인칭 금지")
BULLET("학술 · 증권사 리포트 톤을 일관 유지")

H2("컬러 시스템 — CSS 변수로 토큰화")
TABLE(
    ["토큰", "값", "용도"],
    [
        ["--bg / --surface", "#fafaf9 / #ffffff", "베이스 배경 · 카드 표면"],
        ["--border / --border-strong", "#e7e5e4 / #d6d3d1", "구분선"],
        ["--text / --text-muted", "#0c0a09 / #57534e", "주요 텍스트 · 보조 텍스트"],
        ["--kr-up / --kr-down", "#e31b1b / #1261c4", "한국 시장 색 컨벤션 (빨강 상승 · 파랑 하락)"],
        ["일시적 / 구조적", "#059669 / #dc2626", "\"왜 저평가인가\" 블록 nature 색"],
    ],
    col_widths=[5.0, 4.0, 7.0],
)

H2("폰트 — SIL OFL 라이선스만 사용")
BULLET("Pretendard (한글 본문, CDN)")
BULLET("JetBrains Mono (브랜드 마크에서)")
BULLET("font-feature-settings로 ss03 · kern 활성화 — 숫자 가독성 · 자간 최적화")

H2("반응형")
BULLET("데스크톱 (1440 기준) · 모바일 (390 기준) 양쪽 검증")
BULLET("모바일에서 헤더 nav 풀너비 3등분, 카드 압축형 표시 (투자포인트 3 / 리스크 2 + +N개 상세)")
doc.add_page_break()

# 11. 제출 산출물
H1("10. DACON 제출 산출물 · 최종 결과")
P("DACON 월간 해커톤에서 최종 1등을 수상했습니다.", size=11, bold=True)
P(" ")
TABLE(
    ["제출물", "위치 · 형식", "내용"],
    [
        ["기획서 PDF", "docs/기획서_초안.pdf (1.4 MB)", "프로젝트 개요 · 아키텍처 · 평가 기준 매핑"],
        ["Skills.md 패키지", "skills_submission.zip (~2.45 MB)", ".md 8개 + 같은 내용의 PDF 8개"],
        ["배포 URL", "https://hsh2578.github.io/dacon-skills-dashboard/", "정적 사이트 본체"],
        ["GitHub 저장소 (선택)", "https://github.com/hsh2578/dacon-skills-dashboard", "코드 · 룰북 · 데이터 전체 공개"],
        ["최종 결과", "DACON 월간 해커톤 1등", "Skills 기반 대시보드 설계 부문 수상"],
    ],
    col_widths=[4.0, 5.5, 6.5],
)

H2("Skills.md 패키지 구성")
TABLE(
    ["파일", "역할"],
    [
        ["value_recovery_quant.md", "메인 룰북 — 4팩터 Z-Score 알고리즘 명세"],
        ["forward_attractive.md", "보조 룰북 — 단일 Forward 팩터 스크리너"],
        ["dividend_value.md", "보조 룰북 — 배당+가치 스크리너"],
        ["agents/fundamental_analyst.md", "에이전트 룰북 — 정성 모멘텀"],
        ["agents/risk_analyst.md", "에이전트 룰북 — 정성 리스크"],
        ["agents/synthesizer.md", "에이전트 룰북 — 종목별 통합"],
        ["agents/portfolio_ranker.md", "에이전트 룰북 — 10종목 재순위 (저평가 해소 가능성)"],
        ["README.md", "패키지 설명 · Skills.md 메타 명세 · 새 룰북 추가 가이드"],
    ],
    col_widths=[6.0, 10.0],
)
doc.add_page_break()

# 12. 평가 기준
H1("11. DACON 평가 기준별 강조 포인트")
H2("① 범용성 (25점)")
BULLET("universe는 시가총액 3,000억 이상 보통주 303종목 — 한국 주식 시장의 의미 있는 부분 커버")
BULLET("4팩터 알고리즘은 PER/PBR/Forward만 있으면 어떤 시장이든 적용 가능 (확장성)")
BULLET("S&P 500 월별 데이터를 같은 차트 패턴으로 보여줘 미국 시장 확장 실증")
BULLET("보조 룰북 forward_attractive · dividend_value로 다른 스타일 확장 시나리오 명시")

H2("② Skills.md 설계 (25점)")
BULLET("메인 룰북 1종 + 보조 룰북 2종 + 에이전트 룰북 4종 = 총 7개 룰북 + README")
BULLET("Skills.md 6섹션 표준 포맷 일관 적용 (핵심 컨셉 · 데이터 소스 · 필터 · 점수화 · 시각화 · 인사이트)")
BULLET("§7 메인 룰북과의 관계 · §8 운영 예외 처리 추가로 실무 운영 룰까지 명시")
BULLET("에이전트 룰북은 출처 태그 강제 · 글자수 가이드 · 환각 방지 룰까지 룰북에 직접 인코딩")

H2("③ 대시보드 자동 생성 (25점)")
BULLET("/update-data 슬래시 커맨드 한 줄로 페치 → 점수 → AI 분석 → 검증 → commit/push까지 자동")
BULLET("Skills.md 룰북 변경 시 코드 수정 없이 다음 갱신부터 자동 반영")
BULLET("verify_data.py가 임계값 위반 시 자동으로 commit/push 차단 — stale 데이터 사고 방지")
BULLET("데이터 · UI 코드 분리: data/*.json만 갱신되면 사이트는 그대로 다른 결과 표시")

H2("④ 바이브코딩 활용 (15점)")
BULLET("정성 분석을 100% AI 서브에이전트가 담당 (사람이 손으로 안 씀)")
BULLET("Claude Agent SDK의 서브에이전트 패턴을 4종 파이프라인으로 활용")
BULLET("2단계 랭킹 구조로 AI의 약점(환각 · 재현성 부족)을 정량 후보 선정과 분리해 보완")
BULLET("AI 룰북 자체를 Skills.md 표준에 맞춰 룰북화 — 다른 도메인 에이전트도 같은 패턴으로 확장 가능")

H2("⑤ 실용성·창의성 (10점)")
BULLET("한국 웹에 PER · PBR 시계열 차트를 정리한 곳이 거의 없다 → 실제 시장 갭 보완")
BULLET("AI가 \"왜 저평가인가\"를 직접 분석하고 일시적/구조적까지 분류 — Value Trap을 자동 구분")
BULLET("정량 후보 + AI 재순위의 2단계 구조 — 객관성과 통찰력을 동시에 확보한 새 패턴")
doc.add_page_break()

# 13. 발표 흐름
H1("12. PPT 발표 흐름 제안")
P("총 10~12장 슬라이드 기준 권장 흐름입니다. 평가 기준 25/25/25/15/10에 시간을 비례 배분.")
TABLE(
    ["#", "슬라이드", "핵심 메시지", "권장 시간"],
    [
        ["1", "타이틀", "PER · PBR Lens — 한 줄 정의 + 라이브 URL", "15초"],
        ["2", "문제 정의", "한국 웹에 PER · PBR 시계열이 없다 + 가치투자 종목 선별이 어렵다", "30초"],
        ["3", "솔루션 큰 그림", "정적 호스팅 + 4팩터 정량 + AI 정성 (2단계 랭킹)", "45초"],
        ["4", "사이트 데모 ①", "Section 1 시장 지수 차트 · Section 2 Top 10 카드", "60초"],
        ["5", "사이트 데모 ②", "카드 펼침 — 투자포인트·리스크·\"왜 저평가인가\" 블록 시연", "60초"],
        ["6", "알고리즘 6단계", "4팩터 raw → Z-Score → Top 10 후보 → AI 재순위", "60초"],
        ["7", "2단계 랭킹 핵심", "quant_rank vs ai_rank — Value Trap을 골프존 사례로 시각화", "60초"],
        ["8", "Skills.md 영역", "룰북 8종 + 에이전트 4종 + 출처 태그 강제", "60초"],
        ["9", "자동화 — /update-data", "한 줄로 전체 파이프라인. 룰북 수정만으로 다음 갱신 자동 반영", "45초"],
        ["10", "실용성·창의성", "\"왜 저평가인가\" 직접 분석 + 일시적/구조적 분류 + 한국 시장 갭 보완", "30초"],
        ["11", "제출 산출물 요약", "PDF · zip · URL · GitHub 4종 + 라이브 URL QR 노출", "20초"],
        ["12", "감사 / 질문", "Q&A 슬라이드", "-"],
    ],
    col_widths=[0.8, 4.0, 9.0, 2.2],
)

H2("데모 시연 시 주의")
BULLET("라이브 사이트는 GitHub Pages라 가끔 캐시 지연 — 발표 전 한 번 새로고침해 두면 안전")
BULLET("AI 분석 보기는 토글 — 발표 시 펼친 채로 두고 카드 한 장에 핵심을 모두 노출")
BULLET("\"왜 저평가인가\" 블록의 nature 배지 색(초록=일시적, 빨강=구조적) 강조 — 시각적으로 가장 임팩트 큰 부분")

H2("데모 종목 추천")
BULLET("상승 케이스 — AI #1 와이지엔터: 강한 촉매가 어떻게 정량 2위를 AI 1위로 끌어올렸는지 설명")
BULLET("Value Trap 케이스 — AI #10 골프존: 정량으로는 4위였지만 STRUCTURAL로 분류돼 최하위 강등")
BULLET("두 종목의 대비가 2단계 랭킹의 효용을 즉시 보여주는 가장 강한 데모")
doc.add_page_break()

# 14. 마무리
H1("13. 정리 — 한 장으로 요약")
P("DACON 월간 해커톤 · 투자 데이터를 시각화하라 · Skills 기반 대시보드 설계 부문 최종 1등 수상작.", size=11, bold=True)
P(" ")
H2("이 프로젝트는")
P("한국 주식의 PER · PBR 시계열을 60개월 차트와 평균±1σ 밴드로 보여주고, 4팩터 정량 + AI 정성의 2단계 랭킹으로 가치투자 Top 10을 자동으로 추천하는 정적 웹 대시보드입니다.")

H2("가장 중요한 3가지")
BULLET("① 정적 호스팅 원칙 — 심사자가 키 없이 결과를 볼 수 있도록. 외부 API 호출 0회.")
BULLET("② 2단계 랭킹 — 정량으로 후보 선정(객관·재현 가능) + AI로 재순위(통찰력). 두 단계를 명확히 분리.")
BULLET("③ 출처 태그 강제 — 모든 정성 항목에 WebSearch 출처 의무화로 환각 차단.")

H2("차별점 한 줄")
P("\"같은 사실을 정량으로도 보고 AI로도 보지만, 그 둘을 섞지 않고 단계로 분리해서 객관성과 통찰력을 모두 챙긴 가치투자 대시보드\".", size=11, bold=True)

H2("연락처 / 참고")
TABLE(
    ["항목", "값"],
    [
        ["저장소", "https://github.com/hsh2578/dacon-skills-dashboard"],
        ["라이브", "https://hsh2578.github.io/dacon-skills-dashboard/"],
        ["핵심 룰북", "skills/value_recovery_quant.md (메인) · skills/agents/portfolio_ranker.md (재순위)"],
        ["상세 아키텍처", "CLAUDE.md (저장소 루트)"],
    ],
    col_widths=[3.5, 12.5],
)

out = "docs/발표자료_PER_PBR_Lens_브리핑.docx"
os.makedirs("docs", exist_ok=True)
doc.save(out)
print("생성 완료:", out)
print("파일 크기:", os.path.getsize(out) // 1024, "KB")
