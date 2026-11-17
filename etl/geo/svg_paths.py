"""mapshaper가 만든 투영 좌표(EPSG:5179) GeoJSON → SVG 경로 JSON (src/data/geo.json).

  python3 svg_paths.py sgg.json sido.json ../../src/data/geo.json

출력: {"w","h","sgg":{id:{"d","c":[x,y],"sido"}}, "sido":{id:{"d","c","b":[x0,y0,x1,y1]}}}
좌표는 화면 단위(가로 W), 소수 1자리, 상대 이동(l)으로 압축.
"""
import json
import sys

W = 800.0
PAD = 8.0


def rings(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [r for poly in geom["coordinates"] for r in poly]


def main(sgg_path, sido_path, out_path):
    sgg = json.load(open(sgg_path))["features"]
    sido = json.load(open(sido_path))["features"]
    xs = [p[0] for f in sido for r in rings(f["geometry"]) for p in r]
    ys = [p[1] for f in sido for r in rings(f["geometry"]) for p in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = (W - 2 * PAD) / (x1 - x0)
    H = round((y1 - y0) * s + 2 * PAD, 1)

    def P(p):
        return (round((p[0] - x0) * s + PAD, 1), round((y1 - p[1]) * s + PAD, 1))

    def path(geom):
        out = []
        for r in rings(geom):
            pts = [P(p) for p in r]
            # 연속 중복 제거
            dd = [pts[0]]
            for q in pts[1:]:
                if q != dd[-1]:
                    dd.append(q)
            if len(dd) < 4:
                continue
            seg = [f"M{dd[0][0]:g} {dd[0][1]:g}l"]
            prev = dd[0]
            parts = []
            for q in dd[1:-1]:
                parts.append(f"{round(q[0]-prev[0],1):g} {round(q[1]-prev[1],1):g}")
                prev = q
            seg.append(" ".join(parts).replace(" -", "-"))
            seg.append("z")
            out.append("".join(seg))
        return "".join(out)

    def bbox(geom):
        pts = [P(p) for r in rings(geom) for p in r]
        return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]

    def centroid(geom):
        # 가장 큰 고리의 면적 중심
        best, ba = None, -1
        for r in rings(geom):
            pts = [P(p) for p in r]
            a = cx = cy = 0.0
            for i in range(len(pts) - 1):
                (xa, ya), (xb, yb) = pts[i], pts[i + 1]
                c = xa * yb - xb * ya
                a += c
                cx += (xa + xb) * c
                cy += (ya + yb) * c
            if abs(a) > ba and a != 0:
                ba, best = abs(a), [round(cx / (3 * a), 1), round(cy / (3 * a), 1)]
        return best

    res = {"w": W, "h": H, "sgg": {}, "sido": {}}
    for f in sgg:
        g = f["geometry"]
        res["sgg"][f["properties"]["id"]] = {"d": path(g), "c": centroid(g), "sido": f["properties"]["sido"], "b": bbox(g)}
    for f in sido:
        g = f["geometry"]
        res["sido"][f["properties"]["sido"]] = {"d": path(g), "c": centroid(g), "b": bbox(g)}
    json.dump(res, open(out_path, "w"), ensure_ascii=False, separators=(",", ":"))
    print("geo:", len(res["sgg"]), "sgg,", len(res["sido"]), "sido,", f"{W}x{H}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
