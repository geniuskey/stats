"""「우리 동네의 미래」 데이터.

결합
  - 주민등록 1세별 인구 + 자체 시군구 추계(pop.py) → 2045년 인구·연령구조·소멸위험지수
  - 통계청 시군구 장래인구추계(2022년 기준, DT_1BPB002E) → 공식 추계와 비교
  - commerce.json의 시군구 사업체·종사자·20~39세 순이동·주택·빈집 (build_commerce.py)
지속가능성 지수 = 인구 변화(2035) 30% + 청년 순이동 20% + 소멸위험지수 20% + 사업체 종사자 증감 15% + 빈집률(역) 15%
                  (시군구 분포 표준화 z 가중합 → 50 + 15z, 0~100)
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import kosis
import pop as P
from regions import SIDO, key, stat_is_sgg, stat_sido

ROOT = Path(__file__).resolve().parent.parent
END = 2045
SHOW = list(range(2015, END + 1))


def ind(ages, fem):
    tot = sum(ages)
    old = sum(ages[65:])
    w2039 = sum(fem[20:40]) if fem else None
    return {
        "total": round(tot),
        "kids": round(sum(ages[0:15])),
        "work": round(sum(ages[15:65])),
        "old": round(old),
        "oldShare": round(old / tot, 4) if tot else None,
        "kidShare": round(sum(ages[0:15]) / tot, 4) if tot else None,
        "young": round(sum(ages[20:40])),
        "births": round(ages[0]),
        "extinction": round(w2039 / old, 3) if (fem and old) else None,
    }


def official_sgg():
    rows = kosis.data("101", "DT_1BPB002E", itm="T10", objs={1: "ALL", 2: "0"}, start="2022", end="2042")
    out = defaultdict(dict)
    for r in rows:
        c = r["C1"]
        sd = stat_sido(c)
        if not sd:
            continue
        k = key(sd, r["C1_NM"]) if stat_is_sgg(c) else sd
        out[k][int(r["PRD_DE"])] = float(r["DT"])
    return out


def z(vals):
    xs = [v for v in vals if v is not None]
    if not xs:
        return [0.0] * len(vals)
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1
    return [max(min((v - m) / sd, 3), -3) if v is not None else 0.0 for v in vals]


def build(popr):
    total, female, proj, units, codes = popr["total"], popr["female"], popr["proj"], popr["units"], popr["codes"]
    off = official_sgg()
    cpath = ROOT / "src" / "data" / "commerce.json"
    com = {}
    if cpath.exists():
        for r in json.loads(cpath.read_text())["regions"]:
            com[r["key"]] = r

    regions = []
    for k in units:
        sd, _, nm = k.partition("|")
        hist = {y: total[y][k] for y in range(2015, P.BASE_YEAR + 1) if k in total[y]}
        fhist = {y: female[y].get(k) for y in hist}
        base = total[P.BASE_YEAR][k]
        fb = female[P.BASE_YEAR][k]
        fshare = [(fb[a] / base[a]) if base[a] else 0.5 for a in range(P.NAGE)]
        series = {}
        for s in ("low", "mid", "high"):
            row = {}
            for y in SHOW:
                if y in hist:
                    row[y] = ind(hist[y], fhist[y])
                elif y > P.BASE_YEAR:
                    a = proj[k][s][y]
                    f = [a[i] * (fshare[i - (y - P.BASE_YEAR)] if i >= (y - P.BASE_YEAR) else fshare[i]) for i in range(P.NAGE)]
                    row[y] = ind(a, f)
            series[s] = row
        mid = series["mid"]
        cur = mid[P.BASE_YEAR]
        first = min(hist)
        c = com.get(k, {})
        dn = c.get("dongne", {})
        met = c.get("metrics", {})
        vac = dn.get("vacancyRate") or {}
        vac_last = vac[max(vac, key=int)] if vac else None
        o = off.get(k, {})
        regions.append({
            "id": codes.get(k, k),
            "key": k,
            "name": nm,
            "sido": SIDO[sd][0],
            "sidoCode": sd,
            "series": {s: {y: {f: v[f] for f in ("total", "oldShare", "kidShare", "young", "births", "extinction", "kids", "work", "old")} for y, v in series[s].items()} for s in series},
            "official": {y: round(v) for y, v in sorted(o.items())},
            "ages2025": [round(x) for x in base],
            "ages2045": [round(x) for x in proj[k]["mid"][END]],
            "commerce": {
                "establishments": dn.get("establishments"),
                "employees": dn.get("employees"),
                "netMigrationYoung": dn.get("netMigrationYoung"),
                "netMigration": dn.get("netMigration"),
                "houses": dn.get("houses"),
                "vacant": dn.get("vacant"),
                "vacancyRate": vac or None,
                "class": c.get("class"),
                "index": c.get("index"),
            },
            "m": {
                "pop2015": round(sum(hist[first])),
                "pop2025": cur["total"],
                "pop2035": mid[2035]["total"],
                "pop2045": mid[END]["total"],
                "ch10": round(cur["total"] / sum(hist[first]) - 1, 4),
                "ch2035": round(mid[2035]["total"] / cur["total"] - 1, 4),
                "ch2045": round(mid[END]["total"] / cur["total"] - 1, 4),
                "ch2045low": round(series["low"][END]["total"] / cur["total"] - 1, 4),
                "ch2045high": round(series["high"][END]["total"] / cur["total"] - 1, 4),
                "oldShare2025": cur["oldShare"],
                "oldShare2045": mid[END]["oldShare"],
                "ext2025": cur["extinction"],
                "ext2035": mid[2035]["extinction"],
                "young2025": cur["young"],
                "young2045": mid[END]["young"],
                "oldHalfYear": next((y for y in sorted(mid) if mid[y]["oldShare"] and mid[y]["oldShare"] >= 0.5), None),
                "official2042": round(o[2042]) if 2042 in o else None,
                "ours2042": mid[2042]["total"],
                "youngMig": met.get("youngMigrationRate"),
                "empGrowth": met.get("workerGrowth"),
                "vacancy": vac_last,
            },
        })

    # 지속가능성 지수
    comps = [
        ("ch2035", 0.30, 1), ("youngMig", 0.20, 1), ("ext2025", 0.20, 1), ("empGrowth", 0.15, 1), ("vacancy", 0.15, -1),
    ]
    zs = {f: z([r["m"][f] * sgn if r["m"][f] is not None else None for r in regions]) for f, _, sgn in comps}
    for i, r in enumerate(regions):
        score = sum(zs[f][i] * w for f, w, _ in comps)
        r["m"]["index"] = round(max(0, min(100, 50 + 15 * score)), 1)
        r["m"]["components"] = {f: round(zs[f][i], 2) for f, _, _ in comps}
        e = r["m"]["ext2025"]
        ch = r["m"]["ch2045"]
        r["m"]["risk"] = ("소멸고위험" if e is not None and e < 0.2 else "소멸위험" if e is not None and e < 0.5 else "주의" if e is not None and e < 1.0 else "보통")
        r["m"]["outlook"] = "성장" if ch >= 0.05 else "유지" if ch >= -0.05 else "축소" if ch >= -0.2 else "급감"
    regions.sort(key=lambda r: -r["m"]["index"])
    for i, r in enumerate(regions):
        r["m"]["rank"] = i + 1

    counts = defaultdict(int)
    risk = defaultdict(int)
    for r in regions:
        counts[r["m"]["outlook"]] += 1
        risk[r["m"]["risk"]] += 1
    return {
        "meta": {
            "baseYear": P.BASE_YEAR,
            "end": END,
            "weights": {f: w for f, w, _ in comps},
            "sources": [
                "행정안전부 주민등록인구 1세별 (KOSIS DT_1B04006)",
                "통계청 장래인구추계 시군구 2022년 기준 (KOSIS DT_1BPB002E)",
                "통계청 국내인구이동통계 연령별 순이동 (KOSIS DT_1B26002)",
                "고용노동부 사업체노동실태현황 사업체·종사자 (KOSIS DT_118N_SAUP*)",
                "통계청 주택총조사 빈집 (e-지방지표 DT_1YL202005)",
                "통계청 장래인구추계 출산율 시나리오 (KOSIS DT_1BPA001/004/402/403)",
            ],
        },
        "counts": dict(counts),
        "risk": dict(risk),
        "regions": regions,
    }


if __name__ == "__main__":
    import run_all
    run_all.write("dongne", build(run_all.population()))
