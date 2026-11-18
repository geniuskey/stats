"""「대학은 얼마나 남을까?」 데이터 생성.

결합 데이터
  - 대학·교육대학·산업대학·전문대학 입학자 수 (교육기본통계, 시도·1999~)
  - 고등학교 졸업자 수 (교육기본통계)
  - 18세 인구: 주민등록 1세별 인구 + pop.py 추계 (2043년 입학생까지는 이미 태어난 아이들)

핵심 식
  입학 수요(Y)   = r × 18세 인구(Y−1년 말),  r = 최근 3년 입학자 ÷ 18세 인구 평균 (재수·만학도·외국인 포함 보정)
  입학 규모(C)   = 최근 입학자 수 (KOSIS에 입학정원 표가 없어 실제 입학자를 정원 대용으로 씀)
  지역·학교급 배분: 칸(시도 × 4년제/전문대)마다 탄력성 β를 과거 자료로 추정
      Δlog 입학자(칸, Y) = β × Δlog 전국 입학자(Y)        (2005~ 최근, 원점 회귀)
      입학자(칸, Y) = C(칸) × (수요/C)^β  → 전국 합이 수요가 되도록 비례 조정
  수요가 줄 때 수도권 β는 작고 지방·전문대 β는 크다 = 줄어드는 학생이 어디서 먼저 빠지는지.
"""
from __future__ import annotations

import math
from collections import defaultdict

import kosis
import pop as P
from regions import EDU_SIDO, SIDO

LAST = 2026
FIT_FROM = 2005
PROJ_END = P.END_YEAR + 1        # 18세(Y−1) 추계가 있는 마지막 입학 연도
RATIO_YEARS = [LAST - 2, LAST - 1, LAST]
R_LOW, R_HIGH = 1.0, 1.3
CAPITAL = {"11", "28", "41"}
TYPES = {
    "u": ("4년제", [("DT_1963003_013", {2: "A001", 3: "F_1"}), ("DT_1963003_012", {2: "F_1"}), ("DT_1963003_016", {2: "A001", 3: "F_1"})]),
    "c": ("전문대", [("DT_1963003_011", {2: "A001", 3: "F_1"})]),
}


def edu_rows(tbl, objs, start="1999"):
    rows = kosis.data("334", tbl, objs={1: "ALL", **objs}, start=start, end=str(LAST))
    out = defaultdict(dict)
    for r in rows:
        k = "00" if r["C1"] == "00" else EDU_SIDO.get(r["C1"])
        if k and r["DT"] not in ("", "-"):
            out[k][int(r["PRD_DE"])] = float(r["DT"])
    return out


def entrants():
    """{(region, type): {year: n}}"""
    E = defaultdict(lambda: defaultdict(float))
    for t, (_, tbls) in TYPES.items():
        for tbl, objs in tbls:
            for k, ser in edu_rows(tbl, objs).items():
                for y, v in ser.items():
                    E[(k, t)][y] += v
    return E


def beta(cell: dict, nat: dict, years) -> float:
    xs, ys = [], []
    for y in years:
        if all(t in cell and cell[t] > 0 for t in (y, y - 1)) and all(t in nat for t in (y, y - 1)):
            xs.append(math.log(nat[y] / nat[y - 1]))
            ys.append(math.log(cell[y] / cell[y - 1]))
    sxx = sum(x * x for x in xs)
    if sxx == 0:
        return 1.0
    b = sum(x * y for x, y in zip(xs, ys)) / sxx
    return max(0.2, min(3.0, b))


def allocate(caps: dict, betas: dict, demand: float) -> dict:
    C = sum(caps.values())
    if demand >= C:
        return dict(caps)
    f = demand / C
    raw = {k: caps[k] * f ** betas[k] for k in caps}
    s = sum(raw.values())
    return {k: v * demand / s for k, v in raw.items()}


def rnd(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def build(popr):
    total, proj = popr["total"], popr["proj"]
    E = entrants()
    grads = edu_rows("DT_1963003_004", {2: "A001", 3: "E_1"})

    def p18(k, y_end, scen="mid"):
        if y_end <= P.BASE_YEAR:
            d = total.get(y_end, {}).get(k)
            return d[18] if d else None
        return proj[k][scen][y_end][18] if k in proj else None

    nat_tot = {y: E[("00", "u")].get(y, 0) + E[("00", "c")].get(y, 0) for y in range(1999, LAST + 1)}
    ratio = sum(nat_tot[y] / p18("00", y - 1) for y in RATIO_YEARS) / len(RATIO_YEARS)
    cells = [(k, t) for k in SIDO for t in TYPES if E[(k, t)].get(LAST)]
    caps = {c: E[c][LAST] for c in cells}
    C = sum(caps.values())
    betas = {c: beta(E[c], nat_tot, range(FIT_FROM + 1, LAST + 1)) for c in cells}

    years = list(range(LAST + 1, PROJ_END + 1))
    # 18세 1명당 입학자 r: 18세가 줄수록 재수생·만학도·외국인 유학생으로 메워 r이 올라갔다(2019 0.86 → 2025 1.17).
    # 하나로 못 박지 않고 범위로 둔다: 낮음 1.0(2021~23 수준), 기준 최근 3년 평균, 높음 1.3(최대치를 넘어 계속 확대)
    ratios = {"low": R_LOW, "mid": ratio, "high": R_HIGH}
    demand = {s: {y: ratios[s] * p18("00", y - 1) for y in years} for s in ("low", "mid", "high")}
    alloc = {y: allocate(caps, betas, demand["mid"][y]) for y in years}

    # 전국
    def first_year(cond):
        return next((y for y in years if cond(y)), None)

    fill = {y: min(1.0, demand["mid"][y] / C) for y in years}
    nat = {
        "entrants": {t: {y: rnd(E[("00", t)].get(y)) for y in range(1999, LAST + 1) if E[("00", t)].get(y)} for t in TYPES},
        "entrantsTotal": {y: rnd(v) for y, v in nat_tot.items()},
        "grads": {y: rnd(v) for y, v in sorted(grads["00"].items())},
        "age18": {y: rnd(p18("00", y - 1)) for y in range(2016, LAST + 1)},
        "ratioHist": {y: round(nat_tot[y] / p18("00", y - 1), 3) for y in range(2016, LAST + 1)},
        "gradRatioHist": {y: round(nat_tot[y] / grads["00"][y], 3) for y in range(2005, LAST + 1) if grads["00"].get(y)},
        "seatsPer18": {y: round(C / p18("00", y - 1), 3) for y in range(LAST, PROJ_END + 1)},
        "age18Proj": {s: {y: rnd(p18("00", y - 1, s)) for y in years} for s in ("low", "mid", "high")},
        "demand": {s: {y: rnd(v) for y, v in d.items()} for s, d in demand.items()},
        "fill": {y: round(v, 4) for y, v in fill.items()},
        "byType": {t: {y: rnd(sum(v for (k, tt), v in alloc[y].items() if tt == t)) for y in years} for t in TYPES},
        "capByType": {t: rnd(sum(v for (k, tt), v in caps.items() if tt == t)) for t in TYPES},
    }

    # 시도
    sidos = []
    for k in SIDO:
        ks = [c for c in cells if c[0] == k]
        if not ks:
            continue
        cap = sum(caps[c] for c in ks)
        proj_k = {y: sum(alloc[y][c] for c in ks) for y in years}
        a18 = p18(k, LAST - 1)
        a18_40 = p18(k, 2039)
        hist = {y: rnd(sum(E[c].get(y, 0) for c in ks)) for y in range(2005, LAST + 1)}
        cap_c = sum(caps[c] for c in ks if c[1] == "c")
        sidos.append({
            "id": k, "name": SIDO[k][0], "capital": k in CAPITAL,
            "cap": rnd(cap), "capU": rnd(cap - cap_c), "capC": rnd(cap_c),
            "betaU": round(betas.get((k, "u"), 0), 3) if (k, "u") in betas else None,
            "betaC": round(betas.get((k, "c"), 0), 3) if (k, "c") in betas else None,
            "hist": hist,
            "proj": {y: rnd(v) for y, v in proj_k.items()},
            "fill": {y: round(v / cap, 4) for y, v in proj_k.items()},
            "empty2035": rnd(cap - proj_k[2035]), "empty2040": rnd(cap - proj_k[2040]),
            "fill2030": round(proj_k[2030] / cap, 4), "fill2035": round(proj_k[2035] / cap, 4), "fill2040": round(proj_k[2040] / cap, 4),
            "age18": rnd(a18), "age18_2040": rnd(a18_40),
            "localRatio": round(cap / a18, 3) if a18 else None,     # 지역 입학 규모 ÷ 지역 18세
            "localRatio2040": round(cap / a18_40, 3) if a18_40 else None,
            "change2016": round(hist[LAST] / hist[2016] - 1, 4) if hist.get(2016) else None,
        })

    # 백테스트: 지역 배분 모형이 '전국 입학자가 줄 때 어디서 줄어드는지'를 맞히는가
    #   fit_end년까지 자료로 β를 추정 → target년 전국 입학자(실제)를 주고 시도별로 배분 → 실제와 비교
    #   비교 기준(naive): 모든 시도가 같은 비율로 줄어든다고 볼 때
    bt_reg = []
    for fit_end, target in ((2015, 2021), (2015, 2024), (2018, 2023)):
        caps0 = {c: E[c][fit_end] for c in cells if E[c].get(fit_end)}
        b0 = {c: beta(E[c], nat_tot, range(FIT_FROM + 1, fit_end + 1)) for c in caps0}
        pr = allocate(caps0, b0, nat_tot[target])
        s0 = sum(caps0.values())
        rows, em, en = [], [], []
        for k in SIDO:
            ks = [c for c in caps0 if c[0] == k]
            if not ks:
                continue
            act = sum(E[c].get(target, 0) for c in ks)
            pm = sum(pr[c] for c in ks)
            pn = sum(caps0[c] for c in ks) * nat_tot[target] / s0
            em.append(abs(pm / act - 1)); en.append(abs(pn / act - 1))
            rows.append({"id": k, "name": SIDO[k][0], "base": rnd(sum(caps0[c] for c in ks)), "pred": rnd(pm), "naive": rnd(pn), "actual": rnd(act)})
        bt_reg.append({"fitEnd": fit_end, "target": target, "natChange": round(nat_tot[target] / s0 - 1, 4),
                       "mae": round(sum(em) / len(em), 4), "naiveMae": round(sum(en) / len(en), 4), "rows": rows})
    # 과거 충격: 2020→2021 실제 변화 (탄력성의 근거)
    shock = []
    for k in SIDO:
        ks = [c for c in cells if c[0] == k]
        a, b = sum(E[c].get(2020, 0) for c in ks), sum(E[c].get(2021, 0) for c in ks)
        if a:
            shock.append({"id": k, "name": SIDO[k][0], "change": round(b / a - 1, 4)})

    empty = {y: rnd(max(0, C - demand["mid"][y])) for y in years}
    return {
        "meta": {
            "last": LAST, "projEnd": PROJ_END, "ratio": round(ratio, 4), "ratioYears": RATIO_YEARS,
            "ratioLow": R_LOW, "ratioHigh": R_HIGH,
            "bornCutoff": P.BASE_YEAR + 19 - 1,  # 이 해 입학생까지는 이미 태어남
            "sources": [
                "교육부·한국교육개발원 교육기본통계 대학·교육대학·산업대학·전문대학 개황 입학자수 (KOSIS DT_1963003_013, _012, _016, _011)",
                "교육기본통계 고등학교 개황 졸업자수 (KOSIS DT_1963003_004)",
                "행정안전부 주민등록인구 1세별 (KOSIS DT_1B04006) + 이 사이트 인구 추계",
            ],
        },
        "headline": {
            "cap": rnd(C), "capU": nat["capByType"]["u"], "capC": nat["capByType"]["c"],
            "fill2030": round(fill[2030], 4), "fill2035": round(fill[2035], 4), "fill2040": round(fill[2040], 4),
            "fill2040Range": [round(min(1, demand[s][2040] / C), 4) for s in ("low", "high")],
            "empty2040Range": [rnd(max(0, C - demand[s][2040])) for s in ("high", "low")],
            "empty2035": empty[2035], "empty2040": empty[2040], "empty2045": empty[2045],
            "minYear": min(years, key=lambda y: demand["mid"][y]), "minDemand": rnd(min(demand["mid"].values())),
            "first90": first_year(lambda y: fill[y] < 0.9), "first70": first_year(lambda y: fill[y] < 0.7),
            "age18Now": rnd(p18("00", LAST - 1)), "age18_2040": rnd(p18("00", 2039)),
            "fillU2040": round(nat["byType"]["u"][2040] / nat["capByType"]["u"], 4),
            "fillC2040": round(nat["byType"]["c"][2040] / nat["capByType"]["c"], 4),
        },
        "national": nat,
        "empty": empty,
        "sidos": sidos,
        "backtest": {
            "regional": bt_reg,
            "shock2021": shock,
        },
    }


if __name__ == "__main__":
    import pickle, pprint
    from pathlib import Path
    popr = pickle.loads((Path(__file__).resolve().parent.parent / "data/raw/pop.pkl").read_bytes())
    d = build(popr)
    pprint.pprint(d["headline"]); pprint.pprint(d["meta"])
    for s in d["sidos"]:
        print(s["name"], s["cap"], s["betaU"], s["betaC"], s["fill2035"], s["fill2040"], s["localRatio"], s["localRatio2040"])
    pprint.pprint([{k: v for k, v in b.items() if k != "rows"} for b in d["backtest"]["regional"]])
    print(d["national"]["demand"]["mid"])
