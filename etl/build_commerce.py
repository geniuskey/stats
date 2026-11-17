"""「소멸하는 상권, 성장하는 상권」 + 「우리 동네의 미래」 보조 시계열.

결합 데이터 (모두 KOSIS OpenAPI)
  - 기업생멸행정통계: 시군구×산업대분류 활동·신생·소멸 기업 수 (DT_6BD1132, 2016~)
  - 고용노동부 사업체노동실태현황: 시군구×산업 사업체수·종사자수
      (DT_118N_SAUPN75/78 2017~2023, DT_118N_SAUPM75/78 2024~)
  - 국내인구이동통계: 시군구×연령(5세) 순이동 (DT_1B26002)
  - 주민등록 세대수 (DT_1B040B3), 미거주주택(빈집) 비율 (DT_1YL202005)
  - 주민등록 1세별 인구 + 자체 소지역 인구추계 (pop.py, run_all.population())

상권 = 도매및소매업(G) + 숙박및음식점업(I).
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import kosis
import run_all
from regions import SIDO, STAT_PREFIX, adm_sido, is_unit, key, stat_is_sgg, stat_sido

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "commerce.json"

IND = ("G", "I")
BIZ_FIRST, BIZ_LAST = 2017, 2024
GROWTH_FROM = 2020  # 2019→2020 전국 수준 급감(조사 체계 변경·코로나19 추정) → 2020년부터 비교
CONSUMER_AGES = range(20, 65)
YOUNG_CODES = ("120", "130", "150", "160")  # 20~39세
YEARS_HIST = list(range(2015, 2026))

unmatched: dict[str, set[str]] = defaultdict(set)


def num(v):
    if v in (None, "", "-", "X", "x"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


class Resolver:
    """원천 표의 (시도, 이름) → 분석 단위 key."""

    def __init__(self, units):
        self.units = set(units)

    def __call__(self, sd: str | None, name: str, src: str):
        if sd is None:
            unmatched[src].add(name)
            return None
        name = "".join(name.split())  # '남  구' 같은 공백 표기 정규화
        if name in ("세종시",):
            name = "세종특별자치시"
        k = key(sd, name)
        if k in self.units:
            return k
        if sd == "28" and name == "남구":  # 2018.7 인천 남구 → 미추홀구
            return key("28", "미추홀구")
        if name == "군위군":  # 2023.7 경북 → 대구 편입
            return key("27", "군위군")
        unmatched[src].add(f"{sd}|{name}")
        return None


# ------------------------------------------------------------------ 원천 수집

def enterprise_demography(res: Resolver):
    """{key: {ind: {year: {active, birth, death}}}} (ind: '0','G','I')"""
    rows = kosis.data("101", "DT_6BD1132", itm="T01+T02+T03", objs={1: "ALL", 2: "0+G+I"}, start="2016", end="2025")
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    fld = {"T01": "active", "T02": "birth", "T03": "death"}
    for r in rows:
        c = r["C1"]
        if c == "00":
            k = "00"
        elif not stat_is_sgg(c):
            k = stat_sido(c)
        else:
            sd = stat_sido(c)
            k = res(sd, r["C1_NM"], "기업생멸")
            if k is None:
                continue
        v = num(r["DT"])
        if v is None or k is None:
            continue
        d = out[k][r["C2"]][int(r["PRD_DE"])]
        d[fld[r["ITM_ID"]]] = d.get(fld[r["ITM_ID"]], 0) + v
    return out


def _labor_tables():
    # (table, 지역 OBJ, 산업 코드 접두, 기간)
    return [
        ("DT_118N_SAUPN75", "190326INDUSTRY_10S", BIZ_FIRST, 2023),
        ("DT_118N_SAUPN78", "190326INDUSTRY_10S", BIZ_FIRST, 2023),
        ("DT_118N_SAUPM75", "INDUSTRY_11S", 2024, BIZ_LAST),
        ("DT_118N_SAUPM78", "INDUSTRY_11S", 2024, BIZ_LAST),
    ]


def establishments(res: Resolver):
    """{key: {ind: {year: {est, emp}}}} — 사업체노동실태현황 (1인 이상 사업체)."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for tbl, ip, y0, y1 in _labor_tables():
        meta = kosis.meta("118", tbl)
        reg_obj = next(r["OBJ_ID"] for r in meta if r["OBJ_ID"] not in ("ITEM", "15118SIZES_07") and "INDUSTRY" not in r["OBJ_ID"])
        parent = {r["ITM_ID"]: r.get("UP_ITM_ID") for r in meta if r["OBJ_ID"] == reg_obj}
        inds = "+".join(ip + s for s in ("0", "G", "I"))
        rows = kosis.data("118", tbl, itm="16118ED_1+16118ED_9A", objs={1: "ALL", 2: inds, 3: "15118SIZES_0700"},
                          start=str(y0), end=str(y1))
        for r in rows:
            rc = r["C1"]
            up = parent.get(rc)
            if up is None:  # 시도 합계 행 → 단위 합으로 대체
                continue
            stat_code = up.split("_")[-1]
            sd = STAT_PREFIX.get(stat_code)
            k = res(sd, r["C1_NM"], tbl)
            if k is None:
                continue
            ind = r["C2"].replace(ip, "")
            v = num(r["DT"])
            if v is None:
                continue
            f = "est" if r["ITM_ID"] == "16118ED_1" else "emp"
            d = out[k][ind][int(r["PRD_DE"])]
            d[f] = d.get(f, 0) + v
    return out


def _adm_rows(tbl, itm, objs, start, end, res: Resolver, src):
    """행정코드 표 → (key, row). 단위 판정은 이름 매칭으로 하고(일반구는 단위 목록에 없어 자연 제외),
    같은 단위·연도에 여러 코드가 대응하면(예: 인천 남구 28170 → 미추홀구 28177) 가장 최신(큰) 코드만 쓴다."""
    rows = kosis.data("101", tbl, itm=itm, objs=objs, start=str(start), end=str(end))
    names = {r["C1"]: r["C1_NM"] for r in rows}
    quiet = Resolver(res.units)
    picked: dict[tuple[str, str], str] = {}
    keyed = []
    for r in rows:
        c = r["C1"]
        if c == "00" or len(c) != 5 or "출장소" in names[c]:
            continue
        sd = adm_sido(c, names[c])
        k = (res if is_unit(c, names[c], names) else quiet)(sd, names[c], src)
        if not k:
            continue
        pk = (k, r["PRD_DE"])
        if c > picked.get(pk, ""):
            picked[pk] = c
        keyed.append((k, r))
    for k, r in keyed:
        if picked[(k, r["PRD_DE"])] == r["C1"]:
            yield k, r


def net_migration(res: Resolver):
    """{key: {year: {total, young}}} — 연간 순이동(전입-전출), young = 20~39세."""
    out = defaultdict(lambda: defaultdict(lambda: {"total": 0.0, "young": 0.0}))
    seen = set()
    for k, r in _adm_rows("DT_1B26002", "T60", {1: "ALL", 2: "0", 3: "000+" + "+".join(YOUNG_CODES)},
                          YEARS_HIST[0], YEARS_HIST[-1], res, "순이동"):
        uid = (k, r["C1"], r["C3"], r["PRD_DE"])
        if uid in seen:
            continue
        seen.add(uid)
        v = num(r["DT"]) or 0.0
        y = int(r["PRD_DE"])
        if r["C3"] == "000":
            out[k][y]["total"] += v
        else:
            out[k][y]["young"] += v
    return out


def households(res: Resolver):
    out = defaultdict(dict)
    for k, r in _adm_rows("DT_1B040B3", "T1", {1: "ALL"}, YEARS_HIST[0], YEARS_HIST[-1], res, "세대수"):
        v = num(r["DT"])
        if v is not None:
            y = int(r["PRD_DE"])
            out[k][y] = out[k].get(y, 0) + v
    return out


def vacancy(res: Resolver):
    """{key: {year: {rate, vacant, houses}}}"""
    rows = kosis.data("101", "DT_1YL202005", itm="T10+T20+T30", objs={1: "ALL"}, start="2015", end="2025")
    out = defaultdict(lambda: defaultdict(dict))
    f = {"T10": "rate", "T20": "vacant", "T30": "houses"}
    for r in rows:
        c = r["C1"]
        if c == "00":
            k = "00"
        elif not stat_is_sgg(c):
            k = stat_sido(c)
        else:
            k = res(stat_sido(c), r["C1_NM"], "빈집")
        v = num(r["DT"])
        if k and v is not None:
            out[k][int(r["PRD_DE"])][f[r["ITM_ID"]]] = v
    return out


# ------------------------------------------------------------------ 지표

def cagr(a, b, n):
    if not a or not b or a <= 0 or b <= 0 or n <= 0:
        return None
    return (b / a) ** (1 / n) - 1


def zscores(vals: dict[str, float | None]):
    xs = [v for v in vals.values() if v is not None]
    if len(xs) < 3:
        return {k: 0.0 for k in vals}
    mu, sd = statistics.mean(xs), statistics.pstdev(xs) or 1.0
    return {k: (max(min((v - mu) / sd, 3), -3) if v is not None else 0.0) for k, v in vals.items()}


def r1(x, n=1):
    return None if x is None else round(x, n)


def ri(x):
    return None if x is None else int(round(x))


def build(popr=None):
    popr = popr or run_all.population()
    units = popr["units"]
    total, proj, codes = popr["total"], popr["proj"], popr["codes"]
    res = Resolver(units)

    ent = enterprise_demography(res)
    est = establishments(res)
    mig = net_migration(res)
    hh = households(res)
    vac = vacancy(res)

    def consumers(k, y):
        if y <= 2025:
            v = total.get(y, {}).get(k)
        else:
            v = proj.get(k, {}).get("mid", {}).get(y)
        return sum(v[a] for a in CONSUMER_AGES) if v else None

    def consumer_series(k):
        out = {"actual": {}, "low": {}, "mid": {}, "high": {}}
        for y in YEARS_HIST:
            v = total.get(y, {}).get(k)
            if v:
                out["actual"][y] = ri(sum(v[a] for a in CONSUMER_AGES))
        for s in ("low", "mid", "high"):
            for y in range(2026, 2046):
                v = proj.get(k, {}).get(s, {}).get(y)
                if v:
                    out[s][y] = ri(sum(v[a] for a in CONSUMER_AGES))
        return out

    def young_pop(k, y):
        v = total.get(y, {}).get(k)
        return sum(v[20:40]) if v else None

    def gi(series_by_ind, y, f):
        vals = [series_by_ind.get(i, {}).get(y, {}).get(f) for i in IND]
        return sum(vals) if all(v is not None for v in vals) else None

    raw = {}
    for k in units:
        e, s = ent.get(k, {}), est.get(k, {})
        # 상권 사업체·종사자 (고용부)
        est_hist = {y: ri(gi(s, y, "est")) for y in range(BIZ_FIRST, BIZ_LAST + 1)}
        emp_hist = {y: ri(gi(s, y, "emp")) for y in range(BIZ_FIRST, BIZ_LAST + 1)}
        est_g = cagr(est_hist.get(GROWTH_FROM), est_hist.get(BIZ_LAST), BIZ_LAST - GROWTH_FROM)
        emp_g = cagr(emp_hist.get(GROWTH_FROM), emp_hist.get(BIZ_LAST), BIZ_LAST - GROWTH_FROM)
        # 기업 신생·소멸 (G+I)
        dem = {}
        for y in range(2016, 2026):
            a, b, d = gi(e, y, "active"), gi(e, y, "birth"), gi(e, y, "death")
            dem[y] = {"active": ri(a), "birth": ri(b), "death": ri(d),
                      "birthRate": r1(b / a * 100) if a and b is not None else None,
                      "deathRate": r1(d / a * 100) if a and d is not None else None}
        ne_years = [y for y in (2022, 2023, 2024) if dem[y]["birthRate"] is not None and dem[y]["deathRate"] is not None]
        net_entry = statistics.mean(dem[y]["birthRate"] - dem[y]["deathRate"] for y in ne_years) if ne_years else None
        # 소비인구
        c25, c30, c35 = consumers(k, 2025), consumers(k, 2030), consumers(k, 2035)
        cons_chg30 = c30 / c25 - 1 if c25 and c30 else None
        cons_chg35 = c35 / c25 - 1 if c25 and c35 else None
        # 청년 순이동률 (최근 3년 평균, 20~39세 1천명당)
        m = mig.get(k, {})
        yr = [(m[y]["young"], young_pop(k, y)) for y in (2023, 2024, 2025) if y in m and young_pop(k, y)]
        young_mig = statistics.mean(v / p * 1000 for v, p in yr) if yr else None
        stores = est_hist.get(BIZ_LAST)
        dens = stores / c25 * 1000 if stores and c25 else None
        raw[k] = dict(est_hist=est_hist, emp_hist=emp_hist, est_g=est_g, emp_g=emp_g, dem=dem, net_entry=net_entry,
                      c25=c25, c30=c30, c35=c35, cons_chg30=cons_chg30, cons_chg35=cons_chg35,
                      young_mig=young_mig, dens=dens)

    comp = {
        "estGrowth": zscores({k: v["est_g"] for k, v in raw.items()}),
        "empGrowth": zscores({k: v["emp_g"] for k, v in raw.items()}),
        "netEntry": zscores({k: v["net_entry"] for k, v in raw.items()}),
        "consumers2030": zscores({k: v["cons_chg30"] for k, v in raw.items()}),
        "youngMigration": zscores({k: v["young_mig"] for k, v in raw.items()}),
    }
    weights = {"estGrowth": 0.2, "empGrowth": 0.2, "netEntry": 0.2, "consumers2030": 0.25, "youngMigration": 0.15}

    regions = []
    for k in units:
        v = raw[k]
        z = sum(comp[c][k] * w for c, w in weights.items())
        idx = max(0, min(100, 50 + 15 * z))
        if v["cons_chg35"] is not None and v["cons_chg35"] <= -0.20 and (v["net_entry"] is None or v["net_entry"] <= 0):
            cls = "decline"     # 소멸위험
        elif idx < 42:
            cls = "shrink"      # 위축
        elif idx >= 58:
            cls = "growth"      # 성장
        else:
            cls = "stagnant"    # 정체
        sd, _, nm = k.partition("|")
        m = mig.get(k, {})
        h = hh.get(k, {})
        vc = vac.get(k, {})
        s_all = est.get(k, {}).get("0", {})
        regions.append({
            "id": codes.get(k, k),
            "key": k,
            "name": nm,
            "sido": SIDO[sd][0],
            "sidoCode": sd,
            "index": r1(idx),
            "class": cls,
            # 조기 신호: 점포는 늘고 있는데 2035년 소비인구는 20% 이상 감소 → 점포 과잉 위험
            "oversupply": bool(v["est_g"] is not None and v["est_g"] > 0 and v["cons_chg35"] is not None and v["cons_chg35"] <= -0.20),
            "components": {c: r1(comp[c][k], 2) for c in comp},
            "metrics": {
                "stores": v["est_hist"].get(BIZ_LAST),
                "workers": v["emp_hist"].get(BIZ_LAST),
                "storeGrowth": r1(v["est_g"] * 100, 2) if v["est_g"] is not None else None,       # %/년 2020→2024
                "workerGrowth": r1(v["emp_g"] * 100, 2) if v["emp_g"] is not None else None,
                "netEntry": r1(v["net_entry"], 2),                                                # %p, 2022~2024 평균
                "storesPer1k": r1(v["dens"], 1),                                                  # 20~64세 1천명당
                "consumers2025": ri(v["c25"]),
                "consumers2030": ri(v["c30"]),
                "consumers2035": ri(v["c35"]),
                "consumerChange2030": r1(v["cons_chg30"] * 100, 1) if v["cons_chg30"] is not None else None,
                "consumerChange2035": r1(v["cons_chg35"] * 100, 1) if v["cons_chg35"] is not None else None,
                # 점포 수가 그대로일 때 2035년 점포 1곳당 소비인구 변화 (= 수요 변화)
                "demandPerStore2035": r1(v["cons_chg35"] * 100, 1) if v["cons_chg35"] is not None else None,
                "storesPer1k2035": r1(v["est_hist"][BIZ_LAST] / v["c35"] * 1000, 1) if v["est_hist"].get(BIZ_LAST) and v["c35"] else None,
                "youngMigrationRate": r1(v["young_mig"], 1),                                       # 20~39세 1천명당/년
            },
            "series": {
                "stores": v["est_hist"],
                "workers": v["emp_hist"],
                "demography": v["dem"],
                "consumers": consumer_series(k),
            },
            # 「우리 동네의 미래」 보조 시계열
            "dongne": {
                "establishments": {y: ri(s_all.get(y, {}).get("est")) for y in range(BIZ_FIRST, BIZ_LAST + 1)},
                "employees": {y: ri(s_all.get(y, {}).get("emp")) for y in range(BIZ_FIRST, BIZ_LAST + 1)},
                "netMigration": {y: ri(m[y]["total"]) for y in sorted(m)},
                "netMigrationYoung": {y: ri(m[y]["young"]) for y in sorted(m)},
                "households": {y: ri(h[y]) for y in sorted(h)},
                "houses": {y: ri(vc[y].get("houses")) for y in sorted(vc)},
                "vacant": {y: ri(vc[y].get("vacant")) for y in sorted(vc)},
                "vacancyRate": {y: vc[y].get("rate") for y in sorted(vc)},
            },
        })

    regions.sort(key=lambda r: -r["index"])
    for i, r in enumerate(regions, 1):
        r["rank"] = i

    # 전국·시도 요약
    def agg(keys):
        def s(f):
            vals = [raw[k][f] for k in keys if raw[k][f] is not None]
            return sum(vals) if vals else None
        stores = {y: sum(raw[k]["est_hist"].get(y) or 0 for k in keys) for y in range(BIZ_FIRST, BIZ_LAST + 1)}
        c25, c35 = s("c25"), s("c35")
        return {"stores": stores, "workers": {y: sum(raw[k]["emp_hist"].get(y) or 0 for k in keys) for y in range(BIZ_FIRST, BIZ_LAST + 1)},
                "consumers2025": ri(c25), "consumers2035": ri(c35),
                "consumerChange2035": r1((c35 / c25 - 1) * 100, 1) if c25 and c35 else None}

    nat_dem = {}
    for y in range(2016, 2026):
        a, b, d = gi(ent.get("00", {}), y, "active"), gi(ent.get("00", {}), y, "birth"), gi(ent.get("00", {}), y, "death")
        nat_dem[y] = {"active": ri(a), "birth": ri(b), "death": ri(d),
                      "birthRate": r1(b / a * 100) if a and b is not None else None,
                      "deathRate": r1(d / a * 100) if a and d is not None else None}
    summary = {"00": {**agg(units), "demography": nat_dem, "name": "전국", "consumers": consumer_series("00")}}
    for sd in SIDO:
        ks = [k for k in units if k.startswith(sd + "|")]
        if ks:
            summary[sd] = {**agg(ks), "name": SIDO[sd][1]}
    counts = defaultdict(int)
    for r in regions:
        counts[r["class"]] += 1
        counts["oversupply"] += r["oversupply"]

    return {
        "meta": {
            "industries": "도매 및 소매업(G) + 숙박 및 음식점업(I)",
            "storeYears": [BIZ_FIRST, BIZ_LAST],
            "growthPeriod": [GROWTH_FROM, BIZ_LAST],
            "netEntryYears": [2022, 2024],
            "consumerAges": [20, 64],
            "weights": weights,
            "classes": {
                "growth": "성장: 활력 지수 58 이상",
                "stagnant": "정체: 활력 지수 42~58",
                "shrink": "위축: 활력 지수 42 미만",
                "decline": "소멸위험: 2035년 소비인구(20~64세) 20% 이상 감소 + 최근 3년 순진입률(신생률−소멸률) 0 이하",
            },
            "oversupply": "점포 과잉 신호: 2020→2024 상권 사업체 증가 + 2035년 소비인구 20% 이상 감소",
            "classCounts": dict(counts),
            "sources": [
                "통계청 기업생멸행정통계 시군구별 산업대분류별 기업 수(활동/신생/소멸) (KOSIS DT_6BD1132)",
                "고용노동부 사업체노동실태현황 시군구·산업별 사업체수·종사자수 (KOSIS DT_118N_SAUPN75, DT_118N_SAUPN78, DT_118N_SAUPM75, DT_118N_SAUPM78)",
                "통계청 국내인구이동통계 시군구/연령별 순이동자수 (KOSIS DT_1B26002)",
                "행정안전부 주민등록 세대수 (KOSIS DT_1B040B3)",
                "통계청 주택총조사 미거주주택(빈집) 비율 (KOSIS DT_1YL202005)",
                "행정안전부 주민등록인구 + 자체 인구추계 (KOSIS DT_1B04006)",
            ],
            "unmatched": {s: sorted(v) for s, v in unmatched.items()},
        },
        "summary": summary,
        "regions": regions,
    }


if __name__ == "__main__":
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB), regions={len(d['regions'])}")
    print("classes", d["meta"]["classCounts"])
    print("unmatched", d["meta"]["unmatched"])
    if "-v" in sys.argv:
        for r in d["regions"][:8] + d["regions"][-8:]:
            print(r["rank"], r["sido"], r["name"], r["index"], r["class"], r["metrics"])
