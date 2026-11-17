"""「내 월급의 실질 가치」 데이터 생성.

결합 데이터
  - 고용노동부 사업체노동력조사 월평균 임금총액 (1인 이상 사업체, 산업별)  DT_118N_MON041/051/054
  - e-지방지표 시도별 상용 월평균 임금                                      DT_1YL15006
  - 통계청 소비자물가지수(지출목적별·품목), 생활물가지수, 자가주거비포함지수   DT_1J22001/005/006
  - 소득세법·4대보험 요율(코드로 구현한 간이 세금 계산)

새 지표
  - 실질임금(2025년 원화 기준) — 3가지 물가 잣대(CPI, 생활물가, 자가주거비포함)
  - 세후·보험료 후 '가처분' 실질 월급
  - 품목별 구매력 지수: 같은 월급으로 그 품목을 2015년 대비 몇 % 더/덜 살 수 있나
  - 산업별·시도별 실질임금 변화 순위
  - 2030년까지 실질임금 시나리오
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import kosis

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "wage.json"

BASE = 2025          # 실질가치 기준연도(2025년 원화)
REF = 2015           # 구매력 비교 기준연도
WAGE_START = 2011
PROJ_END = 2030

ITM_TOTAL = "13103110311MD_12"   # 전체임금총액
ITM_REG = "13103110311MD_13"     # 상용임금총액
WAGE_TABLES = [  # (테이블, 산업코드 접두, 기간)
    ("DT_118N_MON041", "15118INDUSTRY_9S", 2011, 2019),
    ("DT_118N_MON051", "190326INDUSTRY_10S", 2020, 2025),
]
WAGE_2026 = ("DT_118N_MON054", "260225INDUSTRY_11S")

SECTIONS = {
    "B": "광업", "C": "제조업", "D": "전기·가스·증기", "E": "수도·하수·폐기물", "F": "건설업",
    "G": "도매·소매업", "H": "운수·창고업", "I": "숙박·음식점업", "J": "정보통신업",
    "K": "금융·보험업", "L": "부동산업", "M": "전문·과학·기술", "N": "사업시설관리·지원",
    "P": "교육서비스업", "Q": "보건·사회복지", "R": "예술·스포츠·여가", "S": "협회·수리·개인서비스",
}

# 소비자물가 품목 (지출목적별 표 DT_1J22001 코드)
CPI_ITEMS = {
    "0": "총지수", "A01": "식료품", "D": "주거·수도·광열", "D01101": "전세", "D01102": "월세",
    "D04201": "공동주택관리비", "D05101": "전기료", "G02101": "휘발유", "G03201": "시내버스료",
    "K01119": "자장면", "K01129": "치킨", "K01127": "김밥", "K01112": "삼겹살(외식)",
    "K01133": "커피(외식)", "K01130": "햄버거", "A01110": "라면", "A01101": "쌀",
    "B01101": "소주", "H03102": "휴대전화료", "J04101": "초등학생학원비", "J01101": "유치원납입금",
}
# 시도 코드(CPI C 분류) -> 표준 시도 / e-지방지표 코드
SIDO = [  # (표준코드, 이름, CPI 코드, e-지방지표 코드)
    ("11", "서울", "T11", "11"), ("26", "부산", "T12", "21"), ("27", "대구", "T13", "22"),
    ("28", "인천", "T14", "23"), ("29", "광주", "T15", "1224"), ("30", "대전", "T16", "25"),
    ("31", "울산", "T17", "26"), ("36", "세종", "T18", "29"), ("41", "경기", "T21", "31"),
    ("51", "강원", "T31", "32"), ("43", "충북", "T41", "33"), ("44", "충남", "T51", "34"),
    ("52", "전북", "T61", "35"), ("46", "전남", "T71", "1236"), ("47", "경북", "T81", "37"),
    ("48", "경남", "T90", "38"), ("50", "제주", "T96", "39"),
]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ 수집

def wages_annual(itm: str):
    """{section: {year: 월평균 임금}} — section '0'은 전체."""
    out: dict[str, dict[int, float]] = {}
    for tbl, pre, y0, y1 in WAGE_TABLES:
        codes = "+".join(pre + s for s in ["0", *SECTIONS])
        rows = kosis.data("118", tbl, itm=itm, objs={1: codes, 2: "size01"}, start=str(y0), end=str(y1))
        for r in rows:
            sec = r["C1"][len(pre):]
            v = num(r["DT"])
            if v:
                out.setdefault(sec, {})[int(r["PRD_DE"])] = v
    return out


def monthly(org, tbl, itm, objs, start, end):
    rows = kosis.data(org, tbl, itm=itm, objs=objs, prd_se="M", start=start, end=end)
    return {r["PRD_DE"]: num(r["DT"]) for r in rows if num(r["DT"])}


def wage_2026_estimate(itm: str, last_annual: float):
    """2026년은 1~N월 누적만 있으므로 (2026 1~N월 평균 / 2025 같은 달 평균) × 2025 연평균으로 추정."""
    tbl, pre = WAGE_2026
    m26 = monthly("118", tbl, itm, {1: pre + "0", 2: "size01"}, "202601", "202612")
    if not m26:
        return None, 0
    months = sorted(m26)
    n = len(months)
    m25 = monthly("118", "DT_118N_MON051", itm, {1: "190326INDUSTRY_10S0", 2: "size01"}, "202501", "202512")
    same = [m25.get("2025" + p[4:]) for p in months]
    if None in same:
        return None, 0
    g = (sum(m26.values()) / n) / (sum(same) / n)
    return last_annual * g, n


def cpi_series(tbl: str, objs_fn, codes: list[str]):
    """연간 지수 + 2026년 잠정(1~최근월 평균 증가율 적용)."""
    out = {}
    rows = kosis.data("101", tbl, objs=objs_fn("+".join(codes)), start="1965", end=str(BASE))
    for r in rows:
        c = r["C2"] if "C2" in r and r.get("C2") in codes else r["C1"]
        v = num(r["DT"])
        if v:
            out.setdefault(c, {})[int(r["PRD_DE"])] = v
    rows = kosis.data("101", tbl, objs=objs_fn("+".join(codes)), prd_se="M", start=f"{BASE}01", end=f"{BASE + 1}12")
    mm: dict[str, dict[str, float]] = {}
    for r in rows:
        c = r["C2"] if "C2" in r and r.get("C2") in codes else r["C1"]
        v = num(r["DT"])
        if v:
            mm.setdefault(c, {})[r["PRD_DE"]] = v
    n26 = 0
    for c, d in mm.items():
        cur = sorted(p for p in d if p.startswith(str(BASE + 1)))
        prev = [d.get(str(BASE) + p[4:]) for p in cur]
        if cur and None not in prev and c in out and BASE in out[c]:
            out[c][BASE + 1] = out[c][BASE] * (sum(d[p] for p in cur) / sum(prev))
            n26 = len(cur)
    return out, n26


# ------------------------------------------------------------------ 세금·보험 (간이)

PENSION_CAP = {  # 국민연금 기준소득월액 상한(원, 연중 적용값 근사)
    2011: 3_750_000, 2012: 3_890_000, 2013: 3_980_000, 2014: 4_080_000, 2015: 4_210_000,
    2016: 4_340_000, 2017: 4_490_000, 2018: 4_680_000, 2019: 4_860_000, 2020: 5_030_000,
    2021: 5_240_000, 2022: 5_530_000, 2023: 5_900_000, 2024: 6_170_000, 2025: 6_370_000,
    2026: 6_590_000,
}
HEALTH = {  # 건강보험료율(전체, %), 장기요양(건보료 대비 %)
    2011: (5.64, 6.55), 2012: (5.80, 6.55), 2013: (5.89, 6.55), 2014: (5.99, 6.55),
    2015: (6.07, 6.55), 2016: (6.12, 6.55), 2017: (6.12, 6.55), 2018: (6.24, 7.38),
    2019: (6.46, 8.51), 2020: (6.67, 10.25), 2021: (6.86, 11.52), 2022: (6.99, 12.27),
    2023: (7.09, 12.81), 2024: (7.09, 12.95), 2025: (7.09, 12.95), 2026: (7.19, 13.14),
}
EMPLOY = {2011: 0.55, 2012: 0.55, 2013: 0.60, 2014: 0.65, 2015: 0.65, 2016: 0.65, 2017: 0.65,
          2018: 0.65, 2019: 0.69, 2020: 0.80, 2021: 0.80, 2022: 0.85, 2023: 0.90, 2024: 0.90,
          2025: 0.90, 2026: 0.90}
PENSION = {y: (4.75 if y >= 2026 else 4.5) for y in range(2011, 2031)}


def _clamp_year(d, y):
    ks = sorted(d)
    return d[min(max(y, ks[0]), ks[-1])]


def insurance(monthly_wage: float, y: int) -> dict:
    cap = _clamp_year(PENSION_CAP, y)
    pension = min(monthly_wage, cap) * PENSION.get(y, 4.75) / 100
    hr, ltc = _clamp_year(HEALTH, y)
    health = monthly_wage * hr / 2 / 100
    care = health * ltc / 100
    emp = monthly_wage * _clamp_year(EMPLOY, y) / 100
    return {"pension": pension, "health": health, "care": care, "employ": emp}


def earned_income_deduction(g: float, y: int) -> float:
    if y <= 2013:
        steps = [(5e6, .8), (15e6, .5), (30e6, .15), (45e6, .10), (math.inf, .05)]
    else:
        steps = [(5e6, .7), (15e6, .4), (45e6, .15), (100e6, .05), (math.inf, .02)]
    d, prev = 0.0, 0.0
    for lim, rate in steps:
        if g > prev:
            d += (min(g, lim) - prev) * rate
        prev = lim
    if y >= 2020:
        d = min(d, 20e6)
    return d


def tax_brackets(y: int):
    if y <= 2011:
        return [(12e6, .06), (46e6, .15), (88e6, .24), (math.inf, .35)]
    if y <= 2013:
        return [(12e6, .06), (46e6, .15), (88e6, .24), (3e8, .35), (math.inf, .38)]
    if y <= 2016:
        return [(12e6, .06), (46e6, .15), (88e6, .24), (1.5e8, .35), (math.inf, .38)]
    if y == 2017:
        return [(12e6, .06), (46e6, .15), (88e6, .24), (1.5e8, .35), (5e8, .38), (math.inf, .40)]
    if y <= 2020:
        return [(12e6, .06), (46e6, .15), (88e6, .24), (1.5e8, .35), (3e8, .38), (5e8, .40), (math.inf, .42)]
    if y <= 2022:
        return [(12e6, .06), (46e6, .15), (88e6, .24), (1.5e8, .35), (3e8, .38), (5e8, .40), (1e9, .42), (math.inf, .45)]
    return [(14e6, .06), (50e6, .15), (88e6, .24), (1.5e8, .35), (3e8, .38), (5e8, .40), (1e9, .42), (math.inf, .45)]


def progressive(base: float, brackets) -> float:
    t, prev = 0.0, 0.0
    for lim, rate in brackets:
        if base > prev:
            t += (min(base, lim) - prev) * rate
        prev = lim
    return t


def income_tax(annual_gross: float, annual_ins: dict, y: int) -> float:
    """1인 가구(부양가족 없음), 비과세 소득 없음, 기타 공제 없음 가정의 근로소득세+지방소득세(연)."""
    g = annual_gross
    earned = g - earned_income_deduction(g, y)
    ded = 1_500_000 + annual_ins["pension"] + annual_ins["health"] + annual_ins["care"] + annual_ins["employ"]
    if y <= 2013:
        ded += 1_000_000  # 표준공제(소득공제)
    base = max(earned - ded, 0)
    calc = progressive(base, tax_brackets(y))
    # 근로소득세액공제
    if y <= 2013:
        credit = calc * .55 if calc <= 500_000 else 275_000 + (calc - 500_000) * .30
        credit = min(credit, 500_000)
    else:
        credit = calc * .55 if calc <= 1_300_000 else 715_000 + (calc - 1_300_000) * .30
        if g <= 33e6:
            lim = 740_000
        elif g <= 70e6:
            lim = max(740_000 - (g - 33e6) * 0.008, 660_000)
        elif g <= 120e6 or y < 2022:
            lim = max(660_000 - (g - 70e6) * 0.5, 500_000)
        else:
            lim = max(500_000 - (g - 120e6) * 0.5, 200_000)
        credit = min(credit, lim)
    std = 130_000 if y >= 2014 else 0  # 표준세액공제
    tax = max(calc - credit - std, 0)
    return tax * 1.1  # 지방소득세 10%


def take_home(monthly_wage: float, y: int) -> dict:
    ins = insurance(monthly_wage, y)
    ann_ins = {k: v * 12 for k, v in ins.items()}
    tax = income_tax(monthly_wage * 12, ann_ins, y) / 12
    total_ins = sum(ins.values())
    net = monthly_wage - total_ins - tax
    return {"gross": monthly_wage, "insurance": total_ins, "tax": tax, "net": net}


# ------------------------------------------------------------------ 계산

def rnd(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def cagr(a, b, years):
    return (b / a) ** (1 / years) - 1


def build():
    # --- 임금
    total = wages_annual(ITM_TOTAL)
    regular = wages_annual(ITM_REG)
    w26, w26_months = wage_2026_estimate(ITM_TOTAL, total["0"][BASE])
    if w26:
        total["0"][BASE + 1] = w26
    r26, _ = wage_2026_estimate(ITM_REG, regular["0"][BASE])
    if r26:
        regular["0"][BASE + 1] = r26

    # --- 물가 (전국)
    cpi, cpi_months = cpi_series("DT_1J22001", lambda c: {1: "T10", 2: c}, list(CPI_ITEMS))
    life, _ = cpi_series("DT_1J22005", lambda c: {1: "T10", 2: c}, ["110"])
    own, _ = cpi_series("DT_1J22006", lambda c: {1: c}, ["20"])
    cpi_all = cpi["0"]
    deflators = {"cpi": cpi_all, "living": life["110"], "ownHousing": own["20"]}

    years = sorted(y for y in total["0"] if y >= WAGE_START)
    last = years[-1]

    def real(v, y, defl="cpi", base=BASE):
        d = deflators[defl]
        return v * d[base] / d[y] if y in d and base in d else None

    nat = []
    for y in years:
        w = total["0"][y]
        th = take_home(w, y)
        nat.append({
            "year": y,
            "estimate": y > BASE,
            "nominal": rnd(w),
            "regular": rnd(regular["0"].get(y)),
            "real": rnd(real(w, y)),
            "realLiving": rnd(real(w, y, "living")),
            "realOwnHousing": rnd(real(w, y, "ownHousing")),
            "net": rnd(th["net"]),
            "netReal": rnd(real(th["net"], y)),
            "tax": rnd(th["tax"]),
            "insurance": rnd(th["insurance"]),
            "burdenRate": round((th["tax"] + th["insurance"]) / w, 4),
            "cpi": round(cpi_all[y], 3) if y in cpi_all else None,
        })

    # --- 품목별 구매력: (임금_t / 임금_REF) / (가격_t / 가격_REF)
    items = []
    for code, name in CPI_ITEMS.items():
        s = cpi.get(code)
        if not s or REF not in s:
            continue
        series = {}
        for y in years:
            if y in s:
                series[y] = round((total["0"][y] / total["0"][REF]) / (s[y] / s[REF]) * 100, 1)
        price_chg = s[last] / s[REF] - 1 if last in s else None
        items.append({
            "code": code, "name": name,
            "priceChange": round(price_chg, 4) if price_chg is not None else None,
            "power": series,
            "powerChange": round(series[last] / 100 - 1, 4) if last in series else None,
            "index": {y: round(v, 2) for y, v in sorted(s.items()) if y >= 2000},
        })
    items.sort(key=lambda r: r["powerChange"] if r["powerChange"] is not None else 0)

    # --- 산업별 (상용임금총액, 2015→2025 실질 변화)
    industries = []
    for sec, name in SECTIONS.items():
        s = regular.get(sec, {})
        if REF in s and BASE in s:
            r0, r1 = real(s[REF], REF), real(s[BASE], BASE)
            industries.append({
                "code": sec, "name": name,
                "nominal2015": rnd(s[REF]), "nominal2025": rnd(s[BASE]),
                "real2015": rnd(r0), "real2025": rnd(r1),
                "realChange": round(r1 / r0 - 1, 4),
                "realCagr": round(cagr(r0, r1, BASE - REF), 4),
                "series": {y: rnd(real(v, y)) for y, v in sorted(s.items())},
            })
    industries.sort(key=lambda r: -r["realChange"])

    # --- 시도별 (상용 월평균 임금 / 시도 CPI)
    rw = kosis.data("101", "DT_1YL15006", itm="T001", objs={1: "ALL"}, start=str(WAGE_START), end=str(BASE))
    rwage: dict[str, dict[int, float]] = {}
    for r in rw:
        rwage.setdefault(r["C1"], {})[int(r["PRD_DE"])] = num(r["DT"])
    rc = kosis.data("101", "DT_1J22001", objs={1: "+".join(s[2] for s in SIDO), 2: "0"}, start=str(WAGE_START), end=str(BASE))
    rcpi: dict[str, dict[int, float]] = {}
    for r in rc:
        rcpi.setdefault(r["C1"], {})[int(r["PRD_DE"])] = num(r["DT"])
    regions = []
    for std, name, ccode, scode in SIDO:
        w, c = rwage.get(scode, {}), rcpi.get(ccode, {})
        if BASE not in w or BASE not in c:
            continue

        def chg(y0):
            if y0 in w and y0 in c:
                return round(w[BASE] / (w[y0] * c[BASE] / c[y0]) - 1, 4)
            return None
        regions.append({
            "code": std, "name": name,
            "nominal2025": rnd(w[BASE]),
            "nominalChange": round(w[BASE] / w[REF] - 1, 4) if REF in w else None,
            "priceChange": round(c[BASE] / c[REF] - 1, 4) if REF in c else None,
            "realChange": chg(REF),            # 2015→2025 (세종은 2020년부터 집계되어 없음)
            "realChange5": chg(BASE - 5),      # 2020→2025 (17개 시도 모두)
            "series": {y: rnd(w[y] * c[BASE] / c[y]) for y in sorted(w) if y in c},
        })
    regions.sort(key=lambda r: -(r["realChange"] if r["realChange"] is not None else -9))

    # --- 2030 시나리오: 명목임금은 최근 5년 연평균 증가율, 물가 3가지 가정
    g_wage = cagr(total["0"][BASE - 5], total["0"][BASE], 5)
    g_cpi5 = cagr(cpi_all[BASE - 5], cpi_all[BASE], 5)
    g_cpi10 = cagr(cpi_all[BASE - 10], cpi_all[BASE], 10)
    scen_defs = {"target": 0.02, "recent10": g_cpi10, "recent5": g_cpi5}
    start_y = last
    w0 = total["0"][start_y]
    p0 = cpi_all.get(start_y, cpi_all[BASE])
    scenarios = {}
    for k, gp in scen_defs.items():
        path = {}
        for y in range(start_y, PROJ_END + 1):
            n = y - start_y
            w = w0 * (1 + g_wage) ** n
            p = p0 * (1 + gp) ** n
            path[y] = {"nominal": rnd(w), "real": rnd(w * cpi_all[BASE] / p), "net": rnd(take_home(w, min(y, 2026))["net"] * cpi_all[BASE] / p)}
        scenarios[k] = {"inflation": round(gp, 4), "path": path}
    # 실질임금 정체 기간: 실질임금이 이전 최고치를 넘지 못한 해
    peak, stagnant = 0, []
    for row in nat:
        if row["real"] <= peak:
            stagnant.append(row["year"])
        peak = max(peak, row["real"])

    # --- 계산기용 데이터
    calc = {
        "cpi": {y: round(v, 3) for y, v in sorted(cpi_all.items())},
        "living": {y: round(v, 3) for y, v in sorted(life["110"].items())},
        "ownHousing": {y: round(v, 3) for y, v in sorted(own["20"].items())},
        "jeonse": {y: round(v, 3) for y, v in sorted(cpi["D01101"].items())},
        "wolse": {y: round(v, 3) for y, v in sorted(cpi["D01102"].items())},
        "wage": {y: rnd(v) for y, v in sorted(total["0"].items())},
        "taxTable": {
            str(m): {str(y): rnd(take_home(m * 10_000, y)["net"]) for y in years}
            for m in (200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 1000)
        },
    }

    first = nat[0]
    b = next(r for r in nat if r["year"] == BASE)
    ref = next(r for r in nat if r["year"] == REF)
    headline = {
        "nominalChange2015": round(b["nominal"] / ref["nominal"] - 1, 4),
        "realChange2015": round(b["real"] / ref["real"] - 1, 4),
        "realLivingChange2015": round(b["realLiving"] / ref["realLiving"] - 1, 4),
        "realOwnHousingChange2015": round(b["realOwnHousing"] / ref["realOwnHousing"] - 1, 4),
        "netRealChange2015": round(b["netReal"] / ref["netReal"] - 1, 4),
        "burden2015": ref["burdenRate"], "burden2025": b["burdenRate"],
        "realChangeFirst": round(b["real"] / first["real"] - 1, 4),
        "wageCagr5": round(g_wage, 4), "cpiCagr5": round(g_cpi5, 4), "cpiCagr10": round(g_cpi10, 4),
        "stagnantYears": stagnant,
    }

    return {
        "meta": {
            "baseYear": BASE, "refYear": REF, "firstYear": WAGE_START, "lastYear": last,
            "estimate2026": {"wageMonths": w26_months, "cpiMonths": cpi_months},
            "assumptions": "세금은 부양가족 없는 1인 근로자·비과세소득 없음·기타 공제 없음 가정의 간이 계산(근로소득세+지방소득세, 국민연금·건강·장기요양·고용보험 근로자 부담분).",
            "sources": [
                "고용노동부 사업체노동력조사 산업/규모별 임금 및 근로시간 (KOSIS DT_118N_MON041, DT_118N_MON051, DT_118N_MON054)",
                "e-지방지표 시도별 상용 월평균 임금 (KOSIS DT_1YL15006)",
                "통계청 소비자물가지수 지출목적별·품목 (KOSIS DT_1J22001)",
                "통계청 생활물가지수 (KOSIS DT_1J22005)",
                "통계청 자가주거비포함 소비자물가지수 (KOSIS DT_1J22006)",
                "소득세법 근로소득공제·세율·근로소득세액공제, 국민연금·건강보험·장기요양·고용보험 요율(연도별)",
            ],
        },
        "headline": headline,
        "national": nat,
        "items": items,
        "industries": industries,
        "regions": regions,
        "scenarios": scenarios,
        "calculator": calc,
    }


if __name__ == "__main__":
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    print(json.dumps(d["headline"], ensure_ascii=False))
    for r in d["national"]:
        print(r)
    print([(i["name"], i["priceChange"], i["powerChange"]) for i in d["items"]])
    print([(i["name"], i["realChange"]) for i in d["industries"]])
    print([(i["name"], i["realChange"], i["realChange5"]) for i in d["regions"]])
    print({k: (v["inflation"], v["path"][2030]) for k, v in d["scenarios"].items()})
