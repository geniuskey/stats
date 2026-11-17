"""「나는 어디쯤?」 데이터 생성.

사용자가 입력한 나이·성별·연봉·가구소득·순자산이 각 통계 분포에서 어디쯤인지
브라우저에서 계산할 수 있도록, 분포를 '누적 비율 점(CDF)'으로 정리한다.

결합 데이터
  - 국세청 근로소득 연말정산 과세대상근로소득(총급여) 규모별 인원 (KOSIS 133 DT_13301N_A424)
  - 통계청 임금근로일자리 소득(보수) 구간별 분포: 연령대별·성별 (DT_1EP_2006, DT_1EP_2005)
  - 가계금융복지조사 순자산·가구소득 분위 경계값 (DT_1HDAAA21)
  - 가계금융복지조사 가구특성별 소득구간 가구분포 (DT_1HDAAB03)
  - 가계금융복지조사 가구주 연령별 순자산·경상소득 평균·중앙값 (DT_1HDAAA06)
  - 통계청 완전생명표 1세별 기대여명 (DT_1B42)

CDF 점은 [값, 누적비율] 목록이며, 마지막 점 위는 파레토 꼬리(alpha)로 잇는다.
"""
from __future__ import annotations

import math

import kosis


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def r(x, n=4):
    return None if x is None else round(x, n)


def pareto_alpha(x1, s1, x2, s2):
    """생존확률 s1=P(X>x1), s2=P(X>x2) 두 점으로 파레토 지수 추정."""
    if not (x2 > x1 > 0 and s1 > s2 > 0):
        return 2.0
    a = math.log(s1 / s2) / math.log(x2 / x1)
    return round(min(max(a, 1.1), 5.0), 3)


def cdf_from_bins(edges, shares):
    """edges: 구간 하한들(첫 값은 0), shares: 구간 비중(합 1). 마지막 구간은 열린 구간."""
    tot = sum(shares)
    pts, c = [[edges[0], 0.0]], 0.0
    for i in range(len(edges) - 1):
        c += shares[i] / tot
        pts.append([edges[i + 1], r(c)])
    # 꼬리: 마지막 두 경계의 생존확률
    s1 = 1 - pts[-2][1]
    s2 = 1 - pts[-1][1]
    alpha = pareto_alpha(pts[-2][0], s1, pts[-1][0], s2)
    return {"pts": pts, "alpha": alpha}


# ------------------------------------------------------------ 연봉 (국세청)

NTS_EDGES = {  # 구간 코드 접미 → 구간 하한(만원)
    "03": 0, "05": 1000, "07": 1500, "08": 2000, "09": 3000, "10": 4000, "101": 4500,
    "11": 5000, "12": 6000, "16": 8000, "17": 10000, "18": 20000, "19": 30000, "20": 50000, "21": 100000,
}


def salary_nts():
    rows = kosis.data("133", "DT_13301N_A424", itm="C", objs={1: "ALL", 2: "D05"}, newest=1)
    year = int(rows[0]["PRD_DE"])
    cnt: dict[int, float] = {}
    total = None
    for x in rows:
        c, v = x["C1"], num(x["DT"])
        if v is None:
            continue
        if c == "A01":
            total = v
            continue
        if c[:3] not in ("A02", "A03") or len(c) <= 3:
            continue
        suf = c[3:]
        if suf == "17" and c.startswith("A03"):  # 결정세액 없는 자 '1억 초과' → 1억 이상 구간으로
            lo = 10000
        else:
            lo = NTS_EDGES[suf]
        cnt[lo] = cnt.get(lo, 0) + v
    edges = sorted(cnt)
    d = cdf_from_bins(edges, [cnt[e] for e in edges])
    d.update({"year": year, "n": total})
    return d


# ------------------------------------------------------------ 월 보수 (일자리)

JOB_EDGES = {"10": 0, "20": 85, "30": 150, "40": 250, "50": 350, "60": 450, "70": 550, "80": 650, "90": 800, "100": 1000}
AGE_CODES = {"10": (15, 19), "20": (20, 24), "30": (25, 29), "40": (30, 34), "50": (35, 39), "60": (40, 44),
             "70": (45, 49), "80": (50, 54), "90": (55, 59), "100": (60, 64), "110": (65, 69), "7": (70, 120)}


def job_income():
    def group(tbl):
        rows = kosis.data("101", tbl, objs={1: "ALL", 2: "ALL"}, newest=1)
        year = int(rows[0]["PRD_DE"])
        by: dict[str, dict] = {}
        for x in rows:
            v = num(x["DT"])
            if v is None:
                continue
            by.setdefault(x["C2"], {})[x["C1"]] = v
        return year, by

    year, by_age = group("DT_1EP_2006")
    _, by_sex = group("DT_1EP_2005")

    def dist(d):
        edges = [JOB_EDGES[k] for k in JOB_EDGES]
        out = cdf_from_bins(edges, [d.get(k, 0) for k in JOB_EDGES])
        out["mean"] = r(d.get("110"), 1)
        out["median"] = r(d.get("120"), 1)
        return out

    ages = []
    for code, (lo, hi) in AGE_CODES.items():
        if code in by_age:
            ages.append({"lo": lo, "hi": hi, **dist(by_age[code])})
    sex = {}
    # 성별 코드: 총계(000)를 제외한 두 개를 이름으로 구분
    meta = {m["ITM_ID"]: m["ITM_NM"] for m in kosis.meta("101", "DT_1EP_2005") if m["OBJ_ID"] != "ITEM"}
    for code, d in by_sex.items():
        nm = meta.get(code, "")
        if "남" in nm:
            sex["male"] = dist(d)
        elif "여" in nm:
            sex["female"] = dist(d)
        else:
            sex["all"] = dist(d)
    return {"year": year, "ages": ages, "sex": sex}


# ------------------------------------------------------------ 가구 소득·순자산 (가계금융복지조사)

def household():
    rows = kosis.data("101", "DT_1HDAAA21", objs={1: "ALL"}, newest=1)
    year = int(rows[0]["PRD_DE"])
    q = {"T10": {}, "T20": {}}
    for x in rows:
        v = num(x["DT"])
        c = x["C1"]
        if v is None:
            continue
        q[x["ITM_ID"]][c] = v

    def deciles(d):
        pts = [[d[f"30{i}"], i / 10] for i in range(1, 10)]
        top_mean = d["105"]  # 5분위(상위 20%) 평균
        p80 = d["308"]
        # 상위 20% 평균과 P80으로 파레토 지수 (평균 = a/(a-1)·x_m)
        a = top_mean / (top_mean - p80) if top_mean > p80 else 2.0
        return {"pts": pts, "alpha": round(min(max(a, 1.1), 5.0), 3), "mean": r(d["10"], 0),
                "quintileMeans": [r(d[f"10{i}"], 0) for i in range(1, 6)]}

    net = deciles(q["T10"])
    inc = deciles(q["T20"])

    # 가구주 연령별 평균·중앙값
    rows = kosis.data("101", "DT_1HDAAA06", objs={1: "A0100", 2: "ALL", 3: "C08+C04"}, newest=1)
    AGE = {"B1601": (0, 29), "B1602": (30, 39), "B1603": (40, 49), "B1604": (50, 59), "B1605": (60, 120)}
    tmp: dict[str, dict] = {}
    for x in rows:
        if x["C2"] not in AGE:
            continue
        k = "net" if x["C3"] == "C08" else "inc"
        f = "mean" if x["ITM_ID"] == "T01" else "median"
        tmp.setdefault(x["C2"], {}).setdefault(k, {})[f] = r(num(x["DT"]), 0)
    by_age = [{"lo": AGE[c][0], "hi": AGE[c][1], **tmp[c]} for c in AGE if c in tmp]

    # 소득구간별 가구분포: 가구주 연령·가구원수
    rows = kosis.data("101", "DT_1HDAAB03", objs={1: "ALL", 2: "ALL"}, newest=1)
    EDG = {"10": 0, "20": 1000, "30": 3000, "40": 5000, "50": 7000, "60": 10000}
    grp: dict[str, dict] = {}
    for x in rows:
        v = num(x["DT"])
        if v is None or x["C2"] not in EDG:
            continue
        grp.setdefault(x["C1"], {})[x["C2"]] = v
    CH = {"021": ("age", 0, 29), "022": ("age", 30, 39), "023": ("age", 40, 49), "024": ("age", 50, 59), "025": ("age", 60, 120),
          "071": ("size", 1, 1), "072": ("size", 2, 2), "073": ("size", 3, 3), "074": ("size", 4, 4), "075": ("size", 5, 99)}
    # 1억 이상 꼬리: 구간이 넓어 하위 표에서 직접 추정하면 꼬리가 지나치게 두꺼워진다.
    # 전국 분위 경계값에서 1억 지점의 생존확률과 P90으로 구한 지수를 공통으로 쓴다.
    ip = inc["pts"]
    s_1e4 = None
    for (x0, p0), (x1, p1) in zip(ip, ip[1:]):
        if x0 <= 10000 <= x1:
            s_1e4 = 1 - (p0 + (p1 - p0) * (10000 - x0) / (x1 - x0))
    tail_alpha = pareto_alpha(10000, s_1e4, ip[-1][0], 0.1) if s_1e4 else inc["alpha"]
    inc_age, inc_size = [], []
    for c, (kind, lo, hi) in CH.items():
        if c not in grp:
            continue
        d = cdf_from_bins(list(EDG.values()), [grp[c].get(k, 0) for k in EDG])
        d["alpha"] = tail_alpha
        (inc_age if kind == "age" else inc_size).append({"lo": lo, "hi": hi, **d})
    return {"year": year, "incomeYear": year - 1, "net": net, "income": inc, "byAge": by_age,
            "incomeByAge": inc_age, "incomeBySize": inc_size}


# ------------------------------------------------------------ 기대여명

def life():
    m = kosis.meta("101", "DT_1B42")
    age_of = {}
    for x in m:
        if x["OBJ_ID"] == "C" and x["ITM_ID"] != "000":
            digits = "".join(ch for ch in x["ITM_NM"] if ch.isdigit())
            if digits:
                age_of[x["ITM_ID"]] = int(digits)
    rows = kosis.data("101", "DT_1B42", itm="T6+T16+T26", objs={1: "ALL"}, newest=1)
    year = int(rows[0]["PRD_DE"])
    sexmap = {"T6": "all", "T16": "male", "T26": "female"}
    t = {s: {} for s in sexmap.values()}
    for x in rows:
        a, v = age_of.get(x["C1"]), num(x["DT"])
        if a is not None and v is not None:
            t[sexmap[x["ITM_ID"]]][a] = v
    out = {"year": year}
    for s, d in t.items():
        out[s] = [r(d.get(a), 2) for a in range(0, 101)]
    return out


def build():
    return {
        "meta": {
            "sources": [
                "국세청 근로소득 연말정산 신고현황 — 과세대상근로소득(총급여) 규모별 인원 (KOSIS DT_13301N_A424)",
                "통계청 임금근로일자리 소득(보수) 결과 — 연령대별·성별 소득구간 분포 (KOSIS DT_1EP_2006, DT_1EP_2005)",
                "통계청·한국은행·금융감독원 가계금융복지조사 — 순자산·가구소득 분위 경계값 (KOSIS DT_1HDAAA21)",
                "가계금융복지조사 — 가구특성별 소득구간별 가구분포 (KOSIS DT_1HDAAB03)",
                "가계금융복지조사 — 가구주 연령계층별 자산·부채·소득 (KOSIS DT_1HDAAA06)",
                "통계청 완전생명표 1세별 기대여명 (KOSIS DT_1B42)",
                "행정안전부 주민등록인구·통계청 장래인구추계 (대한민국의 미래·우리 동네의 미래 데이터 재사용)",
            ],
        },
        "salary": salary_nts(),
        "job": job_income(),
        "household": household(),
        "life": life(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False)[:3000])
