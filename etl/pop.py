"""주민등록 1세별 인구 수집 + 소지역 인구추계 엔진.

추계 방법: Hamilton-Perry 코호트 변화율(CCR)법
  P(a, t+1) = P(a-1, t) × CCR(a)
  - CCR(a)는 최근 3개 전환(2022→2023, 2023→2024, 2024→2025)의 합계 비율 → 사망과 순이동을 함께 반영
  - 지역 고유의 이동 효과는 해마다 7%씩 전국 평균으로 수렴시킨다(감쇠). 과거 개발 붐이 영원히 지속된다고 가정하지 않기 위함.
  P(0, t) = CR × W(t) × f_s(t)
  - CR: 20~44세 여성 1명당 0세 인구 비율(최근 3년 평균)
  - f_s(t): 통계청 장래인구추계(2022년 기준) 시나리오별 '가임여성 1명당 출생아' 지수 (2025=1)
"""
from __future__ import annotations

import json
from pathlib import Path

import kosis
from regions import SIDO, adm_sido, clean_name, is_unit, key

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data"

AGE_CODES = None  # KOSIS 연령 코드 (0세..100세 이상)
HIST_YEARS = list(range(2015, 2026))
BASE_YEAR = 2025
END_YEAR = 2050
TRANSITIONS = [(2022, 2023), (2023, 2024), (2024, 2025)]
DECAY = 0.85
NAGE = 101  # 0..99, 100+
W_LO, W_HI = 20, 44


def age_codes() -> list[str]:
    global AGE_CODES
    if AGE_CODES is None:
        m = kosis.meta("101", "DT_1B04006")
        AGE_CODES = [r["ITM_ID"] for r in m if r["OBJ_ID"] == "YRE" and r["ITM_ID"] != "000"]
        assert len(AGE_CODES) == NAGE, len(AGE_CODES)
    return AGE_CODES


def _fetch_year(year: int, itm: str):
    """year -> {region_key: [101 ages]} (분석 단위만) + 시도/전국 합계."""
    rows = kosis.data("101", "DT_1B04006", itm=itm, objs={1: "ALL", 2: "ALL"}, start=str(year), end=str(year))
    idx = {c: i for i, c in enumerate(age_codes())}
    names = {r["C1"]: clean_name(r["C1_NM"]) for r in rows}
    out: dict[str, list[float]] = {}
    for r in rows:
        c, a = r["C1"], r["C2"]
        if a not in idx:
            continue
        if c == "00":
            k = "00"
        elif len(c) == 2:
            continue  # 시도 합계는 단위 합으로 재계산
        elif is_unit(c, names[c], names):
            sd = adm_sido(c, names[c])
            if sd is None:
                continue
            k = key(sd, names[c])
        else:
            continue
        v = float(r["DT"]) if r["DT"] not in ("", "-") else 0.0
        out.setdefault(k, [0.0] * NAGE)[idx[a]] += v
    return out, {key(adm_sido(c, n) or "", n): c for c, n in names.items() if is_unit(c, n, names)}


# 행정구역 개편: 과거 연도 표의 옛 key → 지금 key (지금 경계로 시계열을 잇는다)
RENAMED = {
    "47|군위군": "27|군위군",   # 2023.7 경북 → 대구 편입
    "28|남구": "28|미추홀구",   # 2018.7 인천 남구 → 미추홀구
}


def load_population():
    """{'total': {year: {key: ages}}, 'female': {...}, 'codes': {key: adm_code}}"""
    total, female, codes = {}, {}, {}
    for y in HIST_YEARS:
        total[y], c = _fetch_year(y, "T2")
        female[y], _ = _fetch_year(y, "T4")
        for d in (total[y], female[y]):
            for old, new in RENAMED.items():
                if old in d:
                    v = d.pop(old)
                    d.setdefault(new, v)
        codes.update(c)
    for old in RENAMED:
        codes.pop(old, None)
    return {"total": total, "female": female, "codes": codes}


def add_sido_totals(series: dict[int, dict[str, list[float]]], units: list[str]):
    for y, d in series.items():
        for sd in SIDO:
            acc = [0.0] * NAGE
            found = False
            for k in units:
                if k.startswith(sd + "|") and k in d:
                    found = True
                    acc = [a + b for a, b in zip(acc, d[k])]
            if found:
                d[sd] = acc


# ---------------------------------------------------------------- 출산 시나리오

def fertility_index() -> dict[str, dict[int, float]]:
    """시나리오별 f(t) = [출생아(t)/20~44세 여성(t)] / [같은 값(2025)]."""
    w_codes = ["120", "130", "150", "160", "180"]
    births = {}
    women = {}
    # 중위
    b = kosis.data("101", "DT_1BPA004", objs={1: "1", 2: "20"}, start="2022", end=str(END_YEAR))
    births["mid"] = {int(r["PRD_DE"]): float(r["DT"]) * 1000 for r in b}
    w = kosis.data("101", "DT_1BPA001", objs={1: "1", 2: "2", 3: "+".join(w_codes)}, start="2022", end=str(END_YEAR))
    women["mid"] = {}
    for r in w:
        women["mid"][int(r["PRD_DE"])] = women["mid"].get(int(r["PRD_DE"]), 0) + float(r["DT"])
    for s, code in (("high", "01"), ("low", "02")):
        b = kosis.data("101", "DT_1BPA403", objs={1: code, 2: "20"}, start="2022", end=str(END_YEAR))
        births[s] = {int(r["PRD_DE"]): float(r["DT"]) * 1000 for r in b}
        w = kosis.data("101", "DT_1BPA402", objs={1: code, 2: "2", 3: "+".join(w_codes)}, start="2022", end=str(END_YEAR))
        women[s] = {}
        for r in w:
            women[s][int(r["PRD_DE"])] = women[s].get(int(r["PRD_DE"]), 0) + float(r["DT"])
    out = {}
    for s in births:
        base = births[s][BASE_YEAR] / women[s][BASE_YEAR]
        out[s] = {y: (births[s][y] / women[s][y]) / base for y in range(BASE_YEAR + 1, END_YEAR + 1)}
    return {"index": out, "births": births}


# ---------------------------------------------------------------- 추계

def _ccr(total, k, transitions=TRANSITIONS):
    num = [0.0] * NAGE
    den = [0.0] * NAGE
    for t0, t1 in transitions:
        p0, p1 = total[t0].get(k), total[t1].get(k)
        if p0 is None or p1 is None:
            continue
        for a in range(1, NAGE):
            num[a] += p1[a]
            den[a] += p0[a - 1] + (p0[a] if a == NAGE - 1 else 0)
    return num, den


def _women(ages, fem_share):
    return sum(ages[a] * fem_share[a] for a in range(W_LO, W_HI + 1))


MAX_EXCESS = 0.08  # 연간 지역 순이동 효과 상한(±8%)


def project(total, female, k, nat_ccr, fert_index, base_year=BASE_YEAR, transitions=TRANSITIONS,
            end_year=END_YEAR, parent_ccr=None):
    """한 지역의 시나리오별 추계. 반환: {scenario: {year: ages}}

    지역 CCR은 표본 크기에 따라 상위(시도) CCR로 수축(shrinkage)시키고,
    전국 대비 초과분(=지역 고유 순이동)은 상한을 두고 해마다 DECAY 비율로 감쇠한다.
    """
    num, den = _ccr(total, k, transitions)
    ref = parent_ccr or nat_ccr
    ccr = [1.0] * NAGE
    for a in range(1, NAGE):
        if den[a] > 0:
            w = den[a] / (den[a] + 300.0)  # 작은 코호트일수록 상위 지역 값에 가깝게
            raw = num[a] / den[a]
            ccr[a] = w * raw + (1 - w) * ref[a]
        else:
            ccr[a] = ref[a]
        ex = max(min(ccr[a] - nat_ccr[a], MAX_EXCESS), -MAX_EXCESS)
        ccr[a] = nat_ccr[a] + ex
    base = total[base_year][k]
    fb = female[base_year].get(k, [0.0] * NAGE)
    fem_share = [(fb[a] / base[a]) if base[a] > 0 else 0.5 for a in range(NAGE)]
    c_num = c_den = 0.0
    for y in (base_year - 2, base_year - 1, base_year):
        if k in total.get(y, {}) and k in female.get(y, {}):
            c_num += total[y][k][0]
            c_den += sum(female[y][k][W_LO:W_HI + 1])
    cr = c_num / c_den if c_den > 0 else 0.0

    res = {}
    for s, f in fert_index.items():
        cur = list(base)
        series = {base_year: cur}
        for i, y in enumerate(range(base_year + 1, end_year + 1)):
            d = DECAY ** i
            nxt = [0.0] * NAGE
            for a in range(1, NAGE):
                r = nat_ccr[a] + (ccr[a] - nat_ccr[a]) * d
                src = cur[a - 1] + (cur[a] if a == NAGE - 1 else 0)
                nxt[a] = src * r
            nxt[0] = cr * _women(nxt, fem_share) * f.get(y, 1.0)
            series[y] = nxt
            cur = nxt
        res[s] = series
    return res


def national_ccr(total, transitions=TRANSITIONS):
    num, den = _ccr(total, "00", transitions)
    return [1.0] + [num[a] / den[a] if den[a] else 1.0 for a in range(1, NAGE)]


def run():
    pop = load_population()
    total, female = pop["total"], pop["female"]
    units = sorted(k for k in total[BASE_YEAR] if k != "00")
    add_sido_totals(total, units)
    add_sido_totals(female, units)
    fert = fertility_index()
    nat = national_ccr(total)
    sido_ccr = {}
    for sd in SIDO:
        if sd in total[BASE_YEAR]:
            n, d = _ccr(total, sd)
            sido_ccr[sd] = [1.0] + [n[a] / d[a] if d[a] else nat[a] for a in range(1, NAGE)]
    proj = {}
    for k in units + list(SIDO) + ["00"]:
        if k in total[BASE_YEAR]:
            proj[k] = project(total, female, k, nat, fert["index"], parent_ccr=sido_ccr.get(k.split("|")[0]) if "|" in k else None)
    # 전국은 단위 합으로 다시 맞춘다(지역 추계의 합 = 전국)
    for s in fert["index"]:
        for y in proj["00"][s]:
            proj["00"][s][y] = [sum(proj[u][s][y][a] for u in units) for a in range(NAGE)]
        for sd in SIDO:
            if sd in proj:
                for y in proj[sd][s]:
                    proj[sd][s][y] = [sum(proj[u][s][y][a] for u in units if u.startswith(sd + "|")) for a in range(NAGE)]
    return {"total": total, "female": female, "codes": pop["codes"], "units": units, "proj": proj, "fert": fert}


if __name__ == "__main__":
    r = run()
    print(len(r["units"]))
    for s in ("low", "mid", "high"):
        p = r["proj"]["00"][s]
        print(s, {y: round(sum(p[y])) for y in (2025, 2030, 2040, 2050)}, "0세", {y: round(p[y][0]) for y in (2026, 2030, 2040)})


# ---------------------------------------------------------------- 시각화용 프레임

GROUPS5 = [(a, a + 4) for a in range(0, 100, 5)] + [(100, 100)]


def pyramid_frames(total, female, proj_series, k, years, base_year=BASE_YEAR):
    """연도별 5세 단위 남/여 인구 프레임 (애니메이션 피라미드용).

    실측 연도는 주민등록 남녀, 추계 연도는 기준연도의 같은 출생 코호트 여성 비율을 적용한다.
    반환: {"years": [...], "m": [[21]...], "f": [[21]...], "proj": 첫 추계 연도}
    """
    tb, fb = total[base_year][k], female[base_year][k]
    fshare = [(fb[a] / tb[a]) if tb[a] else 0.5 for a in range(NAGE)]
    out = {"years": [], "m": [], "f": [], "proj": base_year + 1}
    for y in years:
        if y <= base_year:
            t, f = total.get(y, {}).get(k), female.get(y, {}).get(k)
            if t is None or f is None:
                continue
        else:
            t = proj_series[y]
            s = y - base_year
            f = [t[a] * (fshare[a - s] if a >= s else fshare[a]) for a in range(NAGE)]
        mm, ff = [], []
        for lo, hi in GROUPS5:
            w = sum(f[lo:hi + 1])
            ff.append(round(w))
            mm.append(round(sum(t[lo:hi + 1]) - w))
        out["years"].append(y)
        out["m"].append(mm)
        out["f"].append(ff)
    return out


def sim_params(total, female, transitions=TRANSITIONS, base_year=BASE_YEAR):
    """브라우저 인구 시뮬레이터 입력: 전국 기준연도 1세별 남녀 인구, 성별 코호트 변화율, 아동비."""
    k = "00"

    def male(y):
        return [t - f for t, f in zip(total[y][k], female[y][k])]

    def ccr(get):
        num, den = [0.0] * NAGE, [0.0] * NAGE
        for t0, t1 in transitions:
            p0, p1 = get(t0), get(t1)
            for a in range(1, NAGE):
                num[a] += p1[a]
                den[a] += p0[a - 1] + (p0[a] if a == NAGE - 1 else 0)
        return [1.0] + [round(num[a] / den[a], 5) if den[a] else 1.0 for a in range(1, NAGE)]

    c_num = c_den = 0.0
    boys = 0.0
    for y in (base_year - 2, base_year - 1, base_year):
        c_num += total[y][k][0]
        boys += total[y][k][0] - female[y][k][0]
        c_den += sum(female[y][k][W_LO:W_HI + 1])
    return {
        "baseYear": base_year,
        "male": [round(x) for x in male(base_year)],
        "female": [round(x) for x in female[base_year][k]],
        "ccrMale": ccr(male),
        "ccrFemale": ccr(lambda y: female[y][k]),
        "childRatio": round(c_num / c_den, 5),
        "maleBirthShare": round(boys / c_num, 4),
    }
