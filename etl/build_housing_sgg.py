"""「집값을 감당할 수 있을까?」 시군구 확장 — 국토부 아파트 실거래가(매매·전월세) 결합.

입력
  - data/molit/{trade,rent}/YYYYMM.csv.gz : etl/molit/collect.py export 결과 (git 제외, 로컬에서만 있음)
  - src/data/housing.json : 시도 가구소득·주담대 금리·가정(LTV·기간) — build_housing이 먼저 돌아야 한다
  - src/data/dongne.json  : 시군구 이름·시도 (지도 id 229개)

자체 지표 (최근 12개월, 신고 기한 30일이 지난 달까지)
  - 84㎡ 가격: 전용 40~135㎡ 중개거래(해제·직거래 제외)의 ㎡당 가격 중앙값 × 84
  - PIR·주택구입 부담률: 시도 가구소득과 현재 금리로 build_housing과 같은 방식
  - 전세가율: 같은 단지(aptSeq) 안에서 전세(월세 0) ㎡당 보증금 중앙값 ÷ 매매 ㎡당 가격 중앙값을 구하고,
    지역 값은 단지별 비율의 중앙값(단지 10곳 이상). 매매 단지와 전세 단지가 달라 생기는 왜곡을 막는다
  - 재계약 보증금 인상률: 갱신 계약 중 종전·이번 모두 전세인 계약의 (보증금 ÷ 종전 보증금 − 1) 중앙값,
    5% 넘게 올린 비율, 내린 비율
  - 갱신요구권 사용 비율, 월세 비중(보증부 월세 포함), 거래량 변화(직전 12개월 대비)

원자료가 없으면(CI 등) None을 돌려 기존 결과를 그대로 둔다.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from regions import GWANGJU_GU

ROOT = Path(__file__).resolve().parent.parent
MOLIT = ROOT / "data" / "molit"
SRC = ROOT / "src" / "data"

AREA_MIN, AREA_MAX = 40.0, 135.0
MIN_N = 20            # 지역 지표를 내기 위한 최소 표본
MIN_COMPLEX = 10      # 전세가율을 내기 위한 최소 단지 수
REPORT_DAYS = 30      # 계약 후 신고 기한
INCHEON_DONGGU = {"만석동", "화수동", "송현동", "송림동", "금곡동", "창영동"}  # 옛 동구 → 2026 제물포구


def num(s: str) -> float | None:
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f"{y + m // 12:04d}{m % 12 + 1:02d}"


def month_end(ym: str) -> date:
    y, m = int(ym[:4]), int(ym[4:])
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def payment(principal: float, annual_rate_pct: float, years: int) -> float:
    n, r = years * 12, annual_rate_pct / 100 / 12
    return principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)


def region_mapper(regions: list[dict]):
    """국토부 현재 시군구 코드(+법정동) → 사이트 지도 id(2025-12 경계, 일반구는 시로 합침)."""
    ids = {r["id"] for r in regions}
    by_name = {(r["sidoCode"], r["name"]): r["id"] for r in regions}
    lawd = {c["code"]: c["name"] for c in json.loads((ROOT / "etl" / "molit" / "lawd.json").read_text())["codes"]}

    def f(code: str, umd: str) -> str | None:
        if code in ids:
            return code
        if code[:2] == "12":  # 2026-07 전남광주 통합 → 옛 광주(29)·전남(46)
            name = lawd.get(code, "")
            return by_name.get(("29" if name in GWANGJU_GU else "46", name))
        if code == "28125":  # 제물포구 = 옛 중구 내륙 + 옛 동구
            return "28140" if umd in INCHEON_DONGGU else "28110"
        if code == "28155":  # 영종구 = 옛 중구 영종도
            return "28110"
        if code in ("28275", "28290"):  # 서해구·검단구 = 옛 서구
            return "28260"
        alt = code[:4] + "0"  # 일반구 → 시 (41111 → 41110)
        return alt if alt in ids else None
    return f


def read(kind: str, ym: str):
    p = MOLIT / kind / f"{ym}.csv.gz"
    if not p.exists():
        return []
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build():
    mf = MOLIT / "trade" / "manifest.json"
    if not mf.exists() or not (MOLIT / "rent" / "manifest.json").exists():
        print("  data/molit 없음 → 건너뜀 (기존 housing_sgg.json 유지)")
        return None
    tm = json.loads(mf.read_text())["months"]
    rm = json.loads((MOLIT / "rent" / "manifest.json").read_text())["months"]
    fetched = date.fromisoformat(min(max(v["fetched"]) for v in list(tm.values()) + list(rm.values())))
    complete = sorted(ym for ym in tm if tm[ym]["complete"] and ym in rm and rm[ym]["complete"])
    # 신고 기한이 지난 마지막 달
    last = max(ym for ym in complete if month_end(ym) + timedelta(days=REPORT_DAYS) <= fetched)
    win = [ym_add(last, -k) for k in range(12)][::-1]
    prev = [ym_add(last, -k) for k in range(12, 24)][::-1]
    if any(ym not in complete for ym in win + prev):
        raise SystemExit(f"수집이 덜 됐습니다: {[ym for ym in win + prev if ym not in complete]}")

    H = json.loads((SRC / "housing.json").read_text())
    A = H["meta"]["assumptions"]
    area, ltv, term = A["area"], A["ltv"], A["termYears"]
    hreg = {r["id"]: r for r in H["regions"]}
    rate = hreg["00"]["current"]["rate"]
    regions = json.loads((SRC / "dongne.json").read_text())["regions"]
    to_id = region_mapper(regions)

    # 지역별 표본 모으기
    price = defaultdict(list)      # 매매 ㎡당 (만원) — 최근 12개월
    vol = defaultdict(lambda: [0, 0])  # [최근, 직전] 거래 건수(해제 제외, 직거래 포함)
    sale_c = defaultdict(lambda: defaultdict(list))    # 지역 → 단지 → 매매 ㎡당
    jeonse_c = defaultdict(lambda: defaultdict(list))  # 지역 → 단지 → 전세 ㎡당 보증금
    renew = defaultdict(list)      # 재계약 전세 보증금 비율
    rr = defaultdict(lambda: [0, 0])     # [갱신요구권 사용, 갱신 계약]
    wolse = defaultdict(lambda: [0, 0])  # [월세, 전체 전월세]
    unmapped = defaultdict(int)
    nat_month = {}
    months_all = sorted(set(tm) & set(rm))

    for ym in months_all:
        in_win, in_prev = ym in win, ym in prev
        m_trades = 0
        m_renew: list[float] = []
        m_rr = [0, 0]
        m_wolse = [0, 0]
        for t in read("trade", ym):
            if t.get("cdealType") == "O":
                continue
            m_trades += 1
            if not (in_win or in_prev):
                continue
            rid = to_id(t["_lawd"], t.get("umdNm", ""))
            if rid is None:
                unmapped[t["_lawd"]] += 1
                continue
            vol[rid][0 if in_win else 1] += 1
            if in_win and t.get("dealingGbn") != "직거래":
                a, p = num(t.get("excluUseAr")), num(t.get("dealAmount"))
                if a and p and AREA_MIN <= a <= AREA_MAX:
                    price[rid].append(p / a)
                    if t.get("aptSeq"):
                        sale_c[rid][t["aptSeq"]].append(p / a)
        for r in read("rent", ym):
            dep, mon = num(r.get("deposit")), num(r.get("monthlyRent"))
            if dep is None or mon is None:
                continue
            is_jeonse = mon == 0
            m_wolse[0] += not is_jeonse
            m_wolse[1] += 1
            ratio = None
            if r.get("contractType") == "갱신":
                m_rr[1] += 1
                m_rr[0] += r.get("useRRRight") == "사용"
                pd, pm = num(r.get("preDeposit")), num(r.get("preMonthlyRent")) or 0.0  # 종전 전세는 월세가 빈칸
                if is_jeonse and pd and pd > 0 and pm == 0:
                    ratio = dep / pd
                    m_renew.append(ratio - 1)
            if not in_win:
                continue
            rid = to_id(r["_lawd"], r.get("umdNm", ""))
            if rid is None:
                unmapped[r["_lawd"]] += 1
                continue
            wolse[rid][0] += not is_jeonse
            wolse[rid][1] += 1
            if r.get("contractType") == "갱신":
                rr[rid][1] += 1
                rr[rid][0] += r.get("useRRRight") == "사용"
            if ratio is not None:
                renew[rid].append(ratio - 1)
            a = num(r.get("excluUseAr"))
            if is_jeonse and a and AREA_MIN <= a <= AREA_MAX and dep > 0 and r.get("aptSeq"):
                jeonse_c[rid][r["aptSeq"]].append(dep / a)
        nat_month[ym] = {
            "trades": m_trades,
            "renewUp": round(median(m_renew), 4) if len(m_renew) >= MIN_N else None,
            "renewDown": round(sum(x < -1e-9 for x in m_renew) / len(m_renew), 4) if len(m_renew) >= MIN_N else None,
            "rrShare": round(m_rr[0] / m_rr[1], 4) if m_rr[1] else None,
            "wolseShare": round(m_wolse[0] / m_wolse[1], 4) if m_wolse[1] else None,
        }
    if unmapped:
        print(f"  지도에 못 맞춘 코드: {dict(unmapped)}")

    def metrics(pr, vo, je, rn, r_, wo, income):
        out = {"nTrade": vo[0], "nRent": wo[1]}
        if len(pr) >= MIN_N:
            m2 = median(pr)
            p84 = m2 * area
            out["priceM2"] = round(m2, 1)
            out["price84"] = round(p84)
            if income:
                out["pir"] = round(p84 / income, 1)
                out["burden"] = round(payment(p84 * ltv, rate, term) / (income / 12) * 100, 1)
        if len(je) >= MIN_COMPLEX:
            out["jeonseRatio"] = round(median(je) * 100, 1)
            out["nComplex"] = len(je)
        if vo[1] >= MIN_N:
            out["volChg"] = round(vo[0] / vo[1] - 1, 3)
        if len(rn) >= MIN_N:
            out["renewUp"] = round(median(rn), 4)
            out["renewOver5"] = round(sum(x > 0.05 + 1e-9 for x in rn) / len(rn), 3)  # 5% 상한을 넘은 비율
            out["renewDown"] = round(sum(x < -1e-9 for x in rn) / len(rn), 3)
            out["nRenew"] = len(rn)
        if r_[1] >= MIN_N:
            out["rrShare"] = round(r_[0] / r_[1], 3)
        if wo[1] >= MIN_N:
            out["wolseShare"] = round(wo[0] / wo[1], 3)
        return out

    def complex_ratios(rid: str) -> list[float]:
        return [median(jeonse_c[rid][k]) / median(v) for k, v in sale_c[rid].items() if k in jeonse_c[rid]]

    ratios = {rid: complex_ratios(rid) for rid in set(sale_c) & set(jeonse_c)}
    out_regions = {}
    for reg in regions:
        rid = reg["id"]
        inc = hreg.get(reg["sidoCode"], {}).get("current", {}).get("income")
        m = metrics(price[rid], vol[rid], ratios.get(rid, []), renew[rid], rr[rid], wolse[rid], inc)
        m["income"] = inc
        out_regions[rid] = m

    allv = lambda d: [x for v in d.values() for x in v]  # noqa: E731
    nat = metrics(allv(price), [sum(v[0] for v in vol.values()), sum(v[1] for v in vol.values())],
                  allv(ratios), allv(renew), [sum(v[0] for v in rr.values()), sum(v[1] for v in rr.values())],
                  [sum(v[0] for v in wolse.values()), sum(v[1] for v in wolse.values())], hreg["00"]["current"]["income"])
    have = [k for k, v in out_regions.items() if "burden" in v]
    print(f"  기간 {win[0]}~{win[-1]} · 부담률 있는 시군구 {len(have)}/{len(regions)} · 전국 84㎡ {nat.get('price84')}만원")

    return {
        "meta": {
            "period": [win[0], win[-1]],
            "prevPeriod": [prev[0], prev[-1]],
            "fetched": fetched.isoformat(),
            "rate": rate,
            "assumptions": {"area": area, "ltv": ltv, "termYears": term, "areaRange": [AREA_MIN, AREA_MAX], "minN": MIN_N},
            "monthsProvisional": [ym for ym in months_all if ym > last],
            "sources": [
                "국토교통부 아파트 매매 실거래가 상세 자료 (공공데이터포털 오픈API)",
                "국토교통부 아파트 전월세 실거래가 자료 (공공데이터포털 오픈API)",
                "가구소득·금리: 「집값을 감당할 수 있을까?」 시도 자료 (가계금융복지조사, 한국은행)",
            ],
        },
        "national": nat,
        "regions": out_regions,
        "monthly": {"months": months_all, **{k: [nat_month[ym][k] for ym in months_all] for k in ("trades", "renewUp", "renewDown", "rrShare", "wolseShare")}},
    }


if __name__ == "__main__":
    r = build()
    if r:
        print(json.dumps(r["national"], ensure_ascii=False))
