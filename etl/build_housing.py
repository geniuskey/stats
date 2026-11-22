"""「집값을 감당할 수 있을까?」 데이터 생성.

결합 데이터
  - 한국부동산원 아파트 매매 실거래 평균가격 (만원/㎡, 시도·월) — KOSIS 408 DT_KAB_11672_S15
  - 한국부동산원 아파트 전세 실거래 평균가격 (만원/㎡, 시도·월) — KOSIS 408 DT_KAB_11672_S25
  - 통계청 가계금융복지조사 가구 평균 경상소득(전년도, 시도·연) — KOSIS 101 INH_1HD_AAA01_01
  - 한국은행 예금은행 주택담보대출 금리(신규취급액, 월) — KOSIS 301 DT_121Y006
  - 한국은행 차주당 가계대출 잔액(연령대별) — KOSIS 301 DT_181Y002

자체 지표
  - PIR: 전용 84㎡ 아파트 가격 / 가구 연소득
  - 주택구입 부담률: (84㎡ 가격 × LTV 50%)를 당시 주담대 금리·30년 원리금균등으로 갚을 때 월 상환액 / 월 소득
  - 1년치 소득으로 살 수 있는 면적(전용 평)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import kosis
from regions import SIDO

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "housing.json"

AREA = 84.0          # 국민평형(전용 84㎡)
AREA_SMALL = 59.0
LTV = 0.5
TERM_YEARS = 30
PYEONG = 3.3058
FIRST_YEAR = 2016    # 소득 자료(2017년 조사의 전년도 소득) 시작
OUTLOOK_YEARS = 4

PRICE_CODE = {
    "000": "00", "030": "11", "040": "26", "050": "27", "060": "28", "0307": "29", "080": "30",
    "090": "31", "091": "36", "100": "41", "110": "51", "120": "43", "130": "44", "140": "52",
    "0306": "46", "160": "47", "170": "48", "180": "50", "010": "capital", "020": "noncapital",
}
SEOUL_ZONES = {"0301": "도심권", "0302": "동북권", "0303": "동남권", "0304": "서북권", "0305": "서남권"}
INCOME_CODE = {
    "B0500": "00", "B0511": "11", "B0521": "26", "B0522": "27", "B0523": "28", "B0524": "29",
    "B0525": "30", "B0526": "31", "B0529": "36", "B0531": "41", "B0532": "51", "B0533": "43",
    "B0534": "44", "B0535": "52", "B0536": "46", "B0537": "47", "B0538": "48", "B0539": "50",
    "B0510": "capital", "B0520": "noncapital",
}
REGION_NAMES = {"00": ("전국", "전국"), "capital": ("수도권", "수도권"), "noncapital": ("비수도권", "비수도권")}
REGION_NAMES.update({k: v for k, v in SIDO.items()})
MORTGAGE = "13102134553ACC_ITEM.BECBLA0302"
LOAN_ITEMS = {
    "13102852635ACC_ITEM.0000": "전체", "13102852635ACC_ITEM.C001": "20대", "13102852635ACC_ITEM.C002": "30대",
    "13102852635ACC_ITEM.C003": "40대",
}


def payment(principal: float, annual_rate_pct: float, years: int = TERM_YEARS) -> float:
    """원리금균등 월 상환액."""
    n = years * 12
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / n
    return principal * r / (1 - (1 + r) ** -n)


def monthly(org, tbl, codes, *, start="200601", end):
    out: dict[str, dict[str, float]] = defaultdict(dict)
    objs = {1: "+".join(codes)}
    rows = kosis.data(org, tbl, objs=objs, prd_se="M", start=start, end=end)
    for r in rows:
        if r["DT"] in ("", "-", None):
            continue
        out[r["C1"]][r["PRD_DE"]] = float(r["DT"])
    return out


def ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    t = y * 12 + (m - 1) + k
    return f"{t // 12}{t % 12 + 1:02d}"


def trailing_mean(series: dict[str, float], end_ym: str, n: int = 12):
    vals = [series.get(ym_add(end_ym, -i)) for i in range(n)]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if len(vals) >= n * 0.75 else None


def r1(x, n=1):
    return None if x is None else round(x, n)


def build():
    today = datetime.now(timezone(timedelta(hours=9)))
    end_month, end_year = today.strftime("%Y%m"), today.strftime("%Y")
    price_m = monthly("408", "DT_KAB_11672_S15", list(PRICE_CODE) + list(SEOUL_ZONES), end=end_month)
    jeonse_m = monthly("408", "DT_KAB_11672_S25", list(PRICE_CODE) + list(SEOUL_ZONES), start="201401", end=end_month)
    rate_m = monthly("301", "DT_121Y006", [MORTGAGE], end=end_month)[MORTGAGE]
    last_price_ym = max(price_m["000"])
    last_rate_ym = max(rate_m)
    cur_year = int(last_price_ym[:4])
    outlook_end = cur_year + OUTLOOK_YEARS

    # 소득: 조사연도 Y의 '전년도 경상소득' → 소득연도 Y-1
    inc_rows = kosis.data("101", "INH_1HD_AAA01_01", objs={1: "ALL", 2: "C04"}, start="2017", end=end_year)
    income: dict[str, dict[int, float]] = defaultdict(dict)
    for r in inc_rows:
        k = INCOME_CODE.get(r["C1"])
        if k and r["DT"] not in ("", "-"):
            income[k][int(r["PRD_DE"]) - 1] = float(r["DT"])
    last_inc_year = max(income["00"])
    inc_growth = {}
    for k, s in income.items():
        y1 = last_inc_year
        y0 = y1 - 3
        g = (s[y1] / s[y0]) ** (1 / 3) - 1 if y0 in s else 0.03
        inc_growth[k] = g
        for y in range(y1 + 1, outlook_end + 1):  # 이후 연도는 최근 3년 연평균 증가율로 연장(추정)
            s[y] = s[y - 1] * (1 + g)

    # 대출 잔액
    loan_rows = kosis.data("301", "DT_181Y002", objs={1: "+".join(LOAN_ITEMS)}, start="2013", end=end_year)
    loans = defaultdict(dict)
    for r in loan_rows:
        if r["DT"] not in ("", "-"):
            v = float(r["DT"]) * (10 if r.get("UNIT_NM") == "십만원" else 1)
            loans[LOAN_ITEMS[r["C1"]]][int(r["PRD_DE"])] = round(v)
    loan_unit = "만원"

    years = list(range(FIRST_YEAR, cur_year + 1))

    def year_end_ym(y):
        return last_price_ym if y == cur_year else f"{y}12"

    rate_y = {}
    for y in years:
        end = last_rate_ym if y == cur_year else f"{y}12"
        rate_y[y] = trailing_mean(rate_m, end)

    def metrics(p_m2, inc, rate):
        if p_m2 is None or inc is None or rate is None:
            return None
        price = p_m2 * AREA
        pay = payment(price * LTV, rate)
        return {
            "priceM2": r1(p_m2), "price84": round(price), "income": round(inc), "rate": r1(rate, 2),
            "pir": r1(price / inc), "payment": round(pay, 1), "burden": r1(pay / (inc / 12) * 100),
            "pyeong": r1(inc / p_m2 / PYEONG),
        }

    regions = []
    for code, k in PRICE_CODE.items():
        if k not in income:
            continue
        hist = {}
        for y in years:
            p = trailing_mean(price_m[code], year_end_ym(y))
            m = metrics(p, income[k].get(y), rate_y[y])
            if m:
                j = trailing_mean(jeonse_m.get(code, {}), year_end_ym(y)) if y >= 2014 else None
                m["jeonseRatio"] = r1(j / p * 100) if j and p else None
                hist[y] = m
        if not hist:
            continue
        cur = hist[max(hist)]
        first = hist[min(hist)]
        p_now = cur["priceM2"]
        # 가격 추세: 화면의 비교 시작 연도부터 최근 실측까지의 연평균 상승률
        y_first = min(hist)
        span = max(hist) - y_first
        price_cagr = (p_now / first["priceM2"]) ** (1 / span) - 1 if span > 0 else 0.0
        sens = {}
        for d in (-1, 0, 1):
            rr = cur["rate"] + d
            sens[str(d)] = r1(payment(p_now * AREA * LTV, rr) / (cur["income"] / 12) * 100)
        # 전망: 가격 3 × 금리 3
        price_scen = {"down": -0.02, "flat": 0.0, "trend": price_cagr}
        rate_scen = {"cut": -1.0, "hold": 0.0, "hike": 1.0}
        outlook = {}
        for ps, g in price_scen.items():
            outlook[ps] = {}
            for rs, dr in rate_scen.items():
                row = {}
                for i, y in enumerate(range(cur_year + 1, outlook_end + 1), start=1):
                    frac = min(i / 2, 1.0)  # 금리는 2년에 걸쳐 목표 수준으로 이동
                    rate = cur["rate"] + dr * frac
                    p = p_now * (1 + g) ** i
                    inc = income[k][y]
                    pay = payment(p * AREA * LTV, rate)
                    row[y] = {"burden": r1(pay / (inc / 12) * 100), "pir": r1(p * AREA / inc)}
                outlook[ps][rs] = row
        name_short, name_full = REGION_NAMES[k]
        regions.append({
            "id": k, "name": name_short, "fullName": name_full,
            "level": "nation" if k == "00" else ("group" if k in ("capital", "noncapital") else "sido"),
            "hist": hist, "current": cur, "sensitivity": sens,
            "priceCagr": round(price_cagr, 4), "incomeGrowth": round(inc_growth[k], 4),
            "change": {
                "pir": r1(cur["pir"] - first["pir"]),
                "burden": r1(cur["burden"] - first["burden"]),
                "fromYear": y_first,
            },
            "outlook": outlook,
            "monthly": {
                ym: r1(trailing_mean(price_m[code], ym))
                for ym in sorted(price_m[code]) if ym >= "200712" or ym == last_price_ym
            },
        })

    sido = [r for r in regions if r["level"] == "sido"]
    for key in ("burden", "pir"):
        for i, r in enumerate(sorted(sido, key=lambda r: -r["current"][key]), start=1):
            r.setdefault("rank", {})[key] = i

    zones = []
    seoul_inc = income["11"]
    for code, nm in SEOUL_ZONES.items():
        p = trailing_mean(price_m.get(code, {}), last_price_ym)
        m = metrics(p, seoul_inc.get(cur_year), rate_y[cur_year])
        if m:
            zones.append({"id": code, "name": nm, **m})

    nat = next(r for r in regions if r["id"] == "00")
    return {
        "meta": {
            "lastPriceMonth": f"{last_price_ym[:4]}.{last_price_ym[4:]}",
            "lastRateMonth": f"{last_rate_ym[:4]}.{last_rate_ym[4:]}",
            "lastIncomeYear": last_inc_year,
            "currentYear": cur_year,
            "assumptions": {"area": AREA, "areaSmall": AREA_SMALL, "ltv": LTV, "termYears": TERM_YEARS, "pyeong": PYEONG},
            "units": {"priceM2": "만원/㎡", "price84": "만원", "income": "만원/년", "rate": "연%", "payment": "만원/월",
                      "burden": "% (월상환액/월소득)", "pir": "년", "pyeong": "전용 평"},
            "notes": [
                "연도 값은 해당 연도 1~12월 평균(최근 연도는 최근 12개월 평균)입니다.",
                f"가구소득은 가계금융복지조사의 '전년도 경상소득'으로, {last_inc_year}년 이후는 지역별 최근 3년 연평균 증가율로 연장한 추정치입니다.",
                "금리는 전국 예금은행 주택담보대출 신규취급액 가중평균금리이며 모든 지역에 동일하게 적용합니다.",
                "실거래 평균가격은 거래 구성(입지·면적)에 따라 월별 변동이 커 12개월 평균을 사용합니다.",
            ],
            "sources": [
                "한국부동산원 아파트 매매 실거래 평균가격 (KOSIS DT_KAB_11672_S15)",
                "한국부동산원 아파트 전세 실거래 평균가격 (KOSIS DT_KAB_11672_S25)",
                "통계청·한국은행·금융감독원 가계금융복지조사 가구소득(지역별) (KOSIS INH_1HD_AAA01_01)",
                "한국은행 예금은행 대출금리(신규취급액 기준) 주택담보대출 (KOSIS DT_121Y006)",
                "한국은행 차주당 가계대출 잔액 (KOSIS DT_181Y002)",
            ],
        },
        "rate": {
            "monthly": {ym: v for ym, v in sorted(rate_m.items()) if ym >= "200601"},
            "annual": {y: r1(v, 2) for y, v in rate_y.items()},
        },
        "loans": {"unit": loan_unit, "byAge": loans},
        "calculator": {
            "rateNow": nat["current"]["rate"],
            "regions": [{"id": r["id"], "name": r["name"], "priceM2": r["current"]["priceM2"],
                         "jeonseRatio": r["current"].get("jeonseRatio"), "income": r["current"]["income"]}
                        for r in regions],
            "seoulZones": [{"id": z["id"], "name": z["name"], "priceM2": z["priceM2"]} for z in zones],
        },
        "regions": regions,
        "seoulZones": zones,
    }


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB)")
    if "-q" not in sys.argv:
        for r in data["regions"]:
            c = r["current"]
            print(f"{r['name']:6} PIR {c['pir']:5} 부담 {c['burden']:5}% 평 {c['pyeong']:5} 전세가율 {c.get('jeonseRatio')} "
                  f"Δ부담 {r['change']['burden']:+} 가격CAGR {r['priceCagr']:.3f} ±1%p {r['sensitivity']}")
