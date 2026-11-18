"""「올해 아기는 몇 명 태어날까?」 출생아·합계출산율 나우캐스트.

결합 데이터
  - 월별 출생아 수·혼인 건수·합계출산율 (통계청 인구동향조사, KOSIS DT_1B8000G, 전국·시도)
  - 연간 출생아 수·혼인 건수·합계출산율 (같은 표, 연 단위 확정치)

핵심 식
  1) 올해 출생아 = 올해 1~M월 누계 + 남은 달 추정
       계절법: 누계 ÷ (최근 5년 1~M월 누계가 연간에서 차지한 비중의 평균)
       추세법: 누계 + 작년 남은 달 출생아 × (최근 3개월 전년 동월 대비 증가율)
     두 방법을 1995~작년까지 '그해 M월까지만 알았다면' 조건으로 다시 계산해 오차가 작은 쪽을 쓰고,
     같은 백테스트 오차 분포(10~90%)로 범위를 붙인다.
  2) 올해 합계출산율 = 올해 출생아 ÷ (출생아/합계출산율 비율: 가임 여성 규모를 나타내는 분모, 최근 추세로 연장)
  3) 내년 출생아 = 올해 출생아 × exp(a + b·올해 혼인 증가율 + c·작년 혼인 증가율)
     (혼인 후 첫째 출산까지 1~2년 시차, 1996~작년 연간 자료로 최소제곱 추정)

나우캐스트 기록(log): ETL을 돌릴 때마다 '몇 월 자료 기준으로 올해를 얼마로 봤는지'를 쌓아 두고,
연간 확정치가 나오면 오차를 계산한다 → 예측 성적표에서 공개.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import kosis
from regions import SIDO, stat_sido

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "src" / "data" / "births.json"
TBL = "DT_1B8000G"
ITEM = {"10": "births", "20": "marriages", "12": "tfr"}
BT_FROM = 1995       # 백테스트 시작 연도
SEASON_YEARS = 5     # 계절 비중 평균 기간
GROWTH_MONTHS = 3    # 추세법 증가율 기간


def region_key(code: str) -> str | None:
    if code == "00":
        return "00"
    if code == "12":  # 전남광주통합특별시(2026~) 합계 — 광주·전남은 24·36 코드로 따로 나온다
        return None
    return stat_sido(code)


def fetch():
    """→ monthly[region][item][(y, m)], annual[region][item][y]"""
    monthly = defaultdict(lambda: defaultdict(dict))
    annual = defaultdict(lambda: defaultdict(dict))
    for itm in ITEM:
        rows = kosis.data("101", TBL, itm="T1", objs={1: "ALL", 2: itm}, prd_se="M", start="199001", end="209912")
        for r in rows:
            k = region_key(r["C1"])
            if k is None or r["DT"] in ("", "-", None):
                continue
            p = r["PRD_DE"]
            monthly[k][ITEM[itm]][(int(p[:4]), int(p[4:6]))] = float(r["DT"])
        rows = kosis.data("101", TBL, itm="T1", objs={1: "ALL", 2: itm}, prd_se="Y", start="1981", end="2099")
        for r in rows:
            k = region_key(r["C1"])
            if k is None or r["DT"] in ("", "-", None):
                continue
            annual[k][ITEM[itm]][int(r["PRD_DE"])] = float(r["DT"])
    return monthly, annual


def complete_years(mon: dict) -> list[int]:
    ys = defaultdict(int)
    for (y, _m) in mon:
        ys[y] += 1
    return sorted(y for y, n in ys.items() if n == 12)


def latest_month(mon: dict) -> tuple[int, int]:
    return max(mon)


# ── 올해 연간 추정 ──────────────────────────────────────────
def est_season(mon, y, M):
    """누계 ÷ 최근 5년 1~M월 비중 평균."""
    shares = []
    for py in range(y - SEASON_YEARS, y):
        tot = sum(mon.get((py, m), math.nan) for m in range(1, 13))
        part = sum(mon.get((py, m), math.nan) for m in range(1, M + 1))
        if math.isfinite(tot) and tot > 0:
            shares.append(part / tot)
    if not shares:
        return None
    ytd = sum(mon[(y, m)] for m in range(1, M + 1))
    return ytd / (sum(shares) / len(shares))


def est_trend(mon, y, M):
    """누계 + 작년 남은 달 × 최근 3개월 전년 동월 대비 비율."""
    ms = range(max(1, M - GROWTH_MONTHS + 1), M + 1)
    cur = sum(mon[(y, m)] for m in ms)
    prev = sum(mon.get((y - 1, m), math.nan) for m in ms)
    rest = sum(mon.get((y - 1, m), math.nan) for m in range(M + 1, 13))
    if not (math.isfinite(prev) and math.isfinite(rest)) or prev <= 0:
        return None
    ytd = sum(mon[(y, m)] for m in range(1, M + 1))
    return ytd + rest * cur / prev


METHODS = {"season": est_season, "trend": est_trend}


def quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    i = (len(s) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def backtest_annual(mon, ann, years):
    """{M: {method: [(year, err), ...]}}; err = 예측/확정 − 1."""
    out = {M: {k: [] for k in METHODS} for M in range(1, 12)}
    for y in years:
        if y < BT_FROM or y not in ann:
            continue
        for M in range(1, 12):
            for name, f in METHODS.items():
                p = f(mon, y, M)
                if p is not None:
                    out[M][name].append((y, p / ann[y] - 1))
    return out


def pick(bt_M):
    """최근 15년 평균 절대오차가 작은 방법."""
    best, best_e = None, None
    for name, errs in bt_M.items():
        rec = [abs(e) for y, e in errs][-15:]
        if not rec:
            continue
        e = sum(rec) / len(rec)
        if best_e is None or e < best_e:
            best, best_e = name, e
    return best


def nowcast(mon, ann, y, M, bt):
    method = pick(bt[M])
    point = METHODS[method](mon, y, M)
    errs = [e for _, e in bt[M][method]][-20:]
    lo, hi = quantile(errs, 0.1), quantile(errs, 0.9)
    mae = sum(abs(e) for e in errs) / len(errs)
    return {
        "method": method,
        "point": point,
        "lo": point / (1 + hi),   # 과거에 과대추정(+)했던 만큼 아래로
        "hi": point / (1 + lo),
        "mae": mae,
    }


# ── 합계출산율 ─────────────────────────────────────────────
def tfr_denominator(ann_b, ann_t):
    return {y: ann_b[y] / ann_t[y] for y in ann_b if y in ann_t and ann_t[y] > 0}


def est_den(den, y):
    """분모(y) = 분모(y−1) × 최근 3년 평균 변화율."""
    ys = [t for t in range(y - 4, y) if t in den]
    if len(ys) < 2:
        return None
    rates = [den[b] / den[a] for a, b in zip(ys, ys[1:])]
    return den[y - 1] * (sum(rates) / len(rates)) if y - 1 in den else None


# ── 내년 출생아 (혼인 시차 회귀) ───────────────────────────
def ols(X, Y):
    """작은 최소제곱 (정규방정식, 가우스 소거)."""
    n = len(X[0])
    A = [[sum(x[i] * x[j] for x in X) for j in range(n)] for i in range(n)]
    b = [sum(x[i] * yv for x, yv in zip(X, Y)) for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        for r in range(i + 1, n):
            f = A[r][i] / A[i][i]
            for c in range(i, n):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (b[i] - sum(A[i][c] * x[c] for c in range(i + 1, n))) / A[i][i]
    return x


def lag_rows(B, Mr, years):
    rows = []
    for y in years:
        if all(t in B for t in (y, y - 1)) and all(t in Mr for t in (y - 1, y - 2, y - 3)):
            gB = math.log(B[y] / B[y - 1])
            rows.append((y, [1.0, math.log(Mr[y - 1] / Mr[y - 2]), math.log(Mr[y - 2] / Mr[y - 3])], gB))
    return rows


def fit_lag(B, Mr, upto):
    rows = [r for r in lag_rows(B, Mr, range(1996, upto + 1))]
    coef = ols([x for _, x, _ in rows], [g for _, _, g in rows])
    return coef, rows


def backtest_lag(B, Mr, last):
    """y년 출생을 (y−1)년까지 자료로 적합한 모형으로 예측 — 진짜 1년 앞 예측 오차."""
    errs = []
    for y in range(2008, last + 1):
        coef, _ = fit_lag(B, Mr, y - 1)
        rows = lag_rows(B, Mr, [y])
        if not rows:
            continue
        _, x, _ = rows[0]
        pred = B[y - 1] * math.exp(sum(c * v for c, v in zip(coef, x)))
        naive = B[y - 1]
        errs.append({"year": y, "pred": round(pred), "actual": round(B[y]), "err": round(pred / B[y] - 1, 4),
                     "naiveErr": round(naive / B[y] - 1, 4)})
    return errs


def rnd(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def load_log() -> list[dict]:
    try:
        return json.loads(OUT_FILE.read_text()).get("log", [])
    except (OSError, ValueError):
        return []


def build():
    monthly, annual = fetch()
    nat_m, nat_a = monthly["00"], annual["00"]
    mb, mm = nat_m["births"], nat_m["marriages"]
    ab, am, at = nat_a["births"], nat_a["marriages"], nat_a["tfr"]
    ly, lm = latest_month(mb)                  # 최신 월 (예: 2026, 8)
    last_annual = max(ab)                      # 확정 연간 (예: 2025)
    year = ly if lm < 12 else ly + 1
    if lm == 12 and year - 1 not in ab:        # 12월까지 나왔지만 연간 확정 전
        year = ly
    full = complete_years(mb)

    bt_b = backtest_annual(mb, ab, full)
    bt_m = backtest_annual(mm, am, complete_years(mm))
    M = lm if year == ly else 12

    if M < 12:
        nb = nowcast(mb, ab, year, M, bt_b)
        nm = nowcast(mm, am, year, M, bt_m)
    else:  # 12월까지 다 나왔으면 합계가 곧 연간
        s = sum(mb[(year, m)] for m in range(1, 13))
        nb = {"method": "sum", "point": s, "lo": s, "hi": s, "mae": 0}
        s = sum(mm[(year, m)] for m in range(1, 13))
        nm = {"method": "sum", "point": s, "lo": s, "hi": s, "mae": 0}

    # 합계출산율
    den = tfr_denominator(ab, at)
    d_now = est_den(den, year)
    tfr_now = {k: nb[k] / d_now for k in ("point", "lo", "hi")} if d_now else None
    tfr_bt = []
    for y in range(2005, last_annual + 1):
        d = est_den(den, y)
        if d and y in at:
            tfr_bt.append(round((ab[y] / d) / at[y] - 1, 4))  # 출생아를 정확히 알 때 분모 추정 오차

    # 내년 출생아
    Bx = {**ab, year: nb["point"]}
    Mx = {**am, year: nm["point"]}
    coef, rows = fit_lag(ab, am, last_annual)
    x_next = [1.0, math.log(Mx[year] / Mx[year - 1]), math.log(Mx[year - 1] / Mx[year - 2])]
    g_next = sum(c * v for c, v in zip(coef, x_next))
    lag_bt = backtest_lag(ab, am, last_annual)
    lag_errs = [e["err"] for e in lag_bt]
    nxt = Bx[year] * math.exp(g_next)
    # 범위: 올해 추정 범위 × 1년 앞 예측 오차(10~90%)
    lo_e, hi_e = quantile(lag_errs, 0.1), quantile(lag_errs, 0.9)
    next_births = {"point": nxt, "lo": nb["lo"] * math.exp(g_next) / (1 + hi_e), "hi": nb["hi"] * math.exp(g_next) / (1 + lo_e)}
    resid = [g - sum(c * v for c, v in zip(coef, x)) for _, x, g in rows]

    # 백테스트 요약 (선택된 방법 기준, 최근 20년)
    def bt_summary(bt):
        out = {}
        for Mi in range(1, 12):
            meth = pick(bt[Mi])
            errs = [e for _, e in bt[Mi][meth]][-20:]
            out[Mi] = {"method": meth, "mae": round(sum(abs(e) for e in errs) / len(errs), 4),
                       "max": round(max(abs(e) for e in errs), 4), "n": len(errs)}
        return out

    bt_detail = {  # 현재 기준 월 M에서 과거 연도별 오차 (차트용)
        str(y): round(e, 4) for y, e in bt_b[min(M, 11)][pick(bt_b[min(M, 11)])]
    } if M < 12 else {}

    # 월별 차트 데이터 (최근 5년 + 올해)
    def months(series, y):
        return [series.get((y, m)) for m in range(1, 13)]

    # 키가 해마다 사라지지 않도록 2015년부터 모두 싣는다 (validate.py는 사라진 키를 오류로 본다)
    recent = {str(y): [rnd(v) for v in months(mb, y)] for y in range(2015, year + 1)}
    recent_m = {str(y): [rnd(v) for v in months(mm, y)] for y in range(2015, year + 1)}
    # 올해 남은 달 추정 (계절 비중으로 분배)
    rest_months = list(range(M + 1, 13))
    fc_months = {}
    if rest_months:
        prev_rest = sum(mb[(year - 1, m)] for m in rest_months)
        ytd = sum(mb[(year, m)] for m in range(1, M + 1))
        rest_total = nb["point"] - ytd
        for m in rest_months:
            fc_months[m] = rnd(rest_total * mb[(year - 1, m)] / prev_rest)

    # 시도
    sidos = []
    for sd in SIDO:
        sm = monthly.get(sd, {})
        sb, sa = sm.get("births", {}), annual.get(sd, {}).get("births", {})
        if (year, M) not in sb and M < 12:
            continue
        ytd = sum(sb[(year, m)] for m in range(1, M + 1))
        ytd_prev = sum(sb.get((year - 1, m), 0) for m in range(1, M + 1))
        est = (METHODS[nb["method"]](sb, year, M) if nb["method"] in METHODS else est_season(sb, year, M)) if M < 12 else ytd
        sidos.append({
            "id": sd, "name": SIDO[sd][0],
            "ytd": rnd(ytd), "ytdPrev": rnd(ytd_prev),
            "ytdChange": round(ytd / ytd_prev - 1, 4) if ytd_prev else None,
            "est": rnd(est), "prevYear": rnd(sa.get(year - 1)),
            "estChange": round(est / sa[year - 1] - 1, 4) if est and sa.get(year - 1) else None,
            "tfrPrev": annual.get(sd, {}).get("tfr", {}).get(year - 1),
            "hist": {str(y): rnd(v) for y, v in sorted(sa.items()) if y >= 2000},
        })

    asof = f"{ly}-{lm:02d}"
    log = load_log()
    entry = {"key": asof, "asof": asof, "year": year, "births": rnd(nb["point"]), "lo": rnd(nb["lo"]), "hi": rnd(nb["hi"]),
             "tfr": rnd(tfr_now["point"], 3) if tfr_now else None, "nextYear": year + 1, "next": rnd(next_births["point"])}
    log = [{**e, "key": e["asof"]} for e in log if e.get("asof") != asof] + [entry]
    log.sort(key=lambda e: e["asof"])
    for e in log:  # 확정치가 나온 기록은 오차 계산
        if e["year"] in ab:
            e["actual"] = rnd(ab[e["year"]])
            e["err"] = round(e["births"] / ab[e["year"]] - 1, 4)
            if e.get("tfr") and e["year"] in at:
                e["tfrActual"] = at[e["year"]]
        if e.get("nextYear") in ab:
            e["nextActual"] = rnd(ab[e["nextYear"]])
            e["nextErr"] = round(e["next"] / ab[e["nextYear"]] - 1, 4)

    # 과거 '그해 M월 기준' 의사 실시간 기록 (성적표용): 최근 10년
    pseudo = []
    if M < 12:
        meth = pick(bt_b[M])
        for y, e in bt_b[M][meth]:
            if y < 2006:
                continue
            pseudo.append({"year": y, "pred": rnd(ab[y] * (1 + e)), "actual": rnd(ab[y]), "err": round(e, 4)})

    return {
        "meta": {
            "asof": asof, "year": year, "month": M, "lastAnnual": last_annual,
            "sources": [
                "통계청 인구동향조사 월·분기·연간 출생·사망·혼인·이혼 (KOSIS DT_1B8000G)",
            ],
        },
        "headline": {
            "births": rnd(nb["point"]), "lo": rnd(nb["lo"]), "hi": rnd(nb["hi"]),
            "prev": rnd(ab.get(year - 1)), "change": round(nb["point"] / ab[year - 1] - 1, 4) if ab.get(year - 1) else None,
            "tfr": rnd(tfr_now["point"], 3) if tfr_now else None,
            "tfrLo": rnd(tfr_now["lo"], 3) if tfr_now else None,
            "tfrHi": rnd(tfr_now["hi"], 3) if tfr_now else None,
            "tfrPrev": at.get(year - 1),
            "marriages": rnd(nm["point"]), "marriagesPrev": rnd(am.get(year - 1)),
            "marriagesChange": round(nm["point"] / am[year - 1] - 1, 4) if am.get(year - 1) else None,
            "next": rnd(next_births["point"]), "nextLo": rnd(next_births["lo"]), "nextHi": rnd(next_births["hi"]),
            "nextChange": round(next_births["point"] / nb["point"] - 1, 4),
            "ytd": rnd(sum(mb[(year, m)] for m in range(1, M + 1))),
            "ytdPrev": rnd(sum(mb[(year - 1, m)] for m in range(1, M + 1))),
            "method": nb["method"], "mae": round(nb["mae"], 4),
        },
        "monthly": {"births": recent, "marriages": recent_m, "forecast": {str(m): v for m, v in fc_months.items()}},
        "annual": {
            "births": {str(y): rnd(v) for y, v in sorted(ab.items())},
            "marriages": {str(y): rnd(v) for y, v in sorted(am.items())},
            "tfr": {str(y): v for y, v in sorted(at.items())},
        },
        "model": {
            "lagCoef": [round(c, 4) for c in coef],
            "lagResidSd": round((sum(r * r for r in resid) / max(1, len(resid) - 3)) ** 0.5, 4),
            "tfrDenErrMae": round(sum(abs(e) for e in tfr_bt) / len(tfr_bt), 4) if tfr_bt else None,
        },
        "backtest": {
            "byMonth": bt_summary(bt_b),
            "detail": bt_detail,
            "pseudo": pseudo,
            "lag": lag_bt,
            "lagMae": round(sum(abs(e) for e in lag_errs) / len(lag_errs), 4),
            "naiveMae": round(sum(abs(e["naiveErr"]) for e in lag_bt) / len(lag_bt), 4),
        },
        "sidos": sidos,
        "log": log,
    }


if __name__ == "__main__":
    import pprint
    d = build()
    pprint.pprint({k: d[k] for k in ("meta", "headline", "model")})
    pprint.pprint(d["backtest"]["byMonth"])
    print(d["backtest"]["lagMae"], d["backtest"]["naiveMae"])
    pprint.pprint(d["sidos"][:3])
