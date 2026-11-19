"""공공데이터포털(data.go.kr) 오픈API 공용 도구 — 인증키, 호출(재시도·한도 감지), 월 계산.

인증키는 계정에 하나라 모든 API가 같은 키를 쓴다: DATA_GO_KR_API_KEY 또는 MOLIT_API_KEY (.env/환경변수).
일반 인증키(Decoding)를 권장하고, Encoding 키(%가 들어 있음)를 넣어도 그대로 쓴다.
하루 호출 한도는 API마다 따로다(2026-11 확인: 매매·전월세를 동시에 각 1만 회씩 사용).
"""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
KEY_NAMES = ("DATA_GO_KR_API_KEY", "MOLIT_API_KEY")


class Quota(Exception):
    """하루 호출 한도 초과: 이번 실행의 이 API 수집을 멈춘다."""


class Fatal(Exception):
    """키·활용신청 문제: 실행을 멈춘다."""


def api_key() -> str:
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        vals = dict(l.split("=", 1) for l in env.read_text().splitlines() if "=" in l and not l.startswith("#"))
        for name in KEY_NAMES:
            if vals.get(name, "").strip():
                return vals[name].strip()
    raise SystemExit(f"{' 또는 '.join(KEY_NAMES)}가 필요합니다 (.env 또는 환경변수). 공공데이터포털에서 활용신청 후 발급")


def url(base: str, params: dict) -> str:
    key = api_key()
    if "%" not in key:  # Decoding 키 → 인코딩
        key = urllib.parse.quote(key, safe="")
    return f"{base}?serviceKey={key}&{urllib.parse.urlencode(params)}"


def check_text(text: str) -> None:
    """포털 게이트웨이 공통 오류(한도·키)는 API 형식과 상관없이 같은 문구로 온다."""
    low = text[:2000].lower()
    if "limited_number_of_service_requests" in low or "rate limit" in low:
        raise Quota(" ".join(text[:300].split()))
    if "service_key_is_not_registered" in low or "unregistered" in low or "deadline_has_expired" in low:
        raise Fatal(" ".join(text[:300].split()))


def get(u: str, retries: int = 4, timeout: int = 60) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(u, timeout=timeout) as r:
                text = r.read().decode("utf-8", errors="replace")
            check_text(text)
            return text
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            check_text(body)
            if e.code == 429:
                raise Quota(f"HTTP 429 {body[:200]}")
            if e.code in (401, 403):
                raise Fatal(f"HTTP {e.code}: 키가 없거나 이 API를 활용신청하지 않았습니다. {body[:200]}")
            last = e
        except (Quota, Fatal):
            raise
        except Exception as e:  # 네트워크 오류 재시도
            last = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"요청 실패: {last}")


def today() -> date:
    return datetime.now(KST).date()


def months_between(first: str, last: str) -> list[str]:
    """first~last(YYYYMM, 포함), 최신 달부터."""
    y, m = int(last[:4]), int(last[4:])
    out = []
    while f"{y:04d}{m:02d}" >= first:
        out.append(f"{y:04d}{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def months(n: int, ref: date | None = None) -> list[str]:
    """현재 달 포함 최근 n+1개월, 최신 달부터."""
    ref = ref or today()
    y, m = ref.year, ref.month
    out = []
    for _ in range(n + 1):
        out.append(f"{y:04d}{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def month_end(ym: str) -> date:
    y, m = int(ym[:4]), int(ym[4:])
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
