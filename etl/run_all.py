"""전체 ETL 실행: python etl/run_all.py [모듈 ...]"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data"
PICKLE = ROOT / "data" / "raw" / "pop.pkl"


def population():
    import pop
    if PICKLE.exists() and "--fresh" not in sys.argv:
        return pickle.loads(PICKLE.read_bytes())
    r = pop.run()
    PICKLE.parent.mkdir(parents=True, exist_ok=True)
    PICKLE.write_bytes(pickle.dumps(r))
    return r


def write(name: str, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    print(f"  → {p.relative_to(ROOT)} ({p.stat().st_size/1024:.0f} KB)")


MODULES = {}


def module(fn):
    MODULES[fn.__name__] = fn
    return fn


@module
def school():
    import build_school
    write("school", build_school.build(population()))


@module
def wage():
    import build_wage
    write("wage", build_wage.build())


@module
def housing():
    import build_housing
    write("housing", build_housing.build())


@module
def industry():
    import build_industry
    write("industry", build_industry.build())


@module
def commerce():
    import build_commerce
    write("commerce", build_commerce.build(population()))


@module
def retire():
    import build_retire
    write("retire", build_retire.build())


@module
def korea():
    import build_korea
    write("korea", build_korea.build(population()))


@module
def dongne():
    import build_dongne
    write("dongne", build_dongne.build(population()))


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(MODULES)
    for n in names:
        print(f"[{n}]")
        MODULES[n]()


if __name__ == "__main__":
    main()
