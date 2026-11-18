"""「예측 성적표」 — 이 사이트의 예측이 얼마나 맞았는지.

두 종류의 채점
  1. 과거 검증(백테스트): 과거 시점의 자료만 가지고 같은 방법을 돌려 그 뒤 실제와 비교
     - 인구 추계 엔진: 2020년 말 인구 → 2021~2025년 시군구 인구·65세 이상·0~9세
     - 학교: 2020년 말 인구 → 2021~2026년 시군구 초등학생 (school.json)
     - 출생 나우캐스트: 1995년 이후 해마다 'M월까지만 알았다면' (births.json)
     - 내년 출생아: 혼인 시차 모형의 1년 앞 예측 (births.json)
     - 대학 지역 배분: 전국 입학자가 줄던 시기의 시도별 배분 (univ.json)
     - 참고: 통계청 장래인구추계(2022년 기준) 출생아 vs 실제
  2. 실시간 장부(ledger): ETL을 돌릴 때마다 '아직 오지 않은 해'의 예측을 적어 두고,
     실측이 나오면 자동으로 채점한다. 사후에 고칠 수 없게 git 이력에 남는다.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import pop as P
from regions import SIDO

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
BT_BASE = 2020
BT_TR = [(2017, 2018), (2018, 2019), (2019, 2020)]
GROUPS = {"total": (0, 100), "old": (65, 100), "kids": (0, 9)}


def load(name):
    try:
        return json.loads((DATA / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def pop_backtest(popr):
    total, female, units = popr["total"], popr["female"], popr["units"]
    nat = P.national_ccr(total, BT_TR)
    end = max(total)
    errs = {g: defaultdict(list) for g in GROUPS}
    naive = defaultdict(list)  # 비교: '2020년 인구 그대로'
    worst = []
    for k in units:
        if k not in total[BT_BASE]:
            continue
        pj = P.project(total, female, k, nat, {"c": {}}, base_year=BT_BASE, transitions=BT_TR, end_year=end)["c"]
        for y in range(BT_BASE + 1, end + 1):
            act = total[y].get(k)
            if not act:
                continue
            h = y - BT_BASE
            for g, (a, b) in GROUPS.items():
                p, t = sum(pj[y][a:b + 1]), sum(act[a:b + 1])
                if t > 0:
                    errs[g][h].append(abs(p / t - 1))
            naive[h].append(abs(sum(total[BT_BASE][k]) / sum(act) - 1))
        last = total[end][k]
        e = sum(pj[end]) / sum(last) - 1
        sd, _, nm = k.partition("|")
        worst.append({"name": nm if sd == "36" else f"{SIDO[sd][0]} {nm}", "pred": round(sum(pj[end])), "actual": round(sum(last)), "err": round(e, 4)})
    worst.sort(key=lambda r: -abs(r["err"]))

    def summ(d):
        return {h: {"mae": round(sum(v) / len(v), 4), "median": round(median(v), 4),
                    "within2": round(sum(1 for x in v if x <= 0.02) / len(v), 3),
                    "within5": round(sum(1 for x in v if x <= 0.05) / len(v), 3), "n": len(v)} for h, v in sorted(d.items())}

    return {"base": BT_BASE, "end": end, "groups": {g: summ(d) for g, d in errs.items()}, "naive": summ(naive), "worst": worst[:10]}


def official_births(korea):
    b = korea["births"]
    act, off = b["actual"], b["official"]
    rows = []
    for y in sorted(act, key=int):
        if int(y) >= 2023 and y in off.get("mid", {}):
            rows.append({"year": int(y), "actual": act[y], "low": off["low"].get(y), "mid": off["mid"][y], "high": off["high"].get(y),
                         "errMid": round(off["mid"][y] / act[y] - 1, 4)})
    return rows


# ── 실시간 장부 ─────────────────────────────────────────────
def ledger_entries(popr, births, school, univ):
    """이번 실행에서 적을 '아직 실측이 없는' 예측들."""
    out = []
    if births:
        h, m = births["headline"], births["meta"]
        m = {**m, "asof": f"{m['asof'][:4]}년 {int(m['asof'][5:])}월"}
        out.append({"id": f"births:{m['year']}", "module": "births", "label": f"{m['year']}년 출생아 수", "year": m["year"],
                    "basis": f"{m['asof']} 자료까지", "pred": h["births"], "lo": h["lo"], "hi": h["hi"]})
        if h.get("tfr"):
            out.append({"id": f"tfr:{m['year']}", "module": "births", "label": f"{m['year']}년 합계출산율", "year": m["year"],
                        "basis": f"{m['asof']} 자료까지", "pred": h["tfr"], "lo": h.get("tfrLo"), "hi": h.get("tfrHi"), "digits": 3})
        out.append({"id": f"births:{m['year'] + 1}", "module": "births", "label": f"{m['year'] + 1}년 출생아 수", "year": m["year"] + 1,
                    "basis": f"{m['asof']} 자료까지", "pred": h["next"], "lo": h["nextLo"], "hi": h["nextHi"]})
    by = P.BASE_YEAR
    ny = by + 1
    if "00" in popr["proj"]:
        out.append({"id": f"pop:{ny}", "module": "korea", "label": f"{ny}년 말 주민등록 인구 (전국)", "year": ny,
                    "basis": f"{by}년 말 인구까지", "pred": round(sum(popr["proj"]["00"]["mid"][ny])),
                    "lo": round(sum(popr["proj"]["00"]["low"][ny])), "hi": round(sum(popr["proj"]["00"]["high"][ny]))})
        out.append({"id": f"pop65:{ny}", "module": "korea", "label": f"{ny}년 말 65세 이상 인구 (전국)", "year": ny,
                    "basis": f"{by}년 말 인구까지", "pred": round(sum(popr["proj"]["00"]["mid"][ny][65:]))})
    if school:
        nat = next(r for r in school["regions"] if r["key"] == "00")
        y = school["meta"]["lastActual"] + 1
        v = nat["proj"]["mid"].get(str(y))
        if v:
            out.append({"id": f"school:{y}", "module": "school", "label": f"{y}년 전국 초등학생 수", "year": y,
                        "basis": f"{school['meta']['lastActual']}년 학생 수까지", "pred": v,
                        "lo": nat["proj"]["low"].get(str(y)), "hi": nat["proj"]["high"].get(str(y))})
    if univ:
        y = univ["meta"]["last"] + 1
        d = univ["national"]["demand"]
        cap = univ["headline"]["cap"]
        mid = min(cap, d["mid"].get(str(y), cap))
        out.append({"id": f"univ:{y}", "module": "univ", "label": f"{y}년 대학·전문대 입학자 수", "year": y,
                    "basis": f"{univ['meta']['last']}년 입학자까지", "pred": mid,
                    "lo": min(cap, d["low"].get(str(y), cap)), "hi": min(cap, d["high"].get(str(y), cap))})
    return out


def actual_of(entry, popr, births, school, univ):
    mod, y, key = entry["module"], entry["year"], entry["id"].split(":")[0]
    try:
        if key == "births":
            return births["annual"]["births"].get(str(y))
        if key == "tfr":
            return births["annual"]["tfr"].get(str(y))
        if key == "pop":
            d = popr["total"].get(y, {}).get("00")
            return round(sum(d)) if d else None
        if key == "pop65":
            d = popr["total"].get(y, {}).get("00")
            return round(sum(d[65:])) if d else None
        if key == "school":
            nat = next(r for r in school["regions"] if r["key"] == "00")
            return nat["actual"].get(str(y))
        if key == "univ":
            return univ["national"]["entrantsTotal"].get(str(y))
    except (KeyError, TypeError, StopIteration):
        return None
    return None


def build(popr):
    births, school, univ, korea = load("births"), load("school"), load("univ"), load("korea")
    prev = load("track") or {}
    ledger = prev.get("ledger", [])
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()

    # 장부: 같은 예측 대상·같은 근거(basis)면 한 번만 적는다 (근거 자료가 새로 나오면 새 줄)
    seen = {(e["id"], e["basis"]) for e in ledger}
    for e in ledger_entries(popr, births, school, univ):
        if (e["id"], e["basis"]) not in seen:
            ledger.append({**e, "key": f"{e['id']}@{e['basis']}", "made": today})
    for e in ledger:
        a = actual_of(e, popr, births, school, univ)
        if a is not None:
            e["actual"] = a
            e["err"] = round(e["pred"] / a - 1, 4)
            if e.get("lo") is not None and e.get("hi") is not None:
                e["hit"] = e["lo"] <= a <= e["hi"]
    ledger.sort(key=lambda e: (e["year"], e["id"], e["made"]))

    pb = pop_backtest(popr)
    cards = []
    if school:
        bt = school["backtest"]
        cards.append({"module": "school", "title": "시군구 초등학생 수", "what": f"2020년 말 인구만으로 2021~{2020 + max(map(int, bt['mape']))}년 예측",
                      "n": bt["n"], "unit": "시군구", "mae": bt["mape"], "median": bt["median"]})
    g = pb["groups"]["total"]
    cards.append({"module": "korea", "title": "시군구 총인구", "what": f"{BT_BASE}년 말 인구만으로 {BT_BASE + 1}~{pb['end']}년 예측",
                  "n": g[max(g)]["n"], "unit": "시군구", "mae": {h: v["mae"] for h, v in g.items()}, "median": {h: v["median"] for h, v in g.items()}})
    if births:
        bm = births["backtest"]["byMonth"]
        cards.append({"module": "births", "title": "올해 출생아 수 (나우캐스트)", "what": "해마다 그해 M월까지 자료로 연간 출생아 추정",
                      "n": bm["1"]["n"], "unit": "개 연도", "mae": {m: v["mae"] for m, v in bm.items()}, "xLabel": "월까지 앎"})
    result = {
        "meta": {"updated": today, "btBase": BT_BASE,
                 "sources": ["이 사이트의 각 모듈 계산 결과 (school, births, univ, korea)", "행정안전부 주민등록인구 1세별 (KOSIS DT_1B04006)"]},
        "summary": {
            "pop1y": g[1]["mae"], "popEnd": g[max(g)]["mae"], "popEndH": max(g),
            "popNaiveEnd": pb["naive"][max(pb["naive"])]["mae"],
            "school6y": school["backtest"]["mape"].get("6") if school else None,
            "births8m": births["backtest"]["byMonth"].get("8", {}).get("mae") if births else None,
            "lag": births["backtest"]["lagMae"] if births else None, "lagNaive": births["backtest"]["naiveMae"] if births else None,
            "graded": sum(1 for e in ledger if "actual" in e), "pending": sum(1 for e in ledger if "actual" not in e),
            "hits": sum(1 for e in ledger if e.get("hit")), "withRange": sum(1 for e in ledger if "hit" in e),
        },
        "popBacktest": pb,
        "cards": cards,
        "births": {k: births["backtest"][k] for k in ("byMonth", "pseudo", "lag", "lagMae", "naiveMae")} if births else None,
        "univ": univ["backtest"]["regional"] if univ else None,
        "official": official_births(korea) if korea else None,
        "ledger": ledger,
    }
    return result


if __name__ == "__main__":
    import pickle, pprint
    popr = pickle.loads((ROOT / "data/raw/pop.pkl").read_bytes())
    d = build(popr)
    pprint.pprint(d["summary"]); pprint.pprint(d["popBacktest"]["groups"]); pprint.pprint(d["popBacktest"]["naive"])
    pprint.pprint(d["ledger"]); pprint.pprint(d["official"]); pprint.pprint(d["popBacktest"]["worst"][:5])
