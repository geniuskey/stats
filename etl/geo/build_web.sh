#!/usr/bin/env bash
# 웹 지도(/map/)용 경계 → public/geo/sgg.json(시군구), sido.json(시도), sido_pts.json(시도 이름 위치) (WGS84 GeoJSON, 속성 id·sido)
# 원본: vuski/admdongkor 행정동 경계(CC BY 4.0, 원자료 통계청 SGIS 공공누리 제1유형). 일반구는 시 단위로 합친다.
# 필요: node(npx), python3. 결과물은 저장소에 커밋한다.
set -euo pipefail
cd "$(dirname "$0")"
VER=${VER:-ver20251231}
TMP=$(mktemp -d)
OUT=../../public/geo
mkdir -p "$OUT"
curl -sL -o "$TMP/dong.geojson" "https://raw.githubusercontent.com/vuski/admdongkor/master/$VER/HangJeongDong_$VER.geojson"
python3 -I - "$TMP/dong.geojson" ../../src/data/dongne.json "$TMP/dong_u.geojson" <<'PY'
import json, sys
src, dongne, out = sys.argv[1:4]
ids = {r["id"] for r in json.load(open(dongne))["regions"]}
d = json.load(open(src))
for f in d["features"]:
    s = f["properties"]["sgg"]
    u = s if s in ids else s[:4] + "0"
    assert u in ids, (s, f["properties"])
    f["properties"] = {"id": u, "sido": f["properties"]["sido"]}
json.dump(d, open(out, "w"))
PY
MS="npx -y mapshaper@0.6.102"
$MS "$TMP/dong_u.geojson" -dissolve id copy-fields=sido -simplify 8% keep-shapes -filter-islands min-area=0.5km2 -o format=geojson "$OUT/sgg.json" precision=0.0001
# 시도 경계(멀리서 볼 때 바탕 지도 대신 그리는 선)와 시도 이름 위치
$MS "$OUT/sgg.json" -dissolve sido -o format=geojson "$OUT/sido.json" precision=0.0001
$MS "$OUT/sido.json" -points inner -o format=geojson "$OUT/sido_pts.json" precision=0.001
rm -rf "$TMP"
ls -la "$OUT"
