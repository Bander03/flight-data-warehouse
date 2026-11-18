"""Command line entry point: ``python -m fdw.cli``."""
import argparse
import sys

from . import config
from .load import SourceDataError
from .pipeline import run
from .validate import ValidationError


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):          # Chinese text on any console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="fdw.cli", description=__doc__)
    ap.add_argument("--raw-dir", default=str(config.RAW_DIR))
    ap.add_argument("--cache-dir", default=str(config.CACHE_DIR), help="folder of the cached CSV copies of the raw tables")
    ap.add_argument("--out-dir", default=str(config.OUT_DIR))
    ap.add_argument("--seed", type=int, default=config.SEED)
    args = ap.parse_args(argv)

    try:
        results = run(args.raw_dir, args.out_dir, args.seed, args.cache_dir)
    except SourceDataError as err:
        print(f"SOURCE DATA PROBLEM: {err}", file=sys.stderr)
        return 2
    except ValidationError as err:
        print(f"VALIDATION FAILED: {err}", file=sys.stderr)
        return 1
    for r in results:
        print(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}")
    passed = sum(r.passed for r in results)
    print(f"{passed}/{len(results)} rules passed; output written to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
