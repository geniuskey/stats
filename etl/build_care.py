"""「우리 동네 의료·돌봄」 데이터 생성.

결합 데이터
  - 시군구 인구 추계 (pop.py): 0~9세, 20~44세 여성, 75세 이상, 연령별 인구
  - 노인의료복지시설(요양원 등) 정원·재가 장기요양기관 수 (국민건강보험공단 노인장기요양보험통계, 시군구)
  - 장기요양기관 요양보호사 수 (같은 통계, 시군구)
  - 의료기관 종사 의사 수 (e-지방지표, 시군구)
  - 표시과목별 의원 수: 소아청소년과·산부인과 (건강보험심사평가원, 시군구·분기)
  - 연령별 건강보험 진료비 (건강보험통계, 시도 합계 → 전국 연령별 1인당 진료비)

새 지표
  의료 수요 지수(t) = Σ_연령 1인당 진료비(연령) × 인구(연령, t)  ÷ 같은 값(기준연도)
      → 인구가 줄어도 고령화로 의료 수요는 늘 수 있다. '의사 1명당 의료 수요'는 의사 수가 그대로일 때.
  요양 정원 공백(t) = 75세 이상(t) × 지금의 '75세 이상 100명당 정원' − 지금 정원
  소아과 1곳당 0~9세(t), 산부인과 1곳당 가임여성(t)
"""
from __future__ import annotations

import re
from collections import defaultdict

import kosis
import pop as P
from build_school import jiji
from regions import SIDO

YEARS = [P.BASE_YEAR, 2030, 2035, 2040, 2045]  # 기준연도(현재) + 추계
PAST = [2015, 2020]                             # 실측 (인구·자원 모두 그해 값)
SERIES = PAST + YEARS
OLD_KEYS = {"27|군위군": "47|군위군", "28|미추홀구": "28|남구"}  # 지금 key → 과거 인구 표의 key
HIRA_Q = {2015: "201504", 2020: "202004"}       # 과거 의원 수는 그해 4분기
SHORT = {v[0]: k for k, v in SIDO.items()}
ALIAS = {
    ("26", "진구"): "26|부산진구", ("28", "남구"): "28|미추홀구",
    ("48", "마산시"): "48|창원시", ("48", "진해시"): "48|창원시",
    ("43", "청원군"): "43|청주시", ("44", "연기군"): "36|세종특별자치시",
    ("50", "남제주군"): "50|서귀포시", ("50", "북제주군"): "50|제주시",
    ("47", "군위군"): "27|군위군",
}
AGE_GROUPS = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 100)]


def resolve(sd: str, raw: str, units: set[str]) -> tuple[str | None, bool]:
    """(시도, 이름) → (분석 단위 key, 하위·옛 단위인지)."""
    name = " ".join(raw.split())
    if sd == "36":
        return "36|세종특별자치시", name not in ("세종", "세종시", "세종특별자치시")
    if (sd, name) in ALIAS:
        return ALIAS[(sd, name)], True
    k = f"{sd}|{name}"
    if k in units:
        return k, False
    m = re.match(r"^(\S+?시)\s*(\S.*구)$", name)  # '수원시 권선구', '수원시권선구', '고양시 일산 서구'
    if m and f"{sd}|{m.group(1)}" in units:
        return f"{sd}|{m.group(1)}", True
    return None, False


def find_sido(raw: str, units) -> str | None:
    """시도 코드 없이 온 '안산시상록구' 같은 행: 시 이름이 한 시도에만 있으면 그 시도."""
    m = re.match(r"^(\S+?시)", raw.replace(" ", ""))
    if not m:
        return None
    hits = {u.split("|")[0] for u in units if u.split("|")[1] == m.group(1)}
    return hits.pop() if len(hits) == 1 else None


class Agg:
    """같은 단위에 직접 행과 하위 구(또는 옛 시군) 행이 함께 올 때 이중 집계를 막는다."""

    def __init__(self):
        self.direct = defaultdict(float)
        self.sub = defaultdict(float)

    def add(self, k, sub, v):
        (self.sub if sub else self.direct)[k] += v

    def result(self):
        out = dict(self.sub)
        out.update({k: v for k, v in self.direct.items() if v > 0})
        return out


def hira(tbl: str, c2: str, prd: str | None = None, newest: bool = True, units=frozenset()):
    """심평원 시군구 표 → {key: value} (+ 시도 합계 {sd: value}), 기준 시점."""
    kw = {"newest": 1} if newest else {"start": prd, "end": prd}
    rows = kosis.data("354", tbl, objs={1: "ALL", 2: c2}, prd_se="Q", **kw)
    agg, sido_tot, nat, period = Agg(), {}, None, None
    code_sido = {}
    for r in rows:
        suf = r["C1"].split(".")[-1]
        if len(suf) == 2 and r["C1_NM"] in SHORT:
            code_sido[suf] = SHORT[r["C1_NM"]]
    for r in rows:
        if r["DT"] in ("", "-", None):
            continue
        v, suf = float(r["DT"]), r["C1"].split(".")[-1]
        period = r["PRD_DE"]
        if suf == "00":
            nat = v
        elif len(suf) == 2:
            if suf in code_sido:
                sido_tot[code_sido[suf]] = v
        else:
            sd = code_sido.get(suf[:2])
            if sd is None:
                continue
            k, sub = resolve(sd, r["C1_NM"], units)
            if k:
                agg.add(k, sub, v)
    return agg.result(), sido_tot, nat, period


def ltc(tbl: str, objs: dict, year: str | None = None, units=frozenset(), itm="ALL"):
    """노인장기요양보험 시군구 표 → {(itm, key): value}."""
    kw = {"start": year, "end": year} if year else {"newest": 1}
    rows = kosis.data("350", tbl, itm=itm, objs={1: "ALL", **objs}, **kw)
    letters = {}
    for r in rows:
        c = r["C1"]
        if c.endswith("Z1"):
            continue
        suf = c[len("15350AC400"):]
        if len(suf) == 2 and r["C1_NM"] in SHORT:
            letters[suf] = SHORT[r["C1_NM"]]
    out = defaultdict(Agg)
    sido_tot = defaultdict(dict)
    for r in rows:
        if r["DT"] in ("", "-", None):
            continue
        c, v = r["C1"], float(r["DT"])
        tag = (r["ITM_ID"], r.get("C2", ""))
        if c.endswith("Z1"):
            sido_tot[tag]["00"] = v
            continue
        if not c.startswith("15350AC400"):
            sd = find_sido(r["C1_NM"], units)
            suf = "??"  + "x"
        else:
            suf = c[len("15350AC400"):]
            sd = letters.get(suf[:2])
        if sd is None:
            continue
        if len(suf) == 2:
            sido_tot[tag][sd] = v
            if sd == "36":
                out[tag].add("36|세종특별자치시", False, v)
            continue
        k, sub = resolve(sd, r["C1_NM"], units)
        if k:
            out[tag].add(k, sub, v)
    return {t: a.result() for t, a in out.items()}, sido_tot, rows[0]["PRD_DE"] if rows else None


def cost_weights(total):
    """전국 연령대별 1인당 진료비 (원). 4개 권역 표의 시도 행을 합산."""
    tbls = ["TX_35003_A035", "TX_35003_A064", "TX_35003_A093", "TX_35003_A122"]
    cost = defaultdict(float)
    year = None
    for t in tbls:
        try:
            rows = kosis.data("350", t, itm="H004", objs={1: "ALL", 2: "ALL"}, newest=1)
        except RuntimeError:
            continue
        for r in rows:
            code = r["C1"]
            if len(code) != len("11101HJG25") or r["C2"].endswith("000") or r["DT"] in ("", "-"):
                continue  # 시도 행만, 합계 연령 제외
            cost[r["C2_NM"]] += float(r["DT"])
            year = int(r["PRD_DE"])
    labels = ["0~9세", "10~19세", "20~29세", "30~39세", "40~49세", "50~59세", "60~69세", "70~79세", "80세 이상"]
    y = min(year, P.BASE_YEAR) if year else P.BASE_YEAR
    nat = total[y]["00"]
    w = []
    for lab, (a, b) in zip(labels, AGE_GROUPS):
        pop = sum(nat[a:b + 1])
        w.append(cost[lab] * 1000 / pop if pop and cost.get(lab) else None)  # 진료비 단위 천원
    return w, labels, year


def rnd(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def build(popr):
    total, female, proj, units = popr["total"], popr["female"], popr["proj"], popr["units"]
    U = set(units)
    by = P.BASE_YEAR

    def actual(src, k, y):
        """기준연도까지의 1세별 인구. 과거 연도는 지금 경계로 맞춘다:
        옛 이름(군위군은 2023년 경북→대구, 미추홀구는 2018년 남구에서 개칭)으로 찾고,
        시도·전국은 지금 시군구를 더한다 (그래야 군위군이 그해 대구·경북 어느 쪽에 들어가는지와 무관)."""
        t = src.get(y, {})
        if y == by or (k != "00" and "|" in k):
            d = t.get(k) or t.get(OLD_KEYS.get(k, ""))
            return list(d) if d else None
        parts = [actual(src, u, y) for u in units if k == "00" or u.startswith(k + "|")]
        if not parts or any(x is None for x in parts):
            return None
        return [sum(col) for col in zip(*parts)]

    def ages(k, y, a, b, scen="mid"):
        d = actual(total, k, y) if y <= by else proj.get(k, {}).get(scen, {}).get(y)
        return sum(d[a:b + 1]) if d else None

    def women(k, y):
        # 20~44세 여성: 기준연도까지는 실측, 이후는 총인구 × 기준연도 여성 비중
        if y <= by:
            f = actual(female, k, y)
            return sum(f[20:45]) if f else None
        f = female[by].get(k)
        t = total[by].get(k)
        if not f or not t:
            return None
        share = sum(f[20:45]) / max(1, sum(t[20:45]))
        return ages(k, y, 20, 44) * share if ages(k, y, 20, 44) is not None else None

    # 자원
    ped, ped_sido, ped_nat, ped_prd = hira("DT_HIRA4G", "1535413102140068HD0.B", units=U)
    obg, obg_sido, obg_nat, _ = hira("DT_HIRA4G", "1535413102140068HD0.A", units=U)
    cli, cli_sido, cli_nat, _ = hira("DT_HIRA4G", "1535413102140068HD0.0", units=U)
    ped_old, _, ped_nat_old, ped_prd_old = hira("DT_HIRA4G", "1535413102140068HD0.B", prd="201602", newest=False, units=U)
    obg_old, _, obg_nat_old, _ = hira("DT_HIRA4G", "1535413102140068HD0.A", prd="201602", newest=False, units=U)
    fac, fac_sido, ltc_year = ltc("DT_35006_N021", {2: "003"}, units=U)
    beds = fac.get(("003", "003"), {})             # 노인의료복지시설 정원
    facs = fac.get(("002", "003"), {})             # 노인의료복지시설 기관 수
    cg, cg_sido, _ = ltc("DT_35006_N022", {2: "00107", 3: "350060A01"}, units=U)
    carers = next(iter(cg.values()), {})
    # 과거 자원 (실측): 요양 정원·요양보호사는 그해, 소아과 의원은 그해 4분기
    beds_p, carers_p, ped_p = {}, {}, {}
    for y in PAST:
        f, _, _ = ltc("DT_35006_N021", {2: "003"}, year=str(y), units=U)
        beds_p[y] = f.get(("003", "003"), {})
        c, _, _ = ltc("DT_35006_N022", {2: "00107", 3: "350060A01"}, year=str(y), units=U)
        carers_p[y] = next(iter(c.values()), {})
        ped_p[y] = hira("DT_HIRA4G", "1535413102140068HD0.B", prd=HIRA_Q[y], newest=False, units=U)[0]
    beds15 = beds_p[2015]
    docs_all = jiji("DT_1YL20981", itm="T001")
    w, wlabels, cost_year = cost_weights(total)

    def demand(k, y):
        d = actual(total, k, y) if y <= by else proj.get(k, {}).get("mid", {}).get(y)
        if not d:
            return None
        return sum(wi * sum(d[a:b + 1]) for wi, (a, b) in zip(w, AGE_GROUPS) if wi)

    nat_beds = sum(beds.values())
    nat_old75 = ages("00", by, 75, 100)
    rows = []
    keys = units + list(SIDO) + ["00"]
    sido_sum = lambda m, sd: sum(v for kk, v in m.items() if kk.startswith(sd + "|"))  # noqa: E731
    for k in keys:
        if k not in total[by]:
            continue
        level = "nation" if k == "00" else ("sgg" if "|" in k else "sido")
        if level == "sgg":
            g = lambda m: m.get(k)  # noqa: E731
        elif level == "sido":
            g = lambda m, sd=k: sido_sum(m, sd) if any(kk.startswith(sd + "|") for kk in m) else None  # noqa: E731
        else:
            g = lambda m: sum(m.values())  # noqa: E731
        o75 = {y: ages(k, y, 75, 100) for y in SERIES}
        kids = {y: ages(k, y, 0, 9) for y in SERIES}
        wom = {y: women(k, y) for y in SERIES}
        pop_ = {y: ages(k, y, 0, 100) for y in SERIES}
        dm = {y: demand(k, y) for y in SERIES}
        b, cr, pd, ob, hc = g(beds), g(carers), g(ped), g(obg), g(facs)
        pd0, ob0, b15 = g(ped_old), g(obg_old), g(beds15)
        bh = {y: g(beds_p[y]) for y in PAST}
        ch = {y: g(carers_p[y]) for y in PAST}
        ph = {y: g(ped_p[y]) for y in PAST}
        if level == "sgg":  # 심평원 표는 의원이 없는 시군구를 행으로 내지 않는다 → 0곳
            pd, ob, pd0, ob0 = pd or 0, ob or 0, pd0 or 0, ob0 or 0
            ph = {y: v or 0 for y, v in ph.items()}
        sd, _, nm = k.partition("|")
        dk = docs_all.get(k) or (docs_all.get("36", {}) if k == "36|세종특별자치시" else {})  # jiji: 시군구 key·시도 코드·'00' 같은 규칙
        docs = dk.get(max(dk)) if dk else None
        docs_year = max(dk) if dk else None
        d0 = dm[by]
        r = {
            "id": k if level != "sgg" else popr["codes"].get(k, k),
            "key": k, "level": level,
            "name": "전국" if k == "00" else (SIDO[k][1] if level == "sido" else nm),
            "sido": SIDO[sd][0] if level == "sgg" else "",
            "short": "전국" if k == "00" else SIDO[sd][0],
            "pop": {y: rnd(v) for y, v in pop_.items()},
            "old75": {y: rnd(v) for y, v in o75.items()},
            "kids": {y: rnd(v) for y, v in kids.items()},
            "women": {y: rnd(v) for y, v in wom.items()},
            "demandIdx": {y: round(v / d0, 4) if v is not None else None for y, v in dm.items()} if d0 else None,
            # 연도별 자원: 과거는 실측, 기준연도는 최신 값 (추계 연도는 '지금 그대로'라 싣지 않는다)
            "bedsHist": {**{y: rnd(v) for y, v in bh.items()}, by: rnd(b)},
            "carersHist": {**{y: rnd(v) for y, v in ch.items()}, by: rnd(cr)},
            "pedHist": {**{y: rnd(v) for y, v in ph.items()}, by: rnd(pd)},
            "beds": rnd(b), "beds2015": rnd(b15), "carers": rnd(cr), "facilities": rnd(hc),
            "ped": rnd(pd), "ped2016": rnd(pd0), "obg": rnd(ob), "obg2016": rnd(ob0),
            "docs": rnd(docs), "docsYear": docs_year,
        }
        old_now = o75[by]
        if b is not None and old_now:
            per = b / old_now
            r["bedsPer100"] = round(per * 100, 2)
            r["bedsNeed"] = {y: rnd(o75[y] * per) for y in YEARS}
            r["bedsGap2035"] = rnd(o75[2035] * per - b)
            r["bedsGap2045"] = rnd(o75[2045] * per - b)
            r["bedsPer100_2035"] = round(b / o75[2035] * 100, 2) if o75[2035] else None
        # 75세 100명당 정원: 과거는 그해 정원 ÷ 그해 75세 이상, 이후는 지금 정원 그대로
        bseries = {**bh, **{y: b for y in YEARS}}
        r["bedsPer100ByYear"] = {y: round(bseries[y] / o75[y] * 100, 2) if bseries.get(y) is not None and o75[y] else None for y in SERIES}
        if cr is not None and old_now:
            r["carersPer100"] = round(cr / old_now * 100, 2)
            r["carersGap2035"] = rnd(o75[2035] * cr / old_now - cr)
        if pd is not None:
            pseries = {**ph, **{y: pd for y in YEARS}}  # 과거는 그해 의원 수, 이후는 지금 그대로
            r["kidsPerPed"] = {y: rnd(kids[y] / pseries[y]) if pseries.get(y) and kids[y] is not None else None for y in SERIES}
        if ob is not None:
            r["womenPerObg"] = {y: rnd(wom[y] / ob) if ob and wom[y] else None for y in YEARS}
        if docs and d0:
            r["docsPer1000"] = round(docs / pop_[by] * 1000, 2)
            r["demandPerDoc"] = {y: round(dm[y] / d0, 4) for y in YEARS}  # 의사 수 고정 시 1명당 수요(기준=1)
        rows.append(r)

    # 검증: 시군구 합 ≈ 시도 표 합계
    def coverage(sgg_map, sido_map):
        out = {}
        for sd in SIDO:
            s = sido_sum(sgg_map, sd)
            t = sido_map.get(sd)
            if t:
                out[sd] = round(s / t, 3)
        return out

    sgg = [r for r in rows if r["level"] == "sgg"]
    nat = next(r for r in rows if r["key"] == "00")
    zero_ped = [r for r in sgg if (r.get("ped") or 0) == 0]
    zero_obg = [r for r in sgg if (r.get("obg") or 0) == 0]
    gap_regions = [r for r in sgg if r["old75"][by] and r["old75"][2035] >= 1.5 * r["old75"][by]]
    return {
        "meta": {
            "baseYear": by, "years": SERIES, "pastYears": PAST, "projYears": YEARS[1:],
            "clinicPeriodsPast": HIRA_Q, "ltcYear": ltc_year, "clinicPeriod": ped_prd, "clinicPeriodOld": ped_prd_old,
            "costYear": cost_year, "costWeights": [rnd(x) for x in w], "costLabels": wlabels,
            "coverage": {"ped": coverage(ped, ped_sido), "clinics": coverage(cli, cli_sido)},
            "sources": [
                "국민건강보험공단 노인장기요양보험통계 시·군·구별 급여종류별 장기요양기관 현황·전문인력 현황 (KOSIS DT_35006_N021, DT_35006_N022)",
                "건강보험심사평가원 시군구별 표시과목별 의원 현황 (KOSIS DT_HIRA4G)",
                "e-지방지표 인구 천명당 의료기관 종사 의사수 (KOSIS DT_1YL20981)",
                "국민건강보험공단 건강보험통계 시군구별 연령별 진료현황 (KOSIS TX_35003_A035, _A064, _A093, _A122)",
                "행정안전부 주민등록인구 1세별 (KOSIS DT_1B04006) + 이 사이트 인구 추계",
            ],
        },
        "headline": {
            "old75Now": nat["old75"][by], "old75_2035": nat["old75"][2035], "old75_2045": nat["old75"][2045],
            "beds": nat.get("beds"), "bedsGap2035": nat.get("bedsGap2035"), "bedsGap2045": nat.get("bedsGap2045"),
            "carers": nat.get("carers"), "carersGap2035": nat.get("carersGap2035"),
            "demand2035": nat["demandIdx"][2035], "demand2045": nat["demandIdx"][2045],
            "pop2045": round(nat["pop"][2045] / nat["pop"][by] - 1, 4),
            "ped": nat.get("ped"), "ped2016": nat.get("ped2016"), "obg": nat.get("obg"), "obg2016": nat.get("obg2016"),
            "zeroPed": len(zero_ped), "zeroObg": len(zero_obg), "sggCount": len(sgg),
            "old75Up50_2035": len(gap_regions),
            "demandUp2045": sum(1 for r in sgg if r["demandIdx"] and r["demandIdx"][2045] > 1),
            "popDown2045": sum(1 for r in sgg if r["pop"][2045] and r["pop"][by] and r["pop"][2045] < r["pop"][by]),
            "bedsPer100": nat.get("bedsPer100"),
            "natBedsCheck": rnd(nat_beds), "natOld75": rnd(nat_old75),
        },
        "regions": rows,
    }


if __name__ == "__main__":
    import pickle, pprint
    from pathlib import Path
    popr = pickle.loads((Path(__file__).resolve().parent.parent / "data/raw/pop.pkl").read_bytes())
    d = build(popr)
    pprint.pprint(d["meta"]); pprint.pprint(d["headline"])
    sgg = [r for r in d["regions"] if r["level"] == "sgg"]
    for f in ("beds", "carers", "ped", "obg", "docs", "facilities"):
        print(f, sum(1 for r in sgg if r.get(f) is None), "missing:", [r["key"] for r in sgg if r.get(f) is None][:10])
    for r in sgg[:3] + [x for x in sgg if x["key"] in ("41|수원시", "48|창원시", "41|부천시", "41|화성시", "47|울릉군")]:
        print({k: r.get(k) for k in ("key", "beds", "carers", "ped", "obg", "docs", "bedsPer100", "docsPer1000", "kidsPerPed", "demandIdx")})
