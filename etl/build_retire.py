"""「은퇴 후 대한민국」 데이터 생성.

결합 데이터
  - 완전생명표(1세별) 기대여명 (KOSIS DT_1B42) + 장래 생명표 (DT_1BPA202)
  - 연금통계: 65세 이상 연금 종류별 수급률·월평균 수급액 (DT_1PEN_006)
  - 가계동향조사: 가구주 연령별 월평균 소비지출·항목별 (DT_1L9U108, 전국 1인 이상)
  - 소비자물가지수 지출목적별 (DT_1J22001)
  - 국민노후보장패널: 필요 최소·적정 노후생활비 (국민연금연구원, DT_322001_D003)
  - 주민등록 기반 인구추계 (pop.py)

새 지표
  - 필요 노후자금 = 월 생활비 × 12 × 기대여명 (실질, 오늘 가격)
  - 연금 공백 = (적정 생활비 − 평균 연금 수급액) × 12 × 기대여명
  - 고령가구 체감물가 = 60세 이상 가구 지출 비중으로 가중한 CPI 상승률
  - 부양 구조 = 20~64세 / 65세 이상, 연금 수급자 추계
  - 자금 소진 연령 = 자산·수익률·물가 시나리오별 시뮬레이션
"""
from __future__ import annotations

import json
from pathlib import Path

import kosis

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "retire.json"

CPI_CATS = {  # CPI 지출목적 코드 -> (가계동향 코드, 이름)
    "A": ("H", "식료품·비주류음료"),
    "B": ("J", "주류·담배"),
    "C": ("K", "의류·신발"),
    "D": ("L", "주거·수도·광열"),
    "E": ("M", "가정용품·가사서비스"),
    "F": ("N", "보건"),
    "G": ("O", "교통"),
    "H": ("P", "통신"),
    "I": ("Q", "오락·문화"),
    "J": ("S", "교육"),
    "K": ("T", "음식·숙박"),
    "L": ("U", "기타 상품·서비스"),
}
HH_GROUPS = {"G0": "전체 가구", "G3": "50~59세", "G9": "60~69세", "G7": "65세 이상", "G8": "70세 이상", "G4": "60세 이상"}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def r1(x, n=1):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- 기대여명

def life_table():
    m = kosis.meta("101", "DT_1B42")
    codes = [(r["ITM_ID"], r["ITM_NM"]) for r in m if r["OBJ_ID"] == "C" and r["ITM_ID"] != "000"]
    age_of = {}
    for c, nm in codes:
        a = int("".join(ch for ch in nm if ch.isdigit()))
        age_of[c] = a
    rows = kosis.data("101", "DT_1B42", itm="T6+T16+T26", objs={1: "ALL"}, start="1970", end="2030")
    sexmap = {"T6": "all", "T16": "male", "T26": "female"}
    by = {}
    for r in rows:
        a = age_of.get(r["C1"])
        v = num(r["DT"])
        if a is None or v is None:
            continue
        by.setdefault(int(r["PRD_DE"]), {}).setdefault(sexmap[r["ITM_ID"]], {})[a] = v
    latest = max(by)
    table = {s: [r1(by[latest][s].get(a), 2) for a in range(40, 101)] for s in ("all", "male", "female")}
    hist = {
        str(a): {s: {y: r1(by[y][s].get(a), 2) for y in sorted(by) if by[y].get(s, {}).get(a) is not None} for s in ("male", "female")}
        for a in (60, 65)
    }
    return latest, table, hist


def future_life():
    """장래 생명표(중위) 60-64세·65-69세 기대여명 (5세 연령군 첫 나이 기준)."""
    rows = kosis.data("101", "DT_1BPA202", itm="T40", objs={1: "1", 2: "ALL", 3: "260+280"}, start="2025", end="2072")
    out = {"60": {"male": {}, "female": {}}, "65": {"male": {}, "female": {}}}
    for r in rows:
        a = "60" if r["C3"] == "260" else "65"
        s = "male" if r["C2"] == "1" else "female"
        out[a][s][int(r["PRD_DE"])] = num(r["DT"])
    return out


# ---------------------------------------------------------------- 연금

def pensions():
    rows = kosis.data("101", "DT_1PEN_006", objs={1: "ALL", 2: "ALL", 3: "ALL"}, start="2016", end="2030")
    names = {"PN": "전체(하나 이상)", "BD": "기초·장애인연금", "NP": "국민연금", "JIK": "직역연금", "RP": "퇴직연금", "PP": "개인연금", "HS": "주택연금", "FP": "농지연금"}
    out = {}
    for r in rows:
        if r.get("C2") != "00":
            continue
        k, it, y, v = r["C3"], r["ITM_ID"], int(r["PRD_DE"]), num(r["DT"])
        d = out.setdefault(k, {"name": names.get(k, r["C3_NM"]), "rate": {}, "mean": {}, "median": {}, "recipients": {}})
        if it == "T4":
            d["rate"][y] = v
        elif it == "T7":
            d["mean"][y] = v * 1000 if v is not None else None
        elif it == "T21":
            d["median"][y] = v * 1000 if v is not None else None
        elif it == "T1":
            d["recipients"][y] = v * 1000 if v is not None else None
    by_age = {}
    for r in rows:
        if r.get("C3") != "PN" or r.get("C2") == "00":
            continue
        g = by_age.setdefault(r["C2_NM"], {})
        if r["ITM_ID"] == "T7":
            g.setdefault("mean", {})[int(r["PRD_DE"])] = num(r["DT"]) * 1000
        elif r["ITM_ID"] == "T4":
            g.setdefault("rate", {})[int(r["PRD_DE"])] = num(r["DT"])
    return out, by_age


# ---------------------------------------------------------------- 가계지출

def household():
    items = ["F", "D", "W", "2"] + [v[0] for v in CPI_CATS.values()] + ["L1", "N4", "N7", "N1"]
    rows = kosis.data("101", "DT_1L9U108", itm="T110", objs={1: "+".join(HH_GROUPS), 2: "+".join(items)}, start="2019", end="2030")
    out = {}
    for r in rows:
        v = num(r["DT"])
        out.setdefault(r["C1"], {}).setdefault(int(r["PRD_DE"]), {})[r["C2"]] = v
    return out


def cpi():
    rows = kosis.data("101", "DT_1J22001", objs={1: "T10", 2: "+".join(["0"] + list(CPI_CATS))}, start="2000", end="2030")
    out = {}
    for r in rows:
        out.setdefault(r["C2"], {})[int(r["PRD_DE"])] = num(r["DT"])
    return out


def living_cost():
    rows = kosis.data("322", "DT_322001_D003", objs={1: "A00+A0203+A0204", 2: "B0101+B0102+B0201+B0202"}, prd_se="F", start="2009", end="2030")
    names = {"B0101": "minCouple", "B0102": "minSingle", "B0201": "adeqCouple", "B0202": "adeqSingle"}
    out = {}
    for r in rows:
        v = num(r["DT"])
        out.setdefault(r["C1"], {}).setdefault(names[r["C2"]], {})[int(r["PRD_DE"])] = v * 1000 if v is not None else None
    return out


# ---------------------------------------------------------------- 조합

def cagr(series, y0, y1):
    a, b = series.get(y0), series.get(y1)
    if not a or not b:
        return None
    return (b / a) ** (1 / (y1 - y0)) - 1


def depletion_age(start_age, asset, monthly_need, monthly_pension, real_return, life_end=100):
    """실질 기준 시뮬레이션: 매년 (필요−연금)×12 인출, 실질 수익률 적용. 소진 나이 반환(없으면 None)."""
    bal = asset
    gap = (monthly_need - monthly_pension) * 12
    for age in range(start_age, life_end + 1):
        bal = bal * (1 + real_return) - gap
        if bal < 0:
            return age
    return None


def dependency(popr):
    proj, total = popr["proj"], popr["total"]
    out = {}
    for s in ("low", "mid", "high"):
        out[s] = {}
        for y in list(range(2015, 2026)) + list(range(2026, 2051)):
            ages = total[y]["00"] if y <= 2025 else proj["00"][s][y]
            old = sum(ages[65:])
            work = sum(ages[20:65])
            out[s][y] = {"old": round(old), "work": round(work), "ratio": round(work / old, 2), "share65": round(old / sum(ages), 4),
                         "old75": round(sum(ages[75:])), "old85": round(sum(ages[85:]))}
    return out


def build():
    ly, table, le_hist = life_table()
    le_future = future_life()
    pens, pens_age = pensions()
    hh = household()
    c = cpi()
    lc = living_cost()

    try:
        import run_all
        popr = run_all.population()
        dep = dependency(popr)
    except Exception as e:  # 인구 캐시가 없으면 부양 구조 생략
        print("인구 추계 없음:", e)
        dep = None

    hh_year = max(hh["G7"])
    cpi_year = max(y for y in c["0"] if c["0"][y])
    # 고령가구 체감물가: 65세 이상 가구 지출 비중 가중 (10년 CAGR)
    y0 = cpi_year - 10
    cats = []
    w_old = w_all = 0.0
    infl_old = infl_all = 0.0
    for ck, (hk, name) in CPI_CATS.items():
        g = cagr(c.get(ck, {}), y0, cpi_year)
        so = (hh["G7"][hh_year].get(hk) or 0) / hh["G7"][hh_year]["F"]
        sa = (hh["G0"][hh_year].get(hk) or 0) / hh["G0"][hh_year]["F"]
        cats.append({"code": ck, "name": name, "cagr10": r1(g * 100, 2) if g is not None else None,
                     "share65": round(so, 4), "shareAll": round(sa, 4),
                     "spend65": round(hh["G7"][hh_year].get(hk) or 0), "spendAll": round(hh["G0"][hh_year].get(hk) or 0)})
        if g is not None:
            infl_old += so * g
            w_old += so
            infl_all += sa * g
            w_all += sa
    elderly_cpi = infl_old / w_old
    general_cpi = cagr(c["0"], y0, cpi_year)

    pen_year = max(pens["PN"]["mean"])
    pen_mean = pens["PN"]["mean"][pen_year]
    pen_median = pens["PN"]["median"].get(pen_year)
    lc_year = max(lc["A00"]["adeqCouple"])
    adeq_c = lc["A00"]["adeqCouple"][lc_year]
    adeq_s = lc["A00"]["adeqSingle"][lc_year]
    min_s = lc["A00"]["minSingle"][lc_year]
    spend65 = hh["G7"][hh_year]["F"]

    # 생활비 기준은 조사 연도 가격 → 최신 CPI로 환산
    def to_now(v, y):
        return v * c["0"][cpi_year] / c["0"][y] if c["0"].get(y) else v

    adeq_s_now, adeq_c_now, min_s_now = to_now(adeq_s, lc_year), to_now(adeq_c, lc_year), to_now(min_s, lc_year)

    need = {}
    for sex in ("male", "female"):
        idx = {a: table[sex][a - 40] for a in range(40, 101)}
        need[sex] = {}
        for ra in (55, 60, 63, 65, 70):
            e = idx[ra]
            need[sex][ra] = {
                "lifeExp": e,
                "needAdequate": round(adeq_s_now * 12 * e),
                "needMinimum": round(min_s_now * 12 * e),
                "gapAdequate": round(max(adeq_s_now - pen_mean, 0) * 12 * e),
                "gapMedianPension": round(max(adeq_s_now - (pen_median or pen_mean), 0) * 12 * e),
            }
    # 자금 소진 나이 시나리오 (65세 은퇴, 개인 적정생활비, 평균 연금)
    grid = []
    for asset in (100_000_000, 200_000_000, 300_000_000, 500_000_000):
        for rr in (0.0, 0.01, 0.02, 0.03):
            grid.append({"asset": asset, "realReturn": rr,
                         "depleteAge": depletion_age(65, asset, adeq_s_now, pen_mean, rr)})

    hh_out = {}
    for g, nm in HH_GROUPS.items():
        if g not in hh:
            continue
        hh_out[g] = {"name": nm, "spend": {y: round(v["F"]) for y, v in sorted(hh[g].items()) if v.get("F")},
                     "size": {y: v.get("2") for y, v in sorted(hh[g].items())},
                     "latest": {k: round(v) for k, v in hh[g][hh_year].items() if v is not None and k != "2"}}

    headline = {
        "lifeYear": ly,
        "lifeExp65Male": table["male"][25], "lifeExp65Female": table["female"][25],
        "pensionYear": pen_year, "pensionMean": round(pen_mean), "pensionMedian": pen_median and round(pen_median),
        "pensionRate": pens["PN"]["rate"][pen_year], "npRate": pens["NP"]["rate"][pen_year], "npMean": round(pens["NP"]["mean"][pen_year]),
        "livingCostYear": lc_year, "adequateSingle": round(adeq_s_now), "adequateCouple": round(adeq_c_now), "minimumSingle": round(min_s_now),
        "adequateSingleNominal": round(adeq_s), "adequateCoupleNominal": round(adeq_c),
        "spend65": round(spend65), "spend65HhSize": hh["G7"][hh_year].get("2"), "hhYear": hh_year,
        "pensionCoverage": round(pen_mean / adeq_s_now, 3),
        "elderlyCpi10": round(elderly_cpi * 100, 2), "generalCpi10": round(general_cpi * 100, 2), "cpiYear": cpi_year,
        "needAdequate65Male": need["male"][65]["needAdequate"], "needAdequate65Female": need["female"][65]["needAdequate"],
        "gap65Male": need["male"][65]["gapAdequate"], "gap65Female": need["female"][65]["gapAdequate"],
    }
    if dep:
        headline.update({
            "workPerOld2025": dep["mid"][2025]["ratio"], "workPerOld2035": dep["mid"][2035]["ratio"], "workPerOld2050": dep["mid"][2050]["ratio"],
            "old2025": dep["mid"][2025]["old"], "old2050": dep["mid"][2050]["old"],
            "pensioners2035": round(dep["mid"][2035]["old"] * pens["PN"]["rate"][pen_year] / 100),
        })

    return {
        "meta": {
            "lifeYear": ly, "pensionYear": pen_year, "hhYear": hh_year, "cpiYear": cpi_year, "livingCostYear": lc_year,
            "sources": [
                "통계청 완전생명표 1세별 기대여명 (KOSIS DT_1B42)",
                "통계청 장래인구추계 2022년 기준 장래 생명표 (KOSIS DT_1BPA202)",
                "통계청 연금통계 연금종류별 연금수급자 (KOSIS DT_1PEN_006)",
                "통계청 가계동향조사 가구주 연령별 월평균 가계수지, 전국 1인 이상 (KOSIS DT_1L9U108)",
                "통계청 소비자물가지수 지출목적별 (KOSIS DT_1J22001)",
                "국민연금연구원 국민노후보장패널 필요 최소·적정 노후생활비 (KOSIS DT_322001_D003)",
                "행정안전부 주민등록인구 기반 자체 추계 (pop.py)",
            ],
        },
        "headline": headline,
        "lifeTable": {"year": ly, "ageFrom": 40, "male": table["male"], "female": table["female"], "all": table["all"]},
        "lifeHistory": le_hist,
        "lifeFuture": le_future,
        "pensions": pens,
        "pensionsByAge": pens_age,
        "household": hh_out,
        "cpi": {"total": {y: v for y, v in sorted(c["0"].items())}, "categories": cats, "base": y0},
        "livingCost": lc,
        "need": need,
        "depletionGrid": grid,
        "dependency": dep,
        "calculator": {
            "defaults": {"retireAge": 65, "sex": "male", "asset": 200_000_000, "monthlyNeed": round(adeq_s_now),
                         "monthlyPension": round(pen_mean), "nominalReturn": 0.035, "inflation": round(elderly_cpi, 4), "lifeEnd": 100},
            "inflationScenarios": {"low": 0.015, "mid": round(elderly_cpi, 4), "high": 0.035},
        },
    }


if __name__ == "__main__":
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB)")
    print(json.dumps(d["headline"], ensure_ascii=False, indent=1))
    print(d["cpi"]["categories"])
    print(d["depletionGrid"])
