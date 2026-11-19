"""행정안전부 지역별 인구이동 현황(행정동 → 행정동, 성·만나이별, 월별) 수집기 — 표준 라이브러리만 사용.

    python3 etl/mois/collect_move.py              # 수집(한도에 걸리면 멈추고, 다음 실행 때 이어서)
    python3 etl/mois/collect_move.py status       # 진행 상황
    python3 etl/mois/collect_move.py export       # 조회 단위 캐시 → 월별 csv.gz

옵션: --from 202210(제공 시작)  --to YYYYMM(기본: 지난달. 이번 달은 공개 전이면 0건이 아니라 오류 10이 온다)  --lv 3(1 시도, 2 시군구, 3 행정동)
      --workers 4(동시 다운로드)  --max-calls N  --final-days 15

API: apis.data.go.kr/1741000/ppltnDataStus/selectPpltnDataStus (공공데이터포털 15108093)
  - 전입·전출 행정기관코드가 둘 다 필수이고 전국 코드(0000000000)는 0건이다.
    그래서 시도→시도 256쌍(현재 16개 시도) × 월로 나눠 받는다.
  - 새 시도 코드(강원 51, 전북 52, 전남광주 12)로 조회하면 옛 달도 나온다. 다만 응답의 행정동 코드는
    그 달 당시의 코드다(2022년 강원은 42…). 12는 옛 광주(29)·전남(46)을 모두 포함한다.
  - 명세의 한 페이지 상한은 100이지만 5,000까지 받아 준다(2026-11 확인). 행 하나가 약 8.5KB라
    전국 한 달이 1~2GB 내려받기다. 호출 수보다 내려받기 시간이 병목이다.
  - 2022년 10월부터 제공. 한 달치는 다음 달 중순께 나온다(2026-11-19에 10월분 있음).

저장: data/mois/move/calls/lv{lv}/{YYYYMM}/{전입시도}-{전출시도}.json.gz — 열 이름 + 행(숫자는 정수).
달이 끝나고 --final-days가 지난 뒤 받은 조회는 확정으로 보고 다시 받지 않는다. 그 전에는 하루 한 번 다시 받는다.
export: data/mois/move/lv{lv}/{YYYYMM}.csv.gz + manifest.json. (통계년월, 전입코드, 전출코드)가 같은 행은 한 번만.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from datagokr import Fatal, Quota, ROOT, api_key, get, month_end, months_between, today, url  # noqa: E402

BASE = os.environ.get("MOIS_BASE", "https://apis.data.go.kr/1741000") + "/ppltnDataStus/selectPpltnDataStus"
OUT = ROOT / "data" / "mois" / "move"
FIRST = "202210"
ROWS = 5000
# 현재 시도 코드(2026-07 전남광주 통합 이후). 옛 코드(29·42·45·46)는 새 코드 조회에 포함된다.
SIDO = ["11", "12", "26", "27", "28", "30", "31", "36", "41", "43", "44", "47", "48", "50", "51", "52"]

ID_COLS = ["statsYm", "mvinAdmmCd", "mvinCtpvNm", "mvinSggNm", "mvinDongNm",
           "mvtAdmmCd", "mvtCtpvNm", "mvtSggNm", "mvtDongNm"]
SUM_COLS = ["totNmprCnt", "maleNmprCnt", "femlNmprCnt"]
AGE_COLS = [f"male{a}AgeNmprCnt" for a in range(111)] + [f"feml{a}AgeNmprCnt" for a in range(111)]
COLS = ID_COLS + SUM_COLS + AGE_COLS
N_ID = len(ID_COLS)
KEY = (0, 1, 5)  # statsYm, mvinAdmmCd, mvtAdmmCd


class BadRequest(RuntimeError):
    """재시도해도 같은 결과인 요청 오류."""


def call_path(lv: str, ym: str, i: str, o: str) -> Path:
    return OUT / "calls" / f"lv{lv}" / ym / f"{i}-{o}.json.gz"


def read_call(p: Path) -> dict:
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def read_meta(p: Path) -> dict:
    """큰 파일을 다 읽지 않고 받은 날짜·건수만 (save가 앞쪽에 쓴다)."""
    with gzip.open(p, "rt", encoding="utf-8") as f:
        head = f.read(300)
    end = head.index(', "cols"')
    return json.loads(head[:end] + "}")


def is_final(meta: dict, ym: str, final_days: int) -> bool:
    return (date.fromisoformat(meta["fetched"]) - month_end(ym)).days >= final_days


def needs_fetch(lv: str, ym: str, i: str, o: str, final_days: int) -> bool:
    p = call_path(lv, ym, i, o)
    if not p.exists():
        return True
    meta = read_meta(p)
    return not is_final(meta, ym, final_days) and date.fromisoformat(meta["fetched"]) < today()


def _parse(text: str) -> tuple[list[dict], int]:
    try:
        d = json.loads(text)["Response"]
    except (ValueError, KeyError, TypeError):
        raise RuntimeError(f"예상과 다른 응답: {' '.join(text[:200].split())}")
    h = d.get("head") or {}
    code, msg = str(h.get("resultCode", "")).strip(), h.get("resultMsg", "")
    if code in ("3", "03"):  # NODATA_ERROR
        return [], 0
    if code in ("10",):  # INVALID_REQUEST_PARAMETER: 아직 공개 안 된 달 등. 재시도해도 같다
        raise BadRequest(f"API 오류 {code} {msg}")
    if code not in ("0", "00"):
        raise RuntimeError(f"API 오류 {code} {msg}")
    items = d.get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(items, dict):
        items = [items]
    return items, int(h.get("totalCount") or 0)


def _row(it: dict) -> list:
    out = [str(it.get(c, "") or "").strip() for c in ID_COLS]
    for c in SUM_COLS + AGE_COLS:
        v = str(it.get(c, "") or "0").strip()
        out.append(int(v) if v.lstrip("-").isdigit() else v)
    return out


def fetch(lv: str, ym: str, i: str, o: str) -> tuple[list[list], int, int]:
    """한 시도쌍·한 달 전체. (행, 호출 수, 합계가 안 맞는 행 수)."""
    rows: list[list] = []
    page, calls = 1, 0
    while True:
        params = {"mvinAdmmCd": i + "00000000", "mvtAdmmCd": o + "00000000", "srchFrYm": ym, "srchToYm": ym,
                  "lv": lv, "type": "JSON", "numOfRows": ROWS, "pageNo": page}
        for attempt in range(3):
            try:
                got, total = _parse(get(url(BASE, params), timeout=300))
                calls += 1
                break
            except BadRequest:
                raise
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        rows.extend(_row(it) for it in got)
        if not got or len(rows) >= total:
            break
        page += 1
    if total and len(rows) != total:
        raise RuntimeError(f"건수 불일치 {ym} {i}-{o}: {len(rows)} / {total}")
    bad = 0
    for r in rows:  # 남녀 만나이별 합 = 남녀 인구, 남+여 = 총인구
        tot, m, f = r[N_ID:N_ID + 3]
        ages = r[N_ID + 3:]
        if isinstance(tot, int) and (sum(ages[:111]) != m or sum(ages[111:]) != f or m + f != tot):
            bad += 1
    return rows, calls, bad


def save(lv: str, ym: str, i: str, o: str, rows: list[list]) -> None:
    p = call_path(lv, ym, i, o)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        # 앞쪽 필드 순서 고정: read_meta가 cols 앞까지만 읽는다
        f.write(json.dumps({"ym": ym, "in": i, "out": o, "lv": lv, "fetched": today().isoformat(), "count": len(rows)},
                           ensure_ascii=False)[:-1])
        f.write(', "cols": ' + json.dumps(COLS) + ', "rows": [')
        for k, r in enumerate(rows):
            f.write(("," if k else "") + json.dumps(r, ensure_ascii=False, separators=(",", ":")))
        f.write("]}")
    tmp.replace(p)


def last_month() -> str:
    t = today()
    return f"{t.year - (t.month == 1):04d}{(t.month - 2) % 12 + 1:02d}"


def window(a) -> list[str]:
    return months_between(a.first, a.to or last_month())


def collect(a) -> int:
    api_key()
    todo = [(ym, i, o) for ym in window(a) for i in SIDO for o in SIDO if needs_fetch(a.lv, ym, i, o, a.final_days)]
    total_units = len(window(a)) * len(SIDO) ** 2
    print(f"[move lv{a.lv}] 받을 조회 {len(todo):,}개 (전체 {total_units:,}) · 동시 {a.workers}")
    stop = threading.Event()
    lock = threading.Lock()
    st = {"calls": 0, "units": 0, "rows": 0, "bad": 0, "fails": 0}
    t0 = time.time()

    def work(job):
        ym, i, o = job
        if stop.is_set():
            return
        with lock:
            if a.max_calls is not None and st["calls"] >= a.max_calls:
                stop.set()
                return
        rows, n, bad = fetch(a.lv, ym, i, o)
        save(a.lv, ym, i, o, rows)
        with lock:
            st["calls"] += n
            st["units"] += 1
            st["rows"] += len(rows)
            st["bad"] += bad
            if st["units"] % 50 == 0:
                el = time.time() - t0
                print(f"[move] {st['units']:,}/{len(todo):,} 조회 · {st['rows']:,}행 · 호출 {st['calls']:,} · "
                      f"{st['rows'] / el:.0f}행/초 · 현재 {ym}", flush=True)

    code = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(work, j): j for j in todo}
        for fu in as_completed(futs):
            try:
                fu.result()
            except Quota as e:
                if not stop.is_set():
                    print(f"[move] 하루 호출 한도 도달(호출 {st['calls']:,}회): {e}. 다음 실행에서 이어서 받습니다")
                stop.set()
            except Fatal as e:
                if not stop.is_set():
                    print(f"[move] 중단 — 인증키/활용신청 확인 필요: {e}", file=sys.stderr)
                stop.set()
                code = 2
            except RuntimeError as e:
                st["fails"] += 1
                print(f"[move] 실패 {futs[fu]}: {e}", file=sys.stderr)
    if a.max_calls is not None and st["calls"] >= a.max_calls:
        print(f"[move] --max-calls {a.max_calls} 도달, 다음 실행에서 이어서")
    print(f"[move] 이번 실행: 조회 {st['units']:,}개, 호출 {st['calls']:,}회, {st['rows']:,}행, "
          f"합계 불일치 {st['bad']}행, 실패 {st['fails']}")
    return code


def status(a) -> None:
    yms = window(a)
    total = len(yms) * len(SIDO) ** 2
    have = final = rows = 0
    per_month = {}
    for ym in yms:
        n = r = 0
        for i in SIDO:
            for o in SIDO:
                p = call_path(a.lv, ym, i, o)
                if p.exists():
                    m = read_meta(p)
                    n += 1
                    r += m["count"]
                    final += is_final(m, ym, a.final_days)
        have += n
        rows += r
        per_month[ym] = (n, r)
    print(f"[move lv{a.lv}] {yms[-1]}~{yms[0]} · 시도쌍 {len(SIDO) ** 2}개/월")
    print(f"  받은 조회 {have:,}/{total:,} (확정 {final:,}) · {rows:,}행 · 남은 조회 {total - have:,}")
    done = [ym for ym, (n, _) in per_month.items() if n == len(SIDO) ** 2]
    if done:
        print(f"  다 받은 달 {len(done)}개: {done[-1]}~{done[0]} · 한 달 평균 {sum(per_month[y][1] for y in done) // len(done):,}행")


def export(a) -> None:
    d = OUT / f"lv{a.lv}"
    d.mkdir(parents=True, exist_ok=True)
    mf = d / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {"months": {}}
    manifest.update({"api": "행정안전부_지역별 인구이동 현황", "lv": a.lv, "exported": today().isoformat()})
    for ym in window(a):
        files = [call_path(a.lv, ym, i, o) for i in SIDO for o in SIDO]
        files = [p for p in files if p.exists()]
        if not files:
            continue
        seen: dict[tuple, list] = {}
        dup = conflict = 0
        fetched = []
        for p in files:
            rec = read_call(p)
            fetched.append(rec["fetched"])
            for r in rec["rows"]:
                k = tuple(r[j] for j in KEY)
                if k in seen:
                    dup += 1
                    conflict += seen[k] != r
                    continue
                seen[k] = r
        if not seen:
            continue
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(COLS)
        for k in sorted(seen):
            w.writerow(seen[k])
        with gzip.GzipFile(d / f"{ym}.csv.gz", "wb", mtime=0) as g:
            g.write(buf.getvalue().encode("utf-8"))
        manifest["months"][ym] = {"rows": len(seen), "dup_removed": dup, "dup_conflict": conflict,
                                  "calls": len(files), "complete": len(files) == len(SIDO) ** 2,
                                  "fetched": [min(fetched), max(fetched)]}
        print(f"[move] {ym}: {len(seen):,}행 (중복 {dup}, 값이 다른 중복 {conflict}) · 조회 {len(files)}/{len(SIDO) ** 2}")
    manifest["months"] = dict(sorted(manifest["months"].items(), reverse=True))
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="행정안전부 지역별 인구이동 수집기")
    ap.add_argument("cmd", nargs="?", default="collect", choices=["collect", "status", "export"])
    ap.add_argument("--from", dest="first", default=FIRST)
    ap.add_argument("--to", default=None)
    ap.add_argument("--lv", default="3", choices=["1", "2", "3"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-calls", type=int, default=None)
    ap.add_argument("--final-days", type=int, default=15)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        status(a)
        return 0
    if a.cmd == "export":
        export(a)
        return 0
    return collect(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
