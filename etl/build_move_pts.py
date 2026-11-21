"""타임랩스 점의 출발·도착 위치: 시군구마다 '사람이 실제로 드나든 동' 비중대로 뽑은 무작위 점.

- 비중: 행안부 행정동 전입신고(원자료, 로컬 전용)에서 다른 시군구로 나간(전출)·들어온(전입) 인원을 행정동별로 센다.
- 위치: 그 비중대로 행정동을 고르고, 행정동 경계(vuski/admdongkor, CC BY 4.0) 안의 무작위 점을 뽑는다.
- 결과: public/data/move_pts.json — 시군구 → 출발 점 N개, 도착 점 N개. 집계에서 나온 좌표만 내보낸다(원자료 재배포 아님).

원자료가 없으면(CI) 아무것도 하지 않는다. 결과물은 저장소에 커밋한다.
"""
from __future__ import annotations

import csv
import gzip
import json
import random
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from build_move import MOVE, ROOT, load_regions, make_mapper

VER = "ver20251231"
DONG_URL = f"https://raw.githubusercontent.com/vuski/admdongkor/master/{VER}/HangJeongDong_{VER}.geojson"
CACHE = ROOT / "data" / "raw" / f"HangJeongDong_{VER}.geojson"
OUT = ROOT / "public" / "data" / "move_pts.json"
N = 40  # 시군구마다 출발·도착 점 개수
X0, Y0, Q = 124.0, 33.0, 1000  # 좌표 정수화: (경도-124)*1000, (위도-33)*1000 ≈ 100m


def scan(ym: str):
    regs, _ = load_regions()
    mp = make_mapper(regs)
    out_c: Counter = Counter()
    in_c: Counter = Counter()
    with gzip.open(MOVE / f"{ym}.csv.gz", "rt", encoding="utf-8") as fh:
        rd = csv.reader(fh)
        ix = {h: i for i, h in enumerate(next(rd))}
        i_in, i_out, i_tot = ix["mvinAdmmCd"], ix["mvtAdmmCd"], ix["totNmprCnt"]
        i_ins, i_ind, i_outs, i_outd = ix["mvinSggNm"], ix["mvinDongNm"], ix["mvtSggNm"], ix["mvtDongNm"]
        for row in rd:
            n = int(row[i_tot])
            if not n:
                continue
            a = mp(row[i_in], row[i_ins], row[i_ind])
            b = mp(row[i_out], row[i_outs], row[i_outd])
            if a is None or b is None or a == b:
                continue  # 시군구를 넘는 이사만
            in_c[row[i_in]] += n
            out_c[row[i_out]] += n
    return out_c, in_c


def in_ring(r, x, y):
    inside = False
    j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i]
        xj, yj = r[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def sampler(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    xs = [p[0] for pg in polys for p in pg[0]]
    ys = [p[1] for pg in polys for p in pg[0]]
    bb = (min(xs), min(ys), max(xs), max(ys))

    def draw(rng: random.Random):
        for _ in range(500):
            x, y = rng.uniform(bb[0], bb[2]), rng.uniform(bb[1], bb[3])
            if any(in_ring(pg[0], x, y) and not any(in_ring(h, x, y) for h in pg[1:]) for pg in polys):
                return x, y
        return (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    return draw


def build() -> None:
    months = sorted(p.name[:6] for p in MOVE.glob("*.csv.gz")) if MOVE.exists() else []
    if not months:
        print("move_pts: 원자료 없음 — 건너뜀")
        return
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(scan, months))
    out_c: Counter = Counter()
    in_c: Counter = Counter()
    for o, i in res:
        out_c.update(o)
        in_c.update(i)

    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DONG_URL, CACHE)
    geo = json.loads(CACHE.read_text())
    regs, _ = load_regions()
    ids = {r["id"] for r in regs}

    # 지도 경계(public/geo/sgg.json)와 같은 규칙으로 행정동 → 시군구 (일반구는 시로)
    by_sgg: dict[str, list] = {}
    for f in geo["features"]:
        p = f["properties"]
        s = p["sgg"]
        u = s if s in ids else s[:4] + "0"
        by_sgg.setdefault(u, []).append((p["adm_cd2"], f["geometry"]))

    rng = random.Random(20251231)
    pts: dict[str, list[list[int]]] = {}
    matched = total = 0
    for sid, dongs in sorted(by_sgg.items()):
        draws = {code: sampler(g) for code, g in dongs}
        sides = []
        for cnt in (out_c, in_c):
            w = [(code, cnt.get(code, 0)) for code, _ in dongs]
            tot = sum(v for _, v in w)
            matched += tot
            if tot == 0:  # 자료가 맞지 않으면 면적 대신 동마다 고르게
                w = [(code, 1) for code, _ in dongs]
            codes, ws = zip(*w)
            flat: list[int] = []
            for code in rng.choices(codes, weights=ws, k=N):
                x, y = draws[code](rng)
                flat += [round((x - X0) * Q), round((y - Y0) * Q)]
            sides.append(flat)
        pts[sid] = sides
    total = sum(out_c.values()) + sum(in_c.values())
    print(f"move_pts: {len(pts)}개 시군구, 행정동 경계와 맞은 이동 {matched / max(1, total):.1%} ({len(months)}개월)")
    OUT.write_text(json.dumps({"n": N, "x0": X0, "y0": Y0, "q": Q, "src": f"vuski/admdongkor {VER}", "pts": pts}, separators=(",", ":")))
    print(f"  → {OUT.relative_to(ROOT)} {OUT.stat().st_size / 1024:.0f}KB")


if __name__ == "__main__":
    sys.exit(build())
