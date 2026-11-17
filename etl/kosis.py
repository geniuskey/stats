"""KOSIS OpenAPI 클라이언트 (캐시 포함)."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://kosis.kr/openapi"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "raw"


def api_key() -> str:
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("KOSIS_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("KOSIS_API_KEY가 필요합니다 (.env 또는 환경변수)")
    return key


import sys

FRESH = "--fresh" in sys.argv
RUN_START = time.time()  # --fresh: 이번 실행 중에 받은 캐시만 재사용


def _get(path: str, params: dict, use_cache: bool = True, retries: int = 4):
    params = {**params, "apiKey": api_key(), "format": "json", "jsonVD": "Y"}
    q = urllib.parse.urlencode(params, safe=",+*")
    url = f"{BASE}/{path}?{q}"
    cache_key = hashlib.sha1((path + json.dumps({k: v for k, v in params.items() if k != "apiKey"}, sort_keys=True)).encode()).hexdigest()
    cf = CACHE / f"{cache_key}.json"
    if use_cache and cf.exists() and (not FRESH or cf.stat().st_mtime >= RUN_START):
        return json.loads(cf.read_text())
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                text = r.read().decode("utf-8")
            data = json.loads(text)
            if isinstance(data, dict) and data.get("err"):
                raise RuntimeError(f"KOSIS 오류 {data.get('err')}: {data.get('errMsg')}")
            CACHE.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(data, ensure_ascii=False))
            return data
        except RuntimeError:
            raise
        except Exception as e:  # 네트워크/파싱 오류 재시도
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"요청 실패: {path} {params.get('tblId')}: {last}")


def meta(org: str, tbl: str, kind: str = "ITM"):
    return _get("statisticsData.do", {"method": "getMeta", "type": kind, "orgId": org, "tblId": tbl})


def data(org: str, tbl: str, itm: str = "ALL", objs: dict | None = None, prd_se: str = "Y",
         start: str | None = None, end: str | None = None, newest: int | None = None):
    p = {"method": "getList", "orgId": org, "tblId": tbl, "itmId": itm, "prdSe": prd_se}
    for i in range(1, 9):
        p[f"objL{i}"] = (objs or {}).get(i, "")
    if newest:
        p["newEstPrdCnt"] = str(newest)
    else:
        p["startPrdDe"] = start
        p["endPrdDe"] = end
    return _get("Param/statisticsParameterData.do", p)
