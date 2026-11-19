"""국토부 실거래가 API에 넣을 시군구 코드(LAWD_CD) 목록 → etl/molit/lawd.json

국토부는 시군구 코드가 바뀌면 과거 거래도 현재 코드로 옮겨 준다(2026-11 확인: 강원 42→51,
군위 47→27, 부천·화성 일반구, 인천 구 개편, 전남광주 12 모두 옛 코드로 조회하면 0건).
그래서 최신 행정경계의 코드만 조회한다. 코드가 또 바뀌면 최신 버전으로 다시 만들면 되고,
새 코드의 과거 달은 수집기가 빠진 조회로 보고 다시 받는다.

원본: vuski/admdongkor 행정동 경계의 sgg(5자리, 일반구 단위). 한 번만 실행하고 결과는 커밋한다.
사용: python3 etl/molit/make_lawd.py [버전 ...]   (기본: ver20261001, 여러 개면 합집합)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = "https://raw.githubusercontent.com/vuski/admdongkor/master"
API = "https://api.github.com/repos/vuski/admdongkor/contents"
DEFAULT = ["ver20261001"]


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def codes(ver: str) -> dict[str, tuple[str, str]]:
    files = [f["name"] for f in fetch_json(f"{API}/{ver}") if f["name"].endswith(".geojson")]
    if not files:
        raise SystemExit(f"{ver}: geojson 없음")
    d = fetch_json(f"{RAW}/{ver}/{files[0]}")
    out = {}
    for f in d["features"]:
        p = f["properties"]
        out[p["sgg"]] = (p["sidonm"], p["sggnm"])
    return out


def main(vers: list[str]) -> None:
    merged: dict[str, dict] = {}
    for v in vers:
        cs = codes(v)
        print(f"{v}: 시군구 {len(cs)}개")
        for c, (sido, name) in cs.items():
            e = merged.setdefault(c, {"code": c, "sido": sido, "name": name, "seen": []})
            e["sido"], e["name"] = sido, name  # 최신 버전 이름 우선
            e["seen"].append(v)
    rows = sorted(merged.values(), key=lambda e: e["code"])
    body = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows)
    src = json.dumps("vuski/admdongkor " + " + ".join(vers), ensure_ascii=False)
    (HERE / "lawd.json").write_text(f'{{"source": {src},\n "codes": [\n{body}\n]}}\n')
    print(f"→ lawd.json: {len(rows)}개 코드")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
