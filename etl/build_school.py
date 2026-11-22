"""「학교는 얼마나 남을까?」 데이터 생성.

결합 데이터
  - 주민등록 1세별 인구(행안부) → 미래 학령인구 (pop.py 추계)
  - 초등학교 학생수·학교수·학급당 학생수·교원 1인당 학생수 (e-지방지표, 시군구)
  - 초·중·고 개황 (교육기본통계, 시도)
  - 장래인구추계 출산율 시나리오 (통계청)

핵심 식
  초등학생(Y) = r × Σ_{6..11세} 주민등록인구(Y-1년 말)
  r = 최근 4년(2023~2026) 실제 학생수 / 해당 학령 주민등록인구 평균 (학구 경계 이동·대안학교·해외체류 등 보정)
"""
from __future__ import annotations

import json
from collections import defaultdict

import kosis
import pop as P
from regions import EDU_SIDO, SIDO, key, stat_is_sgg, stat_sido

LAST_ACTUAL = 2026
PROJ_END = 2045
CAL_YEARS = [2023, 2024, 2025, 2026]
LEVELS = {  # 학교급: (연령 범위, 교육통계 테이블, 학생, 학급, 학교, 교원, 입학)
    "ele": (range(6, 12), "DT_1963003_002", "C_1", "B", "A_1", "D_1", "F_1"),
    "mid": (range(12, 15), "DT_1963003_003", "H_1", "G_1", "A_1", "B_1", "D_1"),
    "high": (range(15, 18), "DT_1963003_004", "H_1", "G_1", "A_1", "B_1", "D_1"),
}


def jiji(tbl: str, itm: str = "ALL"):
    """e-지방지표 시군구 표 → {key: {year: value}}; 시도는 시도코드, 전국은 '00'."""
    rows = kosis.data("101", tbl, itm=itm, objs={1: "ALL"}, start="2011", end=str(LAST_ACTUAL))
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for r in rows:
        if r["DT"] in ("", "-", None):
            continue
        c = r["C1"]
        if c == "00":
            k = "00"
        else:
            sd = stat_sido(c)
            if sd is None:
                continue
            k = key(sd, r["C1_NM"]) if stat_is_sgg(c) else sd
        out[k][int(r["PRD_DE"])] = float(r["DT"])
    return out


def edu_sido(tbl: str, item: str):
    rows = kosis.data("334", tbl, objs={1: "ALL", 2: "A001", 3: item}, start="1999", end=str(LAST_ACTUAL))
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for r in rows:
        c = r["C1"]
        k = "00" if c == "00" else EDU_SIDO.get(c)
        if k and r["DT"] not in ("", "-"):
            out[k][int(r["PRD_DE"])] = float(r["DT"])
    return out


def school_age(series_by_year, k, ages, year_end):
    d = series_by_year.get(year_end, {})
    v = d.get(k)
    return sum(v[a] for a in ages) if v else None


def rnd(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def run_backtest(popr, stu):
    """2020년 말 인구만으로 2021~2026년 초등학생 수를 예측해 실제와 비교 (출산율 고정)."""
    total, female, units = popr["total"], popr["female"], popr["units"]
    tr = [(2017, 2018), (2018, 2019), (2019, 2020)]
    nat = P.national_ccr(total, tr)
    ages = LEVELS["ele"][0]
    by, errs = {}, defaultdict(list)
    for k in units + list(SIDO) + ["00"]:
        if k not in total[2020] or k not in stu:
            continue
        act = stu[k]
        rs = [act[y] / sum(total[y - 1][k][a] for a in ages) for y in (2018, 2019, 2020) if y in act and k in total[y - 1]]
        if not rs:
            continue
        r = sum(rs) / len(rs)
        pj = P.project(total, female, k, nat, {"c": {}}, base_year=2020, transitions=tr, end_year=2026)["c"]
        pred = {y: r * sum(pj[y - 1][a] for a in ages) for y in range(2021, 2027)}
        row = {y: {"pred": rnd(pred[y]), "actual": rnd(act.get(y))} for y in pred if act.get(y)}
        by[k] = row
        if "|" in k:
            for y, v in row.items():
                errs[y - 2020].append(v["pred"] / v["actual"] - 1)  # 부호 있는 오차
    ab = {h: [abs(x) for x in e] for h, e in errs.items()}
    mape = {h: round(sum(e) / len(e), 4) for h, e in sorted(ab.items())}
    med = {h: round(sorted(e)[len(e) // 2], 4) for h, e in sorted(ab.items())}
    within10 = {h: round(sum(1 for x in e if x <= 0.10) / len(e), 3) for h, e in sorted(ab.items())}

    def q(xs, p):  # 분위수 (선형 보간)
        s = sorted(xs)
        i = (len(s) - 1) * p
        lo = int(i)
        return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (i - lo)

    # 예측 구간용: 부호 있는 오차(예측 ÷ 실제 − 1)의 10·90% 분위수
    q10 = {h: round(q(e, 0.1), 4) for h, e in sorted(errs.items())}
    q90 = {h: round(q(e, 0.9), 4) for h, e in sorted(errs.items())}
    return {"by": by, "mape": mape, "median": med, "within10": within10, "q10": q10, "q90": q90, "n": len(errs.get(6, []))}


def build(popr):
    total, proj, units = popr["total"], popr["proj"], popr["units"]
    stu = jiji("DT_1YL21241")
    sch = jiji("DT_1YL21231")
    cls = jiji("DT_1YL15001", itm="T003")  # 학급당 학생수(초등)
    tpr = jiji("DT_1YL21171", itm="T10")

    def pop_at(k, scen, year_end, ages):
        if year_end <= P.BASE_YEAR:
            return school_age(total, k, ages, year_end)
        return sum(proj[k][scen][year_end][a] for a in ages) if k in proj else None

    def level_projection(k, ages, actual: dict[int, float]):
        rs = []
        for y in CAL_YEARS:
            a = actual.get(y)
            p = pop_at(k, "mid", y - 1, ages)
            if a and p:
                rs.append(a / p)
        if not rs:
            return None, None
        r = sum(rs) / len(rs)
        out = {}
        for s in ("low", "mid", "high"):
            out[s] = {y: rnd(r * pop_at(k, s, y - 1, ages)) for y in range(LAST_ACTUAL + 1, PROJ_END + 1)}
        return r, out

    regions = []
    ages_ele = LEVELS["ele"][0]
    for k in units + list(SIDO) + ["00"]:
        if k not in total[P.BASE_YEAR]:
            continue
        actual = stu.get(k, {})
        if not actual:
            continue
        r, pj = level_projection(k, ages_ele, actual)
        if pj is None:
            continue
        cur = actual.get(LAST_ACTUAL)
        csize = cls.get(k, {}).get(LAST_ACTUAL)
        nsch = sch.get(k, {}).get(LAST_ACTUAL)
        tratio = tpr.get(k, {}).get(LAST_ACTUAL)
        mid = pj["mid"]
        # 1학년(입학) 추계: 6세(Y-1년 말) × r
        entrants = {}
        for y in range(2016, PROJ_END + 1):
            p6 = pop_at(k, "mid", y - 1, range(6, 7))
            entrants[y] = rnd(r * p6) if p6 is not None else None
        half_year = next((y for y in sorted(mid) if cur and mid[y] <= cur * 0.5), None)
        y2035 = mid.get(2035)
        sd, _, nm = k.partition("|")
        if k == "00":
            name, sido_name, level = "전국", "", "nation"
        elif not nm:
            name, sido_name, level = SIDO[sd][1], "", "sido"
        else:
            name, sido_name, level = nm, SIDO[sd][0], "sgg"
        # 학령인구(시군구 주민) 중·고
        school_age_pop = {}
        for lv in ("mid", "high"):
            ages = LEVELS[lv][0]
            school_age_pop[lv] = {y: rnd(pop_at(k, "mid", y - 1, ages)) for y in range(2016, PROJ_END + 1)}
        regions.append({
            "id": k if level != "sgg" else popr["codes"].get(k, k),
            "key": k,
            "name": name,
            "sido": sido_name,
            "short": SIDO[sd][0] if k != "00" else "전국",
            "sidoCode": sd if k != "00" else "00",
            "level": level,
            "ratio": round(r, 4),
            "actual": {y: rnd(v) for y, v in sorted(actual.items())},
            "proj": pj,
            "entrants": entrants,
            "schoolAgePop": school_age_pop,
            "schools": nsch and rnd(nsch),
            "classSize": csize,
            "teacherRatio": tratio,
            "classSizeHist": {y: v for y, v in sorted(cls.get(k, {}).items())},
            "schoolsHist": {y: rnd(v) for y, v in sorted(sch.get(k, {}).items())},
            "summary": {
                "current": rnd(cur),
                "y2030": mid.get(2030),
                "y2035": y2035,
                "y2045": mid.get(2045),
                "change2035": round(y2035 / cur - 1, 4) if cur and y2035 is not None else None,
                "halfYear": half_year,
                "classes2026": rnd(cur / csize) if cur and csize else None,
                "classes2035": rnd(y2035 / csize) if y2035 and csize else None,
                "perSchool2026": rnd(cur / nsch) if cur and nsch else None,
                "perSchool2035": rnd(y2035 / nsch) if y2035 and nsch else None,
                "teacherRatio2035": round(tratio * y2035 / cur, 1) if tratio and cur and y2035 else None,
                "peakEntrants": max((v for v in entrants.values() if v), default=None),
                "entrants2026": entrants.get(2026),
                "entrants2032": entrants.get(2032),
            },
        })

    # 전국/시도 학교급별 (교육기본통계)
    levels = {}
    for lv, (ages, tbl, i_stu, i_cls, i_sch, i_tch, i_ent) in LEVELS.items():
        s_stu, s_cls = edu_sido(tbl, i_stu), edu_sido(tbl, i_cls)
        s_sch, s_tch = edu_sido(tbl, i_sch), edu_sido(tbl, i_tch)
        lvl = {}
        for k in ["00"] + list(SIDO):
            act = s_stu.get(k)
            if not act:
                continue
            r, pj = level_projection(k, ages, act)
            if pj is None:
                continue
            cur = act[LAST_ACTUAL]
            lvl[k] = {
                "ratio": round(r, 4),
                "actual": {y: rnd(v) for y, v in sorted(act.items())},
                "proj": pj,
                "classes": {y: rnd(v) for y, v in sorted(s_cls.get(k, {}).items())},
                "schools": {y: rnd(v) for y, v in sorted(s_sch.get(k, {}).items())},
                "teachers": {y: rnd(v) for y, v in sorted(s_tch.get(k, {}).items())},
                "change2035": round(pj["mid"][2035] / cur - 1, 4),
            }
        levels[lv] = lvl

    backtest = run_backtest(popr, stu)
    for reg in regions:
        reg["backtest"] = backtest["by"].get(reg["key"])

    return {
        "backtest": {k: v for k, v in backtest.items() if k != "by"},
        "meta": {
            "lastActual": LAST_ACTUAL,
            "baseYear": P.BASE_YEAR,
            "projEnd": PROJ_END,
            "calYears": CAL_YEARS,
            "sources": [
                "행정안전부 주민등록인구 (KOSIS DT_1B04006)",
                "e-지방지표 초등학교 학생수·학교수·학급당 학생수·교원 1인당 학생수 (KOSIS DT_1YL21241, DT_1YL21231, DT_1YL15001, DT_1YL21171)",
                "교육부·한국교육개발원 교육기본통계 초·중·고 개황 (KOSIS DT_1963003_002~004)",
                "통계청 장래인구추계 2022년 기준 (KOSIS DT_1BPA001, DT_1BPA004, DT_1BPA402, DT_1BPA403)",
            ],
        },
        "regions": regions,
        "levels": levels,
    }
