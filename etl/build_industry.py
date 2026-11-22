"""「대한민국 산업의 미래」 데이터 생성.

결합 데이터
  - 지역별고용조사 산업/연령별 취업자 (KOSIS DT_1ES3B27J, KSIC 11차, 반기)
  - 경제활동인구조사 연령계층별 고용률 (DT_1DA7002S)
  - 한국은행 경제활동별 실질 GDP(부가가치) (DT_200Y106)
  - 기업특성별 무역통계 산업별 수출액 (DT_1TEC_P320, KSIC 11차)
  - 주민등록 기반 인구추계 (pop.py, 통계청 출산율 시나리오)

새 지표
  1) 산업별 취업자·실질부가가치·수출 10년 연평균 증가율(2015→2025)과 3축 성장 점수
  2) 은퇴 대체 수요: 10년 안에 65세에 도달하는 취업자(60세 이상 + 50대의 절반) 수와 비중
  3) 노동공급 갭: 연령별 고용률을 고정하고 인구추계를 적용한 산업별 노동공급 vs 수요 시나리오
  4) 1인당 실질부가가치(노동생산성) 증가율
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import kosis

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "industry.json"

Y0, Y1 = 2015, 2025          # 추세 비교 구간(10년)
BASE = 2025                  # 노동공급 추계 기준연도
PROJ_YEARS = list(range(2025, 2046))
SUPPLY_SCEN = ("base", "older")
# 인구 연동 수요: 산업별 수요를 견인하는 인구 (연령 범위). 그 외 산업은 총인구
DEMO_DRIVER = {"P": range(6, 22), "Q": range(65, 101)}
DAMP = 0.9                   # 추세 연장 시나리오: 연간 증가율이 해마다 10%씩 줄어듦
SIGNAL_GAP = 0.01            # 3축 점수: 경제 전체 대비 ±1%p 이상이면 신호

GDP_P = "13102136275ACC_ITEM."
GDP_ITM = "13103136275999"

# 산업 정의: id, 이름, 고용(KSIC 11차 코드 목록), GDP 코드 목록, 수출(TEC M 코드 목록), 그룹
INDUSTRIES = [
    ("A", "농림어업", ["A"], ["1101"], [], "1차"),
    ("B", "광업", ["B"], ["1102"], ["101"], "1차"),
    ("C1", "식료품·음료·담배", ["10", "11", "12"], ["110301"], ["1021"], "제조"),
    ("C2", "섬유·의복·가죽", ["13", "14", "15"], ["110302"], ["1022"], "제조"),
    ("C3", "목재·종이·인쇄", ["16", "17", "18"], ["110303"], ["1023"], "제조"),
    ("C4", "석유·화학·의약·플라스틱", ["19", "20", "21", "22"], ["110304", "110305"], ["1024"], "제조"),
    ("C5", "비금속·1차금속·금속가공", ["23", "24", "25"], ["110306", "110307", "110308"], ["1025"], "제조"),
    ("C6", "전자·전기·기계·정밀", ["26", "27", "28", "29"], ["110309", "110310", "110311"], ["1026"], "제조"),
    ("C7", "자동차·조선·기타제조", ["30", "31", "32", "33", "34"], ["110312", "110313"], ["1027"], "제조"),
    ("D", "전기·가스", ["D"], ["110401", "110402"], [], "인프라"),
    ("E", "수도·하수·폐기물", ["E"], ["110403"], [], "인프라"),
    ("F", "건설", ["F"], ["1105"], [], "인프라"),
    ("G", "도매·소매", ["G"], ["110601"], ["20"], "서비스"),
    ("H", "운수·창고", ["H"], ["1107"], [], "서비스"),
    ("I", "숙박·음식점", ["I"], ["110602"], [], "서비스"),
    ("J", "정보통신", ["J"], ["1114"], [], "서비스"),
    ("K", "금융·보험", ["K"], ["1108"], [], "서비스"),
    ("L", "부동산", ["L"], ["1109"], [], "서비스"),
    ("M", "전문·과학·기술", ["M"], ["11501"], [], "서비스"),
    ("N", "사업시설관리·지원", ["N"], ["11502"], [], "서비스"),
    ("O", "공공행정", ["O"], ["1110"], [], "공공·사회"),
    ("P", "교육", ["P"], ["1111"], [], "공공·사회"),
    ("Q", "보건·사회복지", ["Q"], ["1112"], [], "공공·사회"),
    ("R", "예술·스포츠·여가", ["R"], ["11131"], [], "공공·사회"),
    ("S", "협회·수리·개인서비스", ["S"], ["11132"], [], "공공·사회"),
]

AGE_ITEMS = {"15-29": "T20", "30-39": "T21", "40-49": "T22", "50-59": "T23", "60+": "T24"}
# 고용률(DT_1DA7002S) 세부 연령 → (주민등록 연령 범위, 산업 연령 버킷)
RATE_GROUPS = [
    ("10", range(15, 20), "15-29"), ("201", range(20, 25), "15-29"), ("202", range(25, 30), "15-29"),
    ("301", range(30, 35), "30-39"), ("302", range(35, 40), "30-39"),
    ("401", range(40, 45), "40-49"), ("402", range(45, 50), "40-49"),
    ("501", range(50, 55), "50-59"), ("502", range(55, 60), "50-59"),
    ("601", range(60, 65), "60+"), ("912", range(65, 70), "60+"),
    ("701", range(70, 75), "60+"), ("702", range(75, 101), "60+"),
]


def cagr(a, b, n):
    if not a or not b or a <= 0 or b <= 0:
        return None
    return (b / a) ** (1 / n) - 1


def r4(x):
    return None if x is None else round(x, 4)


# ------------------------------------------------------------------ 수집

def employment():
    """{code: {item: {year: 천명(연평균)}}} + 최신 반기."""
    codes = sorted({c for ind in INDUSTRIES for c in ind[2]} | {"0", "C"})
    items = ["T00"] + list(AGE_ITEMS.values())
    out: dict = {}
    latest = {}
    for chunk in (codes[i:i + 12] for i in range(0, len(codes), 12)):
        rows = kosis.data("101", "DT_1ES3B27J", itm="+".join(items), objs={1: "+".join(chunk)},
                          prd_se="H", start="201301", end="202602")
        for r in rows:
            if r["DT"] in ("", "-", "x", "X"):
                continue
            y, h = int(r["PRD_DE"][:4]), r["PRD_DE"][4:]
            d = out.setdefault(r["C1"], {}).setdefault(r["ITM_ID"], {}).setdefault(y, {})
            d[h] = float(r["DT"])
    annual, half = {}, {}
    for c, items_ in out.items():
        for it, ys in items_.items():
            for y, hs in ys.items():
                half.setdefault(c, {}).setdefault(it, {})
                for h, v in hs.items():
                    half[c][it][f"{y}H{int(h)}"] = v
                if len(hs) == 2:
                    annual.setdefault(c, {}).setdefault(it, {})[y] = sum(hs.values()) / 2
    lp = max(k for k in half["0"]["T00"])
    return annual, half, lp


def gdp():
    codes = sorted({g for ind in INDUSTRIES for g in ind[3]} | {"1200", "1103"})
    rows = kosis.data("301", "DT_200Y106", itm=GDP_ITM, objs={1: "+".join(GDP_P + c for c in codes)},
                      start="2010", end="2025")
    out: dict = {}
    for r in rows:
        c = r["C1"].split(".")[-1]
        out.setdefault(c, {})[int(r["PRD_DE"])] = float(r["DT"])
    return out


def exports():
    codes = sorted({m for ind in INDUSTRIES for m in ind[4]} | {"00", "102"})
    rows = kosis.data("101", "DT_1TEC_P320", itm="T20", objs={1: "01", 2: "10", 3: "+".join(codes), 4: "00"},
                      start="2015", end="2025")
    out: dict = {}
    for r in rows:
        if r["DT"] in ("", "-"):
            continue
        out.setdefault(r["C3"], {})[int(r["PRD_DE"])] = float(r["DT"]) / 1e6  # 십억달러
    return out


def employment_rates():
    rows = kosis.data("101", "DT_1DA7002S", itm="T90", objs={1: "+".join(g[0] for g in RATE_GROUPS)},
                      start=str(BASE), end=str(BASE))
    return {r["C1"]: float(r["DT"]) / 100 for r in rows}


# ------------------------------------------------------------------ 계산

def ssum(src, keys, year):
    vals = [src.get(k, {}).get(year) for k in keys]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def build():
    emp, half, latest_half = employment()
    g = gdp()
    ex = exports()
    rates = employment_rates()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_all import population  # 캐시된 인구추계 (읽기 전용)
    popr = population()
    proj, total = popr["proj"]["00"], popr["total"]

    def emp_series(codes, item="T00"):
        ys = sorted(set.intersection(*[set(emp.get(c, {}).get(item, {})) for c in codes]))
        return {y: sum(emp[c][item][y] for c in codes) for y in ys}

    tot_emp = emp_series(["0"])
    tot_gva = g["1200"]
    tot_ex = ex["00"]
    tot_emp_cagr = cagr(tot_emp[Y0], tot_emp[Y1], Y1 - Y0)
    tot_gva_cagr = cagr(tot_gva[Y0], tot_gva[Y1], Y1 - Y0)
    tot_ex_cagr = cagr(tot_ex[Y0], tot_ex[Y1], Y1 - Y0)

    # ---- 노동공급: 고용률 고정 × 인구추계 → 연령 버킷별 공급
    def pop_at(scen, year, ages):
        if year <= BASE:
            return sum(total[year]["00"][a] for a in ages)
        return sum(proj[scen][year][a] for a in ages)

    # 공급 시나리오: base=연령별 고용률 고정, older=60~69세 +7.5%p·70~74세 +5%p (2035년까지 선형, 이후 유지)
    BOOST = {"601": 0.075, "912": 0.075, "701": 0.05}
    supply_bucket = {}
    for scen in SUPPLY_SCEN:
        supply_bucket[scen] = {}
        for y in PROJ_YEARS:
            b = {k: 0.0 for k in AGE_ITEMS}
            t = min(max((y - BASE) / 10, 0), 1)
            for code, ages, bucket in RATE_GROUPS:
                rate = rates[code] + (BOOST.get(code, 0) * t if scen == "older" else 0)
                b[bucket] += rate * pop_at("mid", y, ages)
            supply_bucket[scen][y] = b
    # 기준연도 공급(주민등록 인구 × 고용률)과 실제 취업자(지역별고용조사)의 차이를 보정
    base_emp_b = {k: emp["0"][it][BASE] * 1000 for k, it in AGE_ITEMS.items()}
    calib = {k: base_emp_b[k] / supply_bucket["base"][BASE][k] for k in AGE_ITEMS}
    for scen in supply_bucket:
        for y in PROJ_YEARS:
            for k in AGE_ITEMS:
                supply_bucket[scen][y][k] *= calib[k]

    national = {
        "employment": {y: round(v) for y, v in tot_emp.items()},
        "supply": {s: {y: round(sum(b.values()) / 1000) for y, b in v.items()} for s, v in supply_bucket.items()},
        # 2015·2020은 실제 연령별 취업자(지역별고용조사), 기준연도 이후는 고용률 유지 공급 (기준연도에서 실제와 맞춰 둠)
        "supplyByAge": {
            **{y: {k: round(emp["0"][it][y]) for k, it in AGE_ITEMS.items()} for y in (2015, 2020)},
            **{y: {k: round(v / 1000) for k, v in supply_bucket["base"][y].items()} for y in (2025, 2030, 2035, 2040, 2045)},
        },
        "workingAge": {s: {y: round(pop_at(s, y, range(15, 65)) / 1000) for y in PROJ_YEARS} for s in ("low", "mid", "high")},
        "older65": {y: round(pop_at("mid", y, range(65, 101)) / 1000) for y in PROJ_YEARS},
        "workingAgeHist": {y: round(sum(total[y]["00"][15:65]) / 1000) for y in sorted(total)},
        "employmentRates": {c: rates[c] for c, _, _ in RATE_GROUPS},
        "cagr": {"employment": r4(tot_emp_cagr), "gva": r4(tot_gva_cagr), "exports": r4(tot_ex_cagr)},
        "gva": {y: round(v) for y, v in tot_gva.items()},
        "exports": {y: round(v, 1) for y, v in tot_ex.items()},
        "latestHalf": latest_half,
        "latestEmployment": half["0"]["T00"][latest_half],
    }

    inds = []
    for iid, name, ecodes, gcodes, xcodes, group in INDUSTRIES:
        es = emp_series(ecodes)
        ages = {k: emp_series(ecodes, it).get(BASE) for k, it in AGE_ITEMS.items()}
        e_base = es[BASE]
        gv = {y: ssum(g, gcodes, y) for y in range(2010, 2026)}
        gv = {y: v for y, v in gv.items() if v is not None}
        xs = {y: ssum(ex, xcodes, y) for y in range(2015, 2026)} if xcodes else {}
        xs = {y: v for y, v in xs.items() if v is not None}

        e_c = cagr(es.get(Y0), es.get(Y1), Y1 - Y0)
        g_c = cagr(gv.get(Y0), gv.get(Y1), Y1 - Y0)
        x_c = cagr(xs.get(Y0), xs.get(Y1), Y1 - Y0) if xs else None
        prod = {y: gv[y] / es[y] for y in gv if y in es and es[y]}  # 십억원/천명 = 백만원/명
        p_c = cagr(prod.get(Y0), prod.get(Y1), Y1 - Y0)

        def sig(v, ref):
            if v is None:
                return None
            return 1 if v - ref >= SIGNAL_GAP else (-1 if v - ref <= -SIGNAL_GAP else 0)

        sigs = {"employment": sig(e_c, tot_emp_cagr), "gva": sig(g_c, tot_gva_cagr), "exports": sig(x_c, tot_ex_cagr)}
        vals = [v for v in sigs.values() if v is not None]
        score = sum(vals) / len(vals)
        if score >= 0.5 and (e_c or 0) > 0 and (g_c or 0) > 0:
            cls = "성장"
        elif score <= -0.5 and ((e_c or 0) < 0 or (g_c or 0) < 0):
            cls = "쇠퇴"
        else:
            cls = "정체"
        flags = []
        if sigs["gva"] == 1 and (e_c is not None and e_c <= 0):
            flags.append("고용 없는 성장")
        if sigs["employment"] == 1 and sigs["gva"] == -1:
            flags.append("저생산성 고용 확대")

        # 은퇴 대체 수요: 60세 이상 전원 + 50대의 절반(55~59세 근사)
        retire = (ages["60+"] or 0) + 0.5 * (ages["50-59"] or 0)
        older_share = (ages["60+"] or 0) / e_base
        young_share = (ages["15-29"] or 0) / e_base

        # 노동공급: 기준연도 연령버킷별 산업 점유율 고정
        share_b = {k: (ages[k] or 0) * 1000 / base_emp_b[k] for k in AGE_ITEMS}
        supply = {s: {y: sum(share_b[k] * supply_bucket[s][y][k] for k in AGE_ITEMS) / 1000 for y in PROJ_YEARS}
                  for s in supply_bucket}
        g_e = e_c or 0.0
        demand_trend, lvl, rate = {}, e_base, g_e
        for y in PROJ_YEARS:
            if y > BASE:
                lvl *= 1 + rate
                rate *= DAMP
            demand_trend[y] = lvl
        drv = DEMO_DRIVER.get(iid, range(0, 101))
        demand_demo = {y: e_base * pop_at("mid", y, drv) / pop_at("mid", BASE, drv) for y in PROJ_YEARS}
        demands = {"hold": {y: e_base for y in PROJ_YEARS}, "trend": demand_trend, "demo": demand_demo}
        gap = {d: {s: {y: round(supply[s][y] - dem[y], 1) for y in (2030, 2035, 2040, 2045)} for s in supply}
               for d, dem in demands.items()}

        inds.append({
            "id": iid, "name": name, "group": group,
            "employment": {y: round(v, 1) for y, v in es.items()},
            "employmentLatest": round(sum(half[c]["T00"][latest_half] for c in ecodes), 1),
            "ages": {k: round(v, 1) if v is not None else None for k, v in ages.items()},
            "gva": {y: round(v, 1) for y, v in gv.items()},
            "exports": {y: round(v, 2) for y, v in xs.items()} or None,
            "productivity": {y: round(v, 1) for y, v in prod.items()},
            "cagr": {"employment": r4(e_c), "gva": r4(g_c), "exports": r4(x_c), "productivity": r4(p_c)},
            "signals": sigs, "score": round(score, 2), "class": cls, "flags": flags,
            "olderShare": r4(older_share), "youngShare": r4(young_share),
            "retire10y": round(retire, 1), "retire10yShare": r4(retire / e_base),
            "supply": {s: {y: round(v, 1) for y, v in supply[s].items() if y % 5 == 0} for s in supply},
            "demand": {d: {y: round(v, 1) for y, v in dem.items() if y % 5 == 0} for d, dem in demands.items()},
            "gap": gap,
            "supplyChange2035": r4(supply["base"][2035] / e_base - 1),
            "supplyChange2045": r4(supply["base"][2045] / e_base - 1),
        })

    # 경제 전체 은퇴 대체 수요 / 노동공급 갭 요약
    tot_ret = sum(i["retire10y"] for i in inds)
    summary = {
        "retire10y": round(tot_ret),
        "retire10yShare": r4(tot_ret / tot_emp[BASE]),
        "supplyChange2035": {s: r4(national["supply"][s][2035] / national["supply"][s][BASE] - 1) for s in supply_bucket},
        "supplyChange2045": {s: r4(national["supply"][s][2045] / national["supply"][s][BASE] - 1) for s in supply_bucket},
        "gap": {d: {s: {y: round(sum(i["gap"][d][s][y] for i in inds)) for y in (2030, 2035, 2040, 2045)}
                    for s in supply_bucket} for d in ("hold", "trend", "demo")},
        "largestShortage2035": sorted(({"id": i["id"], "name": i["name"], "gap": i["gap"]["demo"]["base"][2035]} for i in inds),
                                      key=lambda x: x["gap"])[:5],
        "workingAgeChange2045": r4(national["workingAge"]["mid"][2045] / national["workingAge"]["mid"][BASE] - 1),
        "classes": {c: [i["id"] for i in inds if i["class"] == c] for c in ("성장", "정체", "쇠퇴")},
    }

    return {
        "meta": {
            "baseYear": BASE, "trendFrom": Y0, "trendTo": Y1, "projEnd": PROJ_YEARS[-1],
            "units": {"employment": "천명", "gva": "십억원(2020년 연쇄가격)", "exports": "십억달러",
                      "productivity": "백만원/명", "supply": "천명", "gap": "천명 (공급-수요, 음수=부족)"},
            "scenarios": {"supply": {"base": "연령별 고용률 2025년 수준 고정", "older": "60~69세 고용률 +7.5%p, 70~74세 +5%p (2035년까지)"},
                          "demand": {"hold": "2025년 취업자 수 유지", "trend": "최근 10년 증가율을 연 10%씩 감쇠하며 연장", "demo": "수요 견인 인구에 비례 (교육=6~21세, 보건복지=65세 이상, 그 외=총인구)"}},
            "sources": [
                "통계청 지역별고용조사 산업/연령별 취업자 (KOSIS DT_1ES3B27J, KSIC 11차)",
                "통계청 경제활동인구조사 연령계층별 고용률 (KOSIS DT_1DA7002S)",
                "한국은행 국민계정 경제활동별 실질 GDP (KOSIS DT_200Y106)",
                "통계청·관세청 기업특성별 무역통계 산업별 수출 (KOSIS DT_1TEC_P320)",
                "행정안전부 주민등록인구 + 통계청 장래인구추계 2022년 기준 (pop.py 추계)",
            ],
        },
        "national": national,
        "summary": summary,
        "industries": inds,
    }


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
