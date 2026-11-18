"""새로 만든 src/data/*.json을 검증한다: python etl/validate.py [--baseline REF] [--stamp] [--force]

KOSIS가 빈 표를 주거나 표 ID·단위가 바뀌면 ETL은 오류 없이 엉뚱한 숫자를 만들 수 있다.
자동 갱신이 그런 숫자를 그대로 배포하지 않도록 두 단계로 확인한다.

1. 고정 규칙: 지역 수, 핵심 지표의 상식적인 범위 (RULES)
2. 직전 버전과 비교 (기본: git HEAD)
   - 직전에 있던 키·지역(id)이 사라졌는지
   - 숫자였던 값이 null·문자열·NaN으로 바뀌었는지
   - 숫자 값 중 50% 넘게 바뀐 비율이 5%를 넘는지

하나라도 걸리면 종료 코드 1. --stamp를 주면 통과했고 데이터가 바뀌었을 때
src/data/updated.json에 갱신일을 적는다(사이트 하단 '자료 갱신' 표시).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
SKIP = {"geo.json", "updated.json"}  # geo는 ETL 갱신 대상이 아님

DRIFT_REL = 0.5        # 이만큼 넘게 바뀌면 '큰 변화'
DRIFT_SHARE = 0.05     # 큰 변화가 숫자 값 중 이 비율을 넘으면 실패
LIST_SHRINK = 0.8      # 길이 5 이상 목록이 이 비율 미만으로 줄면 실패
ID_KEYS = ("id", "key", "code", "year")


# ── 고정 규칙 ──────────────────────────────────────────────
# (경로, 최소, 최대) — 숫자면 값 범위, 목록·사전이면 길이 범위
RULES: dict[str, list[tuple[str, float, float]]] = {
    "korea": [
        ("headline.pop2025", 45e6, 56e6),
        ("headline.tfrLatest", 0.5, 1.6),
        ("headline.birthsLatest", 150_000, 450_000),
        ("headline.oldShare2025", 0.15, 0.35),
        ("headline.pop2050.mid", 30e6, 56e6),
        ("sidos", 17, 17),
    ],
    "dongne": [("regions", 220, 240)],
    "commerce": [("regions", 220, 240)],
    "school": [("regions", 235, 260), ("backtest.n", 200, 260)],
    "wage": [("regions", 17, 17), ("national", 10, 40), ("industries", 10, 25)],
    "housing": [("regions", 18, 20), ("seoulZones", 5, 5)],
    "industry": [("industries", 20, 30), ("summary.retire10yShare", 0.1, 0.7)],
    "retire": [
        ("headline.lifeExp65Male", 15, 25),
        ("headline.lifeExp65Female", 18, 30),
        ("headline.pensionMean", 300_000, 2_000_000),
    ],
    "me": [("salary.pts", 10, 30), ("salary.n", 15e6, 30e6)],
}


def get(obj, path: str):
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def check_rules(name: str, data) -> list[str]:
    errors = []
    for path, lo, hi in RULES.get(name, []):
        try:
            v = get(data, path)
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append(f"`{path}` 없음")
            continue
        n = len(v) if isinstance(v, (list, dict)) else v
        if not isinstance(n, (int, float)) or isinstance(n, bool) or not lo <= n <= hi:
            what = "개수" if isinstance(v, (list, dict)) else "값"
            errors.append(f"`{path}` {what} {n!r} — 허용 범위 {lo:g}~{hi:g}")
    return errors


# ── 직전 버전과 비교 ───────────────────────────────────────
def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def id_key(items: list) -> str | None:
    """목록의 원소를 짝지을 키: 모든 원소에 있고 값이 겹치지 않는 첫 키."""
    if not items or not all(isinstance(x, dict) for x in items):
        return None
    for k in ID_KEYS:
        vals = [x.get(k) for x in items]
        if None not in vals and len(set(map(str, vals))) == len(vals):
            return k
    return None


class Diff:
    def __init__(self):
        self.missing: list[str] = []
        self.broken: list[str] = []
        self.shrunk: list[str] = []
        self.numbers = 0
        self.drift: list[tuple[float, str, float, float]] = []

    def walk(self, old, new, path: str):
        if isinstance(old, dict):
            if not isinstance(new, dict):
                self.broken.append(f"`{path}` 사전 → {type(new).__name__}")
                return
            for k, v in old.items():
                p = f"{path}.{k}" if path else k
                if k not in new:
                    self.missing.append(f"`{p}`")
                else:
                    self.walk(v, new[k], p)
        elif isinstance(old, list):
            if not isinstance(new, list):
                self.broken.append(f"`{path}` 목록 → {type(new).__name__}")
                return
            k = id_key(old)
            if k and id_key(new) == k:
                by = {str(x[k]): x for x in new}
                for x in old:
                    p = f"{path}[{k}={x[k]}]"
                    if str(x[k]) not in by:
                        self.missing.append(f"`{p}`")
                    else:
                        self.walk(x, by[str(x[k])], p)
            else:
                if len(old) >= 5 and len(new) < len(old) * LIST_SHRINK:
                    self.shrunk.append(f"`{path}` {len(old)} → {len(new)}개")
                for i, (a, b) in enumerate(zip(old, new)):
                    self.walk(a, b, f"{path}[{i}]")
        elif is_num(old):
            if not is_num(new) or not math.isfinite(new):
                self.broken.append(f"`{path}` {old!r} → {new!r}")
                return
            self.numbers += 1
            if old != 0:
                rel = abs(new - old) / abs(old)
                if rel > DRIFT_REL:
                    self.drift.append((rel, path, old, new))


def baseline(ref: str, name: str):
    try:
        out = subprocess.run(
            ["git", "show", f"{ref}:src/data/{name}.json"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    return json.loads(out)


def reject_constant(c):
    raise ValueError(f"JSON에 {c} 포함")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="HEAD", help="비교할 git 리비전 (기본 HEAD)")
    ap.add_argument("--stamp", action="store_true", help="통과·변경 시 updated.json 기록")
    ap.add_argument("--force", action="store_true", help="오류를 보고만 하고 통과 처리")
    ap.add_argument("--data", type=Path, default=DATA, help="검증할 폴더 (기본 src/data)")
    args = ap.parse_args()
    data_dir = args.data

    report = ["## 데이터 검증", ""]
    failed = False
    changed = []

    for f in sorted(data_dir.glob("*.json")):
        if f.name in SKIP:
            continue
        name = f.stem
        errors: list[str] = []
        warns: list[str] = []
        raw = f.read_bytes()
        try:
            new = json.loads(raw, parse_constant=reject_constant)
        except ValueError as e:
            errors.append(f"읽을 수 없음: {e}")
            new = None

        if new is not None:
            errors += check_rules(name, new)
            old = baseline(args.baseline, name)
            if old is None:
                warns.append(f"{args.baseline}에 직전 버전이 없어 비교 생략")
            elif old != new:
                changed.append(name)
                d = Diff()
                d.walk(old, new, "")
                if d.missing:
                    errors.append(f"사라진 항목 {len(d.missing)}개: " + ", ".join(d.missing[:8]))
                if d.broken:
                    errors.append(f"깨진 값 {len(d.broken)}개: " + ", ".join(d.broken[:8]))
                if d.shrunk:
                    errors.append("줄어든 목록: " + ", ".join(d.shrunk[:8]))
                share = len(d.drift) / d.numbers if d.numbers else 0
                if d.drift:
                    top = sorted(d.drift, reverse=True)[:5]
                    detail = ", ".join(f"`{p}` {a:g}→{b:g}" for _, p, a, b in top)
                    msg = f"50% 넘게 바뀐 숫자 {len(d.drift)}/{d.numbers}개 ({share:.1%}): {detail}"
                    (errors if share > DRIFT_SHARE else warns).append(msg)

        status = "❌" if errors else ("⚠️" if warns else "✅")
        state = "읽기 실패" if new is None else ("변경" if name in changed else "동일")
        report.append(f"- {status} **{name}** ({state})")
        report += [f"  - 오류: {e}" for e in errors]
        report += [f"  - 참고: {w}" for w in warns]
        failed |= bool(errors)

    report.append("")
    if failed and args.force:
        report.append("**오류가 있지만 --force로 반영합니다.**")
        failed = False
    if failed:
        report.append("**실패** — 데이터를 커밋·배포하지 않습니다. 정상적인 큰 변화라면 "
                      "`workflow_dispatch`에서 `skip_validation`을 켜고 다시 실행하세요.")
    if not failed and changed and args.stamp:
        stamp = {"updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat(),
                 "modules": changed}
        (data_dir / "updated.json").write_text(json.dumps(stamp, ensure_ascii=False) + "\n")
        report.append(f"통과 — 갱신일 {stamp['updated']} 기록 ({', '.join(changed)})")
    elif not failed:
        report.append("통과" + ("" if changed else " — 바뀐 데이터 없음"))

    text = "\n".join(report)
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
