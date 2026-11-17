#!/usr/bin/env bash
# 대한민국 시군구·시도 경계 → src/data/geo.json
# 원본: vuski/admdongkor 행정동 경계(2025-12-31, 통계청 SGIS 기반). 일반구는 시 단위로 합친다.
# 필요: node(npx), python3. 한 번만 실행하면 되고 결과물(geo.json)은 저장소에 커밋한다.
set -euo pipefail
cd "$(dirname "$0")"
VER=${VER:-ver20251231}
TMP=$(mktemp -d)
curl -sL -o "$TMP/dong.geojson" "https://raw.githubusercontent.com/vuski/admdongkor/master/$VER/HangJeongDong_$VER.geojson"
python3 -I - "$TMP/dong.geojson" ../../src/data/dongne.json "$TMP/dong_u.geojson" <<'PY'
import json, sys
src, dongne, out = sys.argv[1:4]
ids = {r["id"] for r in json.load(open(dongne))["regions"]}
d = json.load(open(src))
for f in d["features"]:
    s = f["properties"]["sgg"]
    u = s if s in ids else s[:4] + "0"   # 41111 수원시장안구 → 41110 수원시
    assert u in ids, (s, f["properties"])
    f["properties"] = {"id": u, "sido": f["properties"]["sido"]}
json.dump(d, open(out, "w"))
PY
MS="npx -y mapshaper@0.6.102"
$MS "$TMP/dong_u.geojson" -dissolve id copy-fields=sido -proj EPSG:5179 -simplify 4% keep-shapes -filter-islands min-area=2km2 -o format=geojson "$TMP/sgg.json" precision=1
$MS "$TMP/sgg.json" -dissolve sido -o format=geojson "$TMP/sido.json" precision=1
python3 -I svg_paths.py "$TMP/sgg.json" "$TMP/sido.json" ../../src/data/geo.json
rm -rf "$TMP"
