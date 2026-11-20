"""누가, 어디로 이사 가나 — 행안부 행정동 간 인구이동(전입신고) 집계.

입력: data/mois/move/lv3/{YYYYMM}.csv.gz (etl/mois/collect_move.py export, 로컬 전용 원자료)
     src/data/dongne.json (지도 시군구 id·이름·2025년 인구)
출력: 시군구(지도 229개) 순이동, 연령대별 순이동, 주요 이동 경로, 행정동 순유입 상·하위, 월별 전국 추이.

- 원자료는 '전입 행정동 × 전출 행정동 × 성·1세 연령' 인원. 같은 행정동 안 이사는 없다.
- 지역 코드는 그 달의 행정구역 기준이라 사이트 지도(2025-12 경계)로 맞춘다:
  일반구 → 시, 강원 42→51·전북 45→52, 군위 47720→27720, 2026 전남광주(12)·인천 개편 → 옛 구역.
- 최근 12개월 창: 완결된 마지막 달까지 12개월. 원자료는 재배포하지 않고 집계만 낸다.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from regions import GWANGJU_GU

ROOT = Path(__file__).resolve().parent.parent
MOVE = ROOT / "data" / "mois" / "move" / "lv3"
SRC = ROOT / "src" / "data"

CAPITAL = {"11", "28", "41"}
AGE_GROUPS = [("kids", 0, 14), ("youth", 20, 34), ("mid", 35, 49), ("pre", 50, 64), ("old", 65, 110)]
MAX_AGE = 90  # 연령 곡선은 90세 이상을 합친다
INCHEON_DONGGU = ("만석", "화수", "화평", "송현", "송림", "금창")  # 옛 동구 행정동 → 2026 제물포구
TOP_PARTNERS = 5
TOP_FLOWS = 15
TOP_DONG = 12
MIN_DONG_POP_MOVES = 300  # 행정동 순위: 12개월 전입+전출 최소
# 농어촌 기본소득 시범사업 군 (농식품부): 2025-10-20 7곳, 2025년 말 추가 3곳, 2026-06-11 추가 7곳
BASIC_INCOME = {
    "bi1": [("경기", "연천군"), ("강원", "정선군"), ("충남", "청양군"), ("전북", "순창군"),
            ("전남", "신안군"), ("경북", "영양군"), ("경남", "남해군")],
    "bi1b": [("충북", "옥천군"), ("전북", "장수군"), ("전남", "곡성군")],
    "bi2": [("강원", "화천군"), ("충북", "보은군"), ("전북", "진안군"), ("전북", "무주군"), ("전남", "구례군"),
            ("전남", "보성군"), ("경북", "청송군")],
}


def ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f"{y + m // 12:04d}{m % 12 + 1:02d}"


def load_regions():
    d = json.loads((SRC / "dongne.json").read_text())
    regs = d["regions"]
    by = d["meta"]["baseYear"]
    return regs, by


def make_mapper(regs: list[dict]):
    ids = {r["id"] for r in regs}
    by_name = {(r["sidoCode"], r["name"]): r["id"] for r in regs}
    cache: dict[tuple, str | None] = {}

    def f(code10: str, sgg_nm: str, dong_nm: str) -> str | None:
        c = code10[:5]
        key = (c, sgg_nm, dong_nm if c == "28125" else "")
        if key in cache:
            return cache[key]
        out = None
        if c in ids:
            out = c
        elif c[:2] == "12":  # 2026-07 전남광주 통합 → 옛 광주(29)·전남(46)
            out = by_name.get(("29" if sgg_nm in GWANGJU_GU else "46", sgg_nm))
        elif c == "28125":  # 제물포구 = 옛 중구 내륙 + 옛 동구
            out = "28140" if dong_nm.startswith(INCHEON_DONGGU) else "28110"
        elif c == "28155":
            out = "28110"
        elif c in ("28275", "28290"):
            out = "28260"
        elif c == "47720":  # 군위군 2023-07 대구 편입
            out = "27720"
        else:
            alt = {"42": "51", "45": "52"}.get(c[:2], c[:2]) + c[2:]
            for cand in (alt, alt[:4] + "0"):
                if cand in ids:
                    out = cand
                    break
        cache[key] = out
        return out
    return f


def scan_month(args):
    """한 달 원자료 → (월 요약, 창 안이면 상세 집계). 프로세스 풀에서 돈다."""
    ym, detail = args
    regs, _ = load_regions()
    mp = make_mapper(regs)
    p = MOVE / f"{ym}.csv.gz"
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        rd = csv.reader(fh)
        hdr = next(rd)
        ix = {h: i for i, h in enumerate(hdr)}
        i_in, i_out, i_tot = ix["mvinAdmmCd"], ix["mvtAdmmCd"], ix["totNmprCnt"]
        i_ins, i_ind, i_outs, i_outd = ix["mvinSggNm"], ix["mvinDongNm"], ix["mvtSggNm"], ix["mvtDongNm"]
        i_ind_full = (ix["mvinCtpvNm"], ix["mvinSggNm"], ix["mvinDongNm"])
        m_age = [ix[f"male{a}AgeNmprCnt"] for a in range(111)]
        f_age = [ix[f"feml{a}AgeNmprCnt"] for a in range(111)]

        total = inter_sgg = inter_sido = 0
        cap_in = cap_out = 0          # 비수도권 → 수도권, 수도권 → 비수도권
        cap_in_y = cap_out_y = 0      # 20~34세
        unmapped: Counter = Counter()
        reg_net: Counter = Counter()             # 시군구 순이동 (이 달)
        # 상세 (창 안의 달만)
        flow: Counter = Counter()                 # (from_id, to_id) → 인원 (다른 시군구 사이)
        flow_age: dict = {}                       # (from_id, to_id) → 연령대별 인원 (AGE_GROUPS 순서)
        reg_age_in = defaultdict(lambda: [0] * (MAX_AGE + 1))
        reg_age_out = defaultdict(lambda: [0] * (MAX_AGE + 1))
        cap_age = [0] * (MAX_AGE + 1)             # 수도권 순유입(연령별)
        seoul_age = [0] * (MAX_AGE + 1)           # 서울 순유입(연령별)
        dong_in: Counter = Counter()
        dong_out: Counter = Counter()
        dong_name: dict[str, str] = {}

        for row in rd:
            n = int(row[i_tot])
            if not n:
                continue
            a = mp(row[i_in], row[i_ins], row[i_ind])
            b = mp(row[i_out], row[i_outs], row[i_outd])
            if a is None:
                unmapped[row[i_in][:5] + " " + row[i_ins]] += n
            if b is None:
                unmapped[row[i_out][:5] + " " + row[i_outs]] += n
            if a is None or b is None:
                continue
            total += n
            if a != b:
                inter_sgg += n
                reg_net[a] += n
                reg_net[b] -= n
            sa, sb = a[:2], b[:2]
            if sa != sb:
                inter_sido += n
            ca, cb = sa in CAPITAL, sb in CAPITAL
            need_age = (ca != cb) or (detail and a != b)
            ages = None
            if need_age:
                ages = [0] * (MAX_AGE + 1)
                for k in range(111):
                    v = int(row[m_age[k]]) + int(row[f_age[k]])
                    if v:
                        ages[min(k, MAX_AGE)] += v
            if ca != cb:
                y = sum(ages[20:35])
                if ca:
                    cap_in += n
                    cap_in_y += y
                else:
                    cap_out += n
                    cap_out_y += y
            if not detail:
                continue
            if detail == "full":
                ci, co = row[i_in], row[i_out]
                dong_in[ci] += n
                dong_out[co] += n
                if ci not in dong_name:
                    dong_name[ci] = " ".join(row[j] for j in i_ind_full)
            if a == b:
                continue
            flow[(b, a)] += n
            fa = flow_age.get((b, a))
            if fa is None:
                fa = flow_age[(b, a)] = [0] * len(AGE_GROUPS)
            for gi, (_, lo, hi) in enumerate(AGE_GROUPS):
                fa[gi] += sum(ages[lo:min(hi, MAX_AGE) + 1])
            if detail != "full":
                continue
            ri, ro = reg_age_in[a], reg_age_out[b]
            for k, v in enumerate(ages):
                if v:
                    ri[k] += v
                    ro[k] += v
            if ca != cb:
                sgn = 1 if ca else -1
                for k, v in enumerate(ages):
                    cap_age[k] += sgn * v
            if (sa == "11") != (sb == "11"):
                sgn = 1 if sa == "11" else -1
                for k, v in enumerate(ages):
                    seoul_age[k] += sgn * v

    summary = {"ym": ym, "total": total, "interSgg": inter_sgg, "interSido": inter_sido,
               "capIn": cap_in, "capOut": cap_out, "capInY": cap_in_y, "capOutY": cap_out_y,
               "unmapped": dict(unmapped), "regNet": dict(reg_net)}
    det = None
    if detail == "flow":
        det = {"flow": dict(flow), "flowAge": flow_age}
    elif detail:
        det = {"flow": dict(flow), "flowAge": flow_age, "ageIn": dict(reg_age_in), "ageOut": dict(reg_age_out),
               "capAge": cap_age, "seoulAge": seoul_age,
               "dongIn": dict(dong_in), "dongOut": dict(dong_out), "dongName": dong_name}
    return summary, det


FLOWS_DIR = ROOT / "public" / "data"
MIN_PAIR = 10  # 12개월 이동이 이보다 적은 시군구 쌍은 지도에서 뺀다


def write_flows(flow: Counter, flow_age: dict, win: list[str], name: str = "move_flows.json") -> dict:
    """지도 흐름용 시군구 쌍 집계(12개월): [출발 index, 도착 index, 전체, 연령대별...]. 원자료가 아니라 연간 합계.
    net: 시군구별 [전체, 연령대별...] 순이동 (쌍을 거르기 전 전체 합)."""
    out_path = FLOWS_DIR / name
    net: dict[str, list[int]] = defaultdict(lambda: [0] * (1 + len(AGE_GROUPS)))
    for (s, t), n in flow.items():
        v = [n, *flow_age.get((s, t), [0] * len(AGE_GROUPS))]
        for i, x in enumerate(v):
            net[t][i] += x
            net[s][i] -= x
    ids = sorted({x for k in flow for x in k})
    ix = {r: i for i, r in enumerate(ids)}
    rows = [[ix[s], ix[t], n, *flow_age.get((s, t), [0] * len(AGE_GROUPS))]
            for (s, t), n in sorted(flow.items(), key=lambda x: -x[1]) if n >= MIN_PAIR]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "period": [win[0], win[-1]], "ids": ids, "groups": ["all", *[k for k, _, _ in AGE_GROUPS]],
        "ages": {k: [lo, hi] for k, lo, hi in AGE_GROUPS}, "minPair": MIN_PAIR, "rows": rows,
        "net": dict(net),
    }, separators=(",", ":")))
    print(f"  → {out_path.relative_to(ROOT)} ({len(rows):,}쌍, {out_path.stat().st_size // 1024} KB)")
    return {"period": [win[0], win[-1]], "file": name}


def build():
    mf = MOVE / "manifest.json"
    if not mf.exists():
        print("  data/mois/move 없음 → 건너뜀 (기존 move.json 유지)")
        return None
    man = json.loads(mf.read_text())["months"]
    complete = sorted(ym for ym, v in man.items() if v.get("complete"))
    if len(complete) < 13:
        raise RuntimeError(f"완결된 달이 {len(complete)}개뿐")
    # 연속 구간만 (중간에 빠진 달이 없도록 최신에서 거꾸로)
    months = [complete[-1]]
    while ym_add(months[-1], -1) in complete:
        months.append(ym_add(months[-1], -1))
    months = months[::-1]
    last = months[-1]
    win = [ym_add(last, -k) for k in range(12)][::-1]
    fetched = max(max(man[ym]["fetched"]) for ym in months)

    regs, base_year = load_regions()
    pop = {r["id"]: r["series"]["low"][str(base_year)]["total"] for r in regs}
    names = {r["id"]: (r["sido"], r["name"]) for r in regs}

    # 흐름은 달력 연도(12달이 다 있는 해)별로도: 최근 12개월이 아닌 달은 흐름만 센다
    flow_years = [y for y in sorted({ym[:4] for ym in months}) if all(f"{y}{m:02d}" in months for m in range(1, 13))]
    jobs = [(ym, "full" if ym in win else ("flow" if ym[:4] in flow_years else "")) for ym in months]
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(scan_month, jobs))

    unmapped: Counter = Counter()
    for s, _ in results:
        unmapped.update(s["unmapped"])
    total_all = sum(s["total"] for s, _ in results)
    if sum(unmapped.values()) > total_all * 0.001:
        raise RuntimeError(f"지도에 못 맞춘 지역이 많음: {unmapped.most_common(10)}")
    if unmapped:
        print(f"  지도에 못 맞춘 이동 {sum(unmapped.values()):,}명 (제외): {unmapped.most_common(5)}")

    # ---- 창 합산
    flow: Counter = Counter()
    flow_age: dict = {}
    age_in = defaultdict(lambda: [0] * (MAX_AGE + 1))
    age_out = defaultdict(lambda: [0] * (MAX_AGE + 1))
    cap_age = [0] * (MAX_AGE + 1)
    seoul_age = [0] * (MAX_AGE + 1)
    dong_in: Counter = Counter()
    dong_out: Counter = Counter()
    dong_name: dict[str, str] = {}
    for s, d in results:
        if d is None or s["ym"] not in win:
            continue
        flow.update(d["flow"])
        for k, arr in d["flowAge"].items():
            t = flow_age.setdefault(k, [0] * len(AGE_GROUPS))
            for gi, v in enumerate(arr):
                t[gi] += v
        for tgt, src in ((age_in, d["ageIn"]), (age_out, d["ageOut"])):
            for rid, arr in src.items():
                t = tgt[rid]
                for k, v in enumerate(arr):
                    t[k] += v
        for k in range(MAX_AGE + 1):
            cap_age[k] += d["capAge"][k]
            seoul_age[k] += d["seoulAge"][k]
        dong_in.update(d["dongIn"])
        dong_out.update(d["dongOut"])
        dong_name.update(d["dongName"])  # 창의 마지막 달 이름이 남는다

    def grp(arr, lo, hi):
        return sum(arr[lo:min(hi, MAX_AGE) + 1])

    out_by: dict[str, Counter] = defaultdict(Counter)
    in_by: dict[str, Counter] = defaultdict(Counter)
    for (src, dst), n in flow.items():
        out_by[src][dst] += n
        in_by[dst][src] += n

    def r1(v):
        return round(v, 1)

    regions = {}
    for rid in pop:
        ai, ao = age_in.get(rid, [0] * (MAX_AGE + 1)), age_out.get(rid, [0] * (MAX_AGE + 1))
        n_in, n_out = sum(ai), sum(ao)
        p = pop[rid]
        rec = {"in": n_in, "out": n_out, "net": n_in - n_out, "rate": r1((n_in - n_out) / p * 1000), "pop": p}
        for key, lo, hi in AGE_GROUPS:
            net = grp(ai, lo, hi) - grp(ao, lo, hi)
            rec[key] = net
            rec[key + "Rate"] = r1(net / p * 1000)
        # 주요 상대 지역: 전입이 많이 온 곳, 전출이 많이 간 곳
        partners = Counter()
        for o, n in in_by[rid].items():
            partners[o] += n
        for o, n in out_by[rid].items():
            partners[o] += n
        rec["from"] = [[o, n] for o, n in in_by[rid].most_common(TOP_PARTNERS)]
        rec["to"] = [[o, n] for o, n in out_by[rid].most_common(TOP_PARTNERS)]
        # 순이동이 가장 큰 상대 (얻는 곳·잃는 곳)
        nets = {o: in_by[rid].get(o, 0) - out_by[rid].get(o, 0) for o in partners}
        rec["gainFrom"] = [[o, v] for o, v in sorted(nets.items(), key=lambda x: -x[1])[:3] if v > 0]
        rec["loseTo"] = [[o, -v] for o, v in sorted(nets.items(), key=lambda x: x[1])[:3] if v < 0]
        regions[rid] = rec

    # 주요 순이동 경로 (다른 시군구 쌍, 순이동 기준)
    pair_net = {}
    for (src, dst), n in flow.items():
        if (dst, src) in pair_net:
            continue
        back = flow.get((dst, src), 0)
        if n >= back:
            pair_net[(src, dst)] = (n - back, n, back)
        else:
            pair_net[(dst, src)] = (back - n, back, n)
    flows = [{"from": s, "to": t, "net": v[0], "fwd": v[1], "back": v[2]}
             for (s, t), v in sorted(pair_net.items(), key=lambda x: -x[1][0])[:TOP_FLOWS]]
    # 다른 시도로 가는 경로만 따로 (같은 시 안 이사를 빼고 보면)
    flows_cross = [{"from": s, "to": t, "net": v[0], "fwd": v[1], "back": v[2]}
                   for (s, t), v in sorted(pair_net.items(), key=lambda x: -x[1][0]) if s[:2] != t[:2]][:TOP_FLOWS]

    # 행정동 순유입 상·하위 (2026 개편 지역 코드도 그대로: 이름으로 보여 준다)
    dongs = []
    for code in set(dong_in) | set(dong_out):
        i, o = dong_in.get(code, 0), dong_out.get(code, 0)
        if i + o < MIN_DONG_POP_MOVES or code not in dong_name:
            continue
        dongs.append({"code": code, "name": dong_name[code], "in": i, "out": o, "net": i - o})
    dongs.sort(key=lambda x: -x["net"])
    dong_top = dongs[:TOP_DONG]
    dong_bottom = dongs[::-1][:TOP_DONG]

    # 월별 전국
    monthly = {"months": [s["ym"] for s, _ in results]}
    for k in ("total", "interSgg", "interSido"):
        monthly[k] = [s[k] for s, _ in results]
    monthly["capNet"] = [s["capIn"] - s["capOut"] for s, _ in results]
    monthly["capNetYouth"] = [s["capInY"] - s["capOutY"] for s, _ in results]

    # 기본소득 시범 군 vs 나머지 군: 월별 순이동률 (인구 1천 명당)
    by_name = {(r[0], r[1]): rid for rid, r in names.items()}
    bi = {g: [by_name[x] for x in xs] for g, xs in BASIC_INCOME.items()}
    bi_all = {i for ids in bi.values() for i in ids}
    other_gun = [rid for rid, (sd, nm) in names.items() if nm.endswith("군") and rid not in bi_all and rid[:2] not in CAPITAL | {"26", "27", "29", "30", "31", "36"}]
    groups = {**bi, "otherGun": other_gun}
    for g, ids in groups.items():
        p = sum(pop[i] for i in ids)
        monthly[g] = [round(sum(s["regNet"].get(i, 0) for i in ids) / p * 1000, 2) for s, _ in results]

    wres = [s for s, _ in results if s["ym"] in win]
    nat = {
        "total": sum(s["total"] for s in wres),
        "interSgg": sum(s["interSgg"] for s in wres),
        "interSido": sum(s["interSido"] for s in wres),
        "capNet": sum(s["capIn"] - s["capOut"] for s in wres),
        "capNetYouth": sum(s["capInY"] - s["capOutY"] for s in wres),
        "capIn": sum(s["capIn"] for s in wres),
        "capOut": sum(s["capOut"] for s in wres),
    }
    # 시도 순이동 (지도 시군구 합)
    sido = defaultdict(lambda: {"net": 0, "youth": 0, "pop": 0})
    for rid, r in regions.items():
        s = sido[rid[:2]]
        s["net"] += r["net"]  # 같은 시도 안 이동은 서로 상쇄된다
        s["youth"] += r["youth"]
        s["pop"] += r["pop"]
    sido_out = {k: {**v, "rate": r1(v["net"] / v["pop"] * 1000)} for k, v in sido.items()}

    flow_windows = []
    for y in flow_years:
        fy, fay = Counter(), {}
        for s, d in results:
            if d is None or s["ym"][:4] != y:
                continue
            fy.update(d["flow"])
            for k, arr in d["flowAge"].items():
                t = fay.setdefault(k, [0] * len(AGE_GROUPS))
                for gi, v in enumerate(arr):
                    t[gi] += v
        flow_windows.append({"key": y, "label": f"{y}년", **write_flows(fy, fay, [f"{y}01", f"{y}12"], f"move_flows_{y}.json")})
    flow_windows.append({"key": "recent", "label": "최근 1년", **write_flows(flow, flow_age, win)})

    return {
        "meta": {
            "period": [win[0], win[-1]], "first": months[0], "last": last, "fetched": fetched,
            "baseYear": base_year, "maxAge": MAX_AGE,
            "ageGroups": {k: [lo, hi] for k, lo, hi in AGE_GROUPS},
            "sources": ["행정안전부 주민등록 인구이동 통계 — 행정동별 전입·전출 (공공데이터포털 15108093)",
                        "행정안전부 주민등록인구 (시군구 인구, 우리 동네 데이터)"],
        },
        "national": nat,
        "sido": sido_out,
        "regions": regions,
        "names": {k: list(v) for k, v in names.items()},
        "flows": flows,
        "flowsCross": flows_cross,
        "dongTop": dong_top,
        "dongBottom": dong_bottom,
        "capAge": cap_age,
        "seoulAge": seoul_age,
        "monthly": monthly,
        "flowWindows": flow_windows,
        "basicIncome": {**bi, "otherGun": len(other_gun),
                        "rate12": {g: round(sum(regions[i]["net"] for i in ids) / sum(pop[i] for i in ids) * 1000, 1) for g, ids in groups.items()},
                        "net12": {g: sum(regions[i]["net"] for i in ids) for g, ids in groups.items()}},
    }


if __name__ == "__main__":
    import sys
    import time
    sys.path.insert(0, str(Path(__file__).parent))
    t = time.time()
    r = build()
    print(f"{time.time() - t:.0f}s")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        out.write_text(json.dumps(r, ensure_ascii=False))
    print(json.dumps({k: r[k] for k in ("meta", "national")}, ensure_ascii=False, indent=1))
