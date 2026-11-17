"""「대한민국의 미래」 데이터.

결합
  - 주민등록 1세별 인구(2015~2025) + 자체 코호트 추계(pop.py) → 2050년 내국인 인구·연령구조
  - 인구동향 출생아·합계출산율(실측) vs 장래인구추계 시나리오 출생아 → "현실은 어느 시나리오를 따라가나"
  - 장래인구추계(2022년 기준) 공식 지표와 비교
"""
from __future__ import annotations

from collections import defaultdict

import kosis
import pop as P
from regions import SIDO

YEARS = list(range(2015, P.END_YEAR + 1))
GROUPS5 = [(a, a + 4) for a in range(0, 100, 5)] + [(100, 100)]


def agg(ages, lo, hi):
    return sum(ages[lo:hi + 1])


def median_age(ages):
    tot = sum(ages)
    acc = 0.0
    for a, v in enumerate(ages):
        if acc + v >= tot / 2:
            return round(a + (tot / 2 - acc) / v, 1) if v else a
        acc += v
    return 100


def indicators(ages):
    tot = sum(ages)
    kid, work, old = agg(ages, 0, 14), agg(ages, 15, 64), agg(ages, 65, 100)
    return {
        "total": round(tot),
        "kids": round(kid),
        "work": round(work),
        "old": round(old),
        "old75": round(agg(ages, 75, 100)),
        "old85": round(agg(ages, 85, 100)),
        "young": round(agg(ages, 20, 39)),
        "oldShare": round(old / tot, 4),
        "kidShare": round(kid / tot, 4),
        "workShare": round(work / tot, 4),
        "oldDep": round(old / work * 100, 1),
        "totalDep": round((kid + old) / work * 100, 1),
        "agingIndex": round(old / kid * 100, 1) if kid else None,
        "medianAge": median_age(ages),
        "workPerOld": round(agg(ages, 20, 64) / old, 2) if old else None,
    }


def series_for(popr, k):
    total, proj = popr["total"], popr["proj"]
    out = {}
    for s in ("low", "mid", "high"):
        row = {}
        for y in YEARS:
            ages = total[y][k] if y <= P.BASE_YEAR else proj[k][s][y]
            row[y] = indicators(ages)
        out[s] = row
    return out


def first_year(row: dict, field: str, thr: float, above=True):
    for y in sorted(row):
        v = row[y][field]
        if v is not None and ((v >= thr) if above else (v <= thr)):
            return y
    return None


def official():
    """공식 장래인구추계 주요 지표 (중위/고위/저위)."""
    codes = {"10": "total", "33": "oldShare", "42": "oldDep", "60": "medianAge", "22": "work", "23": "old"}
    rows = kosis.data("101", "DT_1BPA002", objs={1: "1+2+3", 2: "+".join(codes)}, start="2022", end="2072")
    names = {"1": "mid", "2": "high", "3": "low"}
    out = {v: defaultdict(dict) for v in names.values()}
    for r in rows:
        v = float(r["DT"])
        f = codes[r["C2"]]
        if f == "oldShare":
            v /= 100
        out[names[r["C1"]]][int(r["PRD_DE"])][f] = v
    return {s: dict(d) for s, d in out.items()}


def official_pyramid(year):
    rows = kosis.data("101", "DT_1BPA001", objs={1: "1", 2: "1+2", 3: "ALL"}, start=str(year), end=str(year))
    m = {}
    for r in rows:
        c = r["C3"]
        if len(c) == 3 and c != "000":
            m.setdefault(r["C3_NM"], {})[r["C2"]] = float(r["DT"])
    return m


def births_actual():
    rows = kosis.data("101", "DT_1B81A23", objs={1: "00"}, start="2000", end="2025")
    b, tfr = {}, {}
    for r in rows:
        y = int(r["PRD_DE"])
        if r["ITM_ID"] == "T1":
            b[y] = float(r["DT"])
        else:
            tfr[y] = float(r["DT"])
    return b, tfr


def build(popr):
    total, female = popr["total"], popr["female"]
    nat = series_for(popr, "00")
    mid = nat["mid"]
    base = mid[P.BASE_YEAR]

    # 피라미드: 2025 실측(주민등록, 남/여) vs 2050 자체추계(중위, 성비는 2025년 동일 연령 코호트 비율 이용)
    t25, f25 = total[P.BASE_YEAR]["00"], female[P.BASE_YEAR]["00"]
    p50 = popr["proj"]["00"]["mid"][2050]
    fshare = [(f25[a] / t25[a]) if t25[a] else 0.5 for a in range(P.NAGE)]
    # 2050년 a세는 2025년 a-25세 코호트 → 그 코호트의 여성 비율 사용(고령층은 2025년 최고령 비율)
    f50 = [p50[a] * (fshare[a - 25] if a >= 25 else fshare[a]) for a in range(P.NAGE)]
    labels, m25, w25, m50, w50 = [], [], [], [], []
    for lo, hi in GROUPS5:
        labels.append(f"{lo}세 이상" if lo == 100 else f"{lo}~{hi}세")
        w = agg(f25, lo, hi)
        m25.append(round(agg(t25, lo, hi) - w))
        w25.append(round(w))
        w2 = sum(f50[lo:hi + 1])
        m50.append(round(sum(p50[lo:hi + 1]) - w2))
        w50.append(round(w2))

    # 출생: 실측 vs 공식 시나리오
    b_act, tfr = births_actual()
    fert_births = popr["fert"]["births"]
    births = {
        "actual": {y: round(v) for y, v in sorted(b_act.items())},
        "tfr": tfr,
        "official": {s: {y: round(v) for y, v in sorted(fert_births[s].items()) if y <= 2050} for s in fert_births},
        "projected": {s: {y: round(popr["proj"]["00"][s][y][0]) for y in range(P.BASE_YEAR + 1, 2051)} for s in ("low", "mid", "high")},
    }
    # 실제 출생이 어느 시나리오에 가까운가 (최근 연도)
    ly = max(b_act)
    gaps = {s: b_act[ly] / fert_births[s][ly] - 1 for s in fert_births if ly in fert_births[s]}

    # 시도
    sidos = []
    for sd, (short, full) in SIDO.items():
        if sd not in popr["proj"]:
            continue
        ss = series_for(popr, sd)["mid"]
        sidos.append({
            "id": sd, "name": short, "full": full,
            "pop2025": ss[2025]["total"], "pop2050": ss[2050]["total"],
            "change2050": round(ss[2050]["total"] / ss[2025]["total"] - 1, 4),
            "oldShare2025": ss[2025]["oldShare"], "oldShare2050": ss[2050]["oldShare"],
            "medianAge2050": ss[2050]["medianAge"],
            "workPerOld2050": ss[2050]["workPerOld"],
            "series": {y: {k: ss[y][k] for k in ("total", "oldShare", "medianAge")} for y in ss},
        })

    off = official()
    return {
        "meta": {
            "baseYear": P.BASE_YEAR,
            "endYear": P.END_YEAR,
            "sources": [
                "행정안전부 주민등록인구 1세별 (KOSIS DT_1B04006) — 내국인 기준",
                "통계청 인구동향조사 출생아 수·합계출산율 (KOSIS DT_1B81A23)",
                "통계청 장래인구추계 2022년 기준 (KOSIS DT_1BPA001, DT_1BPA002, DT_1BPA004, DT_1BPA402, DT_1BPA403)",
            ],
        },
        "national": nat,
        "milestones": {
            "old20": first_year(mid, "oldShare", 0.20),
            "old30": first_year(mid, "oldShare", 0.30),
            "old40": first_year(mid, "oldShare", 0.40),
            "under50m": first_year(mid, "total", 50_000_000, above=False),
            "under45m": first_year(mid, "total", 45_000_000, above=False),
            "workPerOld2": first_year(mid, "workPerOld", 2.0, above=False),
            "medianAge60": first_year(mid, "medianAge", 60),
        },
        "headline": {
            "pop2025": base["total"],
            "pop2050": {s: nat[s][2050]["total"] for s in nat},
            "oldShare2025": base["oldShare"],
            "oldShare2050": mid[2050]["oldShare"],
            "workPerOld2025": base["workPerOld"],
            "workPerOld2050": mid[2050]["workPerOld"],
            "medianAge2025": base["medianAge"],
            "medianAge2050": mid[2050]["medianAge"],
            "old85_2025": base["old85"],
            "old85_2050": mid[2050]["old85"],
            "kids2025": base["kids"],
            "kids2050": mid[2050]["kids"],
            "young2025": base["young"],
            "young2050": mid[2050]["young"],
            "birthsLatestYear": ly,
            "birthsLatest": round(b_act[ly]),
            "tfrLatest": tfr.get(ly),
            "birthsVsScenario": {s: round(v, 4) for s, v in gaps.items()},
        },
        "village": {  # 100명 마을
            str(y): {
                "kids": round(mid[y]["kidShare"] * 100),
                "work": round(mid[y]["workShare"] * 100),
                "old": round(mid[y]["oldShare"] * 100),
                "old85": round(mid[y]["old85"] / mid[y]["total"] * 100, 1),
            } for y in (2015, 2025, 2035, 2050)
        },
        "pyramid": {"labels": labels, "male2025": m25, "female2025": w25, "male2050": m50, "female2050": w50},
        "births": births,
        "official": off,
        "sidos": sorted(sidos, key=lambda r: r["change2050"]),
    }


if __name__ == "__main__":
    import run_all
    run_all.write("korea", build(run_all.population()))
