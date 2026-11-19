"""국토교통부 아파트 실거래가(매매·전월세) 수집기 — 표준 라이브러리만 사용.

    python3 etl/molit/collect.py              # 수집(하루 한도에 걸리면 멈추고, 다음 실행 때 이어서)
    python3 etl/molit/collect.py status       # 진행 상황
    python3 etl/molit/collect.py export       # 조회 단위 캐시 → 월별 csv.gz

옵션: --kind trade,rent  --months 60(현재 달 + 직전 N개월)  --max-calls N(종류별 이번 실행 상한)
      --final-days 90(달이 끝나고 이만큼 지난 뒤 받은 조회는 확정으로 보고 다시 받지 않음)  --sleep 0.05

API는 시군구(LAWD_CD) 1곳 × 계약월(DEAL_YMD) 1개를 한 번에 준다. 조회 하나가 파일 하나:
    data/molit/calls/{kind}/{YYYYMM}/{LAWD}.json.gz   (받은 날짜, 건수, 원본 항목 그대로)
신고 기한(계약 후 30일)과 계약 해제 반영 때문에 최근 달은 확정될 때까지 매일 다시 받는다.
export 결과: data/molit/{kind}/{YYYYMM}.csv.gz + manifest.json. 원자료는 git에 올리지 않는다.

인증키: 공공데이터포털에서 아래 두 API를 활용신청한다. 키 설정은 etl/datagokr.py 참고.
  - 국토교통부_아파트 매매 실거래가 상세 자료
  - 국토교통부_아파트 전월세 실거래가 자료
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from datagokr import Fatal, Quota, api_key, get, month_end, months, today, url  # noqa: E402

ROOT = HERE.parent.parent
OUT = ROOT / "data" / "molit"
BASE = os.environ.get("MOLIT_BASE", "https://apis.data.go.kr/1613000")

KINDS = {
    "trade": ("RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev", "아파트 매매 실거래가 상세"),
    "rent": ("RTMSDataSvcAptRent/getRTMSDataSvcAptRent", "아파트 전월세 실거래가"),
}
ROWS = 1000  # 한 페이지 최대 건수
OK_CODES = {"00", "000"}
NODATA_CODES = {"03"}
QUOTA_CODES = {"22"}
FATAL_CODES = {"12", "20", "30", "31", "32", "33"}  # 서비스 없음·접근 거부·미등록 키·기한 만료·IP·미서명


# ---------- 설정 ----------

def lawd_codes() -> list[str]:
    return [c["code"] for c in json.loads((HERE / "lawd.json").read_text())["codes"]]


def call_path(kind: str, ym: str, lawd: str) -> Path:
    return OUT / "calls" / kind / ym / f"{lawd}.json.gz"


def read_call(p: Path) -> dict:
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def is_final(rec: dict, ym: str, final_days: int) -> bool:
    return (date.fromisoformat(rec["fetched"]) - month_end(ym)).days >= final_days


def needs_fetch(kind: str, ym: str, lawd: str, final_days: int) -> bool:
    p = call_path(kind, ym, lawd)
    if not p.exists():
        return True
    rec = read_call(p)
    if is_final(rec, ym, final_days):
        return False
    return date.fromisoformat(rec["fetched"]) < today()  # 확정 전이면 하루 한 번 다시 받는다


# ---------- API ----------

def _url(kind: str, lawd: str, ym: str, page: int) -> str:
    return url(f"{BASE}/{KINDS[kind][0]}", {"LAWD_CD": lawd, "DEAL_YMD": ym, "pageNo": page, "numOfRows": ROWS})


def _parse(text: str) -> tuple[list[dict], int]:
    """XML 응답 → (항목, 전체 건수). 한도·키 오류는 예외로."""
    low = text.lower()
    if "limited_number_of_service_requests" in low or "rate limit" in low:
        raise Quota(text[:200])
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        if "service_key" in low or "unregistered" in low or "forbidden" in low:
            raise Fatal(text[:300])
        raise RuntimeError(f"XML 아님: {text[:200]!r}")
    code = (root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or "").strip()
    msg = (root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "").strip()
    if code in QUOTA_CODES:
        raise Quota(f"{code} {msg}")
    if code in FATAL_CODES:
        raise Fatal(f"{code} {msg}")
    if code in NODATA_CODES:
        return [], 0
    if code not in OK_CODES:
        raise RuntimeError(f"API 오류 {code} {msg}")
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    total = int((root.findtext(".//totalCount") or "0").strip() or 0)
    return items, total


def fetch(kind: str, lawd: str, ym: str, sleep: float) -> tuple[list[dict], int]:
    """한 시군구·한 달 전체(페이지 모두). (항목, 사용한 호출 수)."""
    items: list[dict] = []
    page, calls = 1, 0
    while True:
        text = None
        for attempt in range(3):  # 일시적인 API 오류(99 등)는 몇 번 더
            try:
                text = get(_url(kind, lawd, ym, page))
                calls += 1
                got, total = _parse(text)
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
        items.extend(got)
        if sleep:
            time.sleep(sleep)
        if not got or len(items) >= total:
            break
        page += 1
    if total and len(items) != total:
        raise RuntimeError(f"건수 불일치 {lawd} {ym}: {len(items)} / {total}")
    return items, calls


def save(kind: str, lawd: str, ym: str, items: list[dict]) -> None:
    p = call_path(kind, ym, lawd)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"lawd": lawd, "ym": ym, "fetched": today().isoformat(), "count": len(items), "items": items}
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(p)


# ---------- 명령 ----------

def collect(kinds: list[str], n_months: int, max_calls: int | None, final_days: int, sleep: float) -> int:
    api_key()
    codes = lawd_codes()
    yms = months(n_months)
    for kind in kinds:
        todo = [(ym, c) for ym in yms for c in codes if needs_fetch(kind, ym, c, final_days)]
        print(f"[{kind}] {KINDS[kind][1]}: 받을 조회 {len(todo):,}개 (전체 {len(yms) * len(codes):,})")
        used = done = fails = rows = 0
        t0 = time.time()
        for ym, c in todo:
            if max_calls is not None and used >= max_calls:
                print(f"[{kind}] --max-calls {max_calls} 도달, 다음 실행에서 이어서")
                break
            try:
                items, n = fetch(kind, c, ym, sleep)
            except Quota as e:
                print(f"[{kind}] 하루 호출 한도 도달({used:,}회 사용): {e}. 내일 다시 실행하면 이어서 받습니다")
                break
            except Fatal as e:
                print(f"[{kind}] 중단 — 인증키/활용신청 확인 필요: {e}", file=sys.stderr)
                return 2
            except RuntimeError as e:
                fails += 1
                print(f"[{kind}] 실패 {c} {ym}: {e}", file=sys.stderr)
                if fails >= 20 and done == 0:
                    print(f"[{kind}] 연속 실패, 이 종류는 멈춥니다", file=sys.stderr)
                    break
                continue
            save(kind, c, ym, items)
            used += n
            done += 1
            rows += len(items)
            if done % 200 == 0:
                rate = done / max(time.time() - t0, 1e-6)
                print(f"[{kind}] {done:,}/{len(todo):,} 조회 · {rows:,}건 · {rate:.1f}조회/초 · 현재 {ym}")
        print(f"[{kind}] 이번 실행: 조회 {done:,}개, 호출 {used:,}회, 거래 {rows:,}건, 실패 {fails}")
    return 0  # 한도 도달은 정상 종료(다음 실행에서 이어서)


def status(kinds: list[str], n_months: int, final_days: int, max_calls: int | None) -> None:
    codes = lawd_codes()
    yms = months(n_months)
    total = len(yms) * len(codes)
    for kind in kinds:
        have = final = rows = 0
        for ym in yms:
            for c in codes:
                p = call_path(kind, ym, c)
                if p.exists():
                    rec = read_call(p)
                    have += 1
                    rows += rec["count"]
                    final += is_final(rec, ym, final_days)
        miss = total - have
        print(f"[{kind}] {KINDS[kind][1]}: {yms[-1]}~{yms[0]} · 시군구 {len(codes)}개")
        print(f"  받은 조회 {have:,}/{total:,} (확정 {final:,}) · 거래 {rows:,}건 · 남은 조회 {miss:,}")
        if max_calls:
            print(f"  하루 {max_calls:,}회면 약 {-(-miss // max_calls)}일")


def export(kinds: list[str], n_months: int) -> None:
    """조회 캐시 → 월별 csv.gz. 같은 거래가 두 조회에서 오면 한 번만 남긴다(안전장치, lawd.json에 없는 코드의 옛 캐시는 읽지 않음)."""
    codes = lawd_codes()
    for kind in kinds:
        d = OUT / kind
        d.mkdir(parents=True, exist_ok=True)
        manifest = {"kind": kind, "api": KINDS[kind][1], "exported": today().isoformat(), "months": {}}
        mf = d / "manifest.json"
        if mf.exists():
            manifest["months"] = json.loads(mf.read_text()).get("months", {})
        for ym in months(n_months):
            recs = [read_call(p) for c in codes if (p := call_path(kind, ym, c)).exists()]
            if not recs:
                continue
            # 거래 키별로 조회마다 센 횟수 중 최댓값 → 한 조회 안의 동일 거래(실제 2건)는 살리고, 조회 간 중복은 제거
            best: dict[tuple, tuple[int, str, dict]] = {}
            fields: list[str] = []
            seen_f: set[str] = set()
            raw = 0
            for rec in recs:
                cnt = Counter()
                for it in rec["items"]:
                    k = tuple(sorted(it.items()))
                    cnt[k] += 1
                    for f in it:
                        if f not in seen_f:
                            seen_f.add(f)
                            fields.append(f)
                    raw += 1
                for k, n in cnt.items():
                    if k not in best or n > best[k][0]:
                        best[k] = (n, rec["lawd"], dict(k))
            rows = [(lawd, it) for n, lawd, it in best.values() for _ in range(n)]
            rows.sort(key=lambda r: (r[0], r[1].get("dealDay", "").zfill(2), json.dumps(r[1], ensure_ascii=False, sort_keys=True)))
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["_lawd", *fields])
            for lawd, it in rows:
                w.writerow([lawd, *(it.get(f, "") for f in fields)])
            with gzip.GzipFile(d / f"{ym}.csv.gz", "wb", mtime=0) as g:  # mtime 고정: 내용이 같으면 파일도 같다
                g.write(buf.getvalue().encode("utf-8"))
            fetched = sorted(r["fetched"] for r in recs)
            manifest["months"][ym] = {
                "rows": len(rows), "dup_removed": raw - len(rows),
                "calls": len(recs), "complete": len(recs) == len(codes),
                "fetched": [fetched[0], fetched[-1]],
            }
            print(f"[{kind}] {ym}: {len(rows):,}건 (중복 제거 {raw - len(rows)}) · 조회 {len(recs)}/{len(codes)}")
        manifest["months"] = dict(sorted(manifest["months"].items(), reverse=True))
        mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="국토부 아파트 실거래가 수집기")
    ap.add_argument("cmd", nargs="?", default="collect", choices=["collect", "status", "export"])
    ap.add_argument("--kind", default="trade,rent")
    ap.add_argument("--months", type=int, default=60)
    ap.add_argument("--max-calls", type=int, default=None)
    ap.add_argument("--final-days", type=int, default=90)
    ap.add_argument("--sleep", type=float, default=0.05)
    a = ap.parse_args(argv)
    kinds = [k.strip() for k in a.kind.split(",") if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        ap.error(f"알 수 없는 --kind: {bad} (가능: {', '.join(KINDS)})")
    if a.cmd == "status":
        status(kinds, a.months, a.final_days, a.max_calls)
        return 0
    if a.cmd == "export":
        export(kinds, a.months)
        return 0
    return collect(kinds, a.months, a.max_calls, a.final_days, a.sleep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
