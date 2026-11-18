"""Cross-check of the MDX library (Plan 2, Task 6).

Compares every MDX result (mdx/results/<stem>.csv, written by tools/run_mdx.ps1) with the rows of its
T-SQL answer key (mdx/answers/<stem>.sql, run read-only on FlightDW through sqlcmd).

Usage (repo root):
    python tools/compare_results.py              # all 28 statements
    python tools/compare_results.py 05_rank_1    # selected stems
Prints one line per statement (MATCH or the differences) and exits 1 on any mismatch.

Matching rules
- Member: caption text must be equal (exact string; Chinese captions included).
- Value: math.isclose(result, key, rel_tol, abs_tol). The cube returns raw doubles, while several keys
  round with CAST(... AS DECIMAL(p, s)). The CLI therefore uses rel_tol = 1e-6 and an absolute floor of
  half a unit in the key's last decimal place (s = 2 -> 0.005, s = 3 -> 0.0005, s = 4 -> 0.00005),
  never more than 0.005: exactly the rounding error the key can introduce and no more. This is tighter
  than the plan's default (rel 1e-3, abs 0.005), which the key's own rounding never needs.
- Row order is ignored for unranked statements (rows matched by Member); for ranked statements
  (05_rank_*, 06_top_n_*) Rank, Member and Value must match row by row in order.
- Extra or missing members are reported by name.
"""
from __future__ import annotations

import csv
import math
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MDX_DIR = REPO / "mdx"
RESULTS = MDX_DIR / "results"
ANSWERS = MDX_DIR / "answers"
INSTANCE = r"localhost\SQLEXPRESS"
RANKED = ("05_rank", "06_top_n")
DEFAULT_REL_TOL = 1e-6
MAX_ABS_TOL = 0.005


def load_result(result_csv: Path) -> list[dict]:
    """Rows of a runner CSV (UTF-8, with or without BOM) as dicts keyed by the header."""
    with open(result_csv, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def parse_sqlcmd(out: str) -> list[dict]:
    """Rows of the first result set of `sqlcmd -W -s <tab>` text output."""
    lines = out.lstrip("﻿").splitlines()
    if len(lines) < 2:
        raise ValueError(f"no result set in sqlcmd output:\n{out}")
    columns = [c.strip() for c in lines[0].split("\t")]
    if set(lines[1].replace("\t", "")) - {"-"}:
        raise ValueError(f"unexpected sqlcmd output:\n{out}")
    rows = []
    for line in lines[2:]:
        if not line.strip():
            break                                   # a blank line ends the result set
        # strip ASCII spaces only: U+3000 or NBSP at the end of a Member is a real difference
        parts = [p.strip(" ") for p in line.split("\t")]
        if len(parts) != len(columns):
            raise ValueError(f"{len(parts)} fields, expected {columns}: {line!r}")
        rows.append(dict(zip(columns, parts)))
    return rows


def _num(text: str) -> float | None:
    text = (text or "").strip()
    if text == "" or text.upper() == "NULL":
        return None
    return float(text)


def _close(a: float | None, b: float | None, rel_tol: float, abs_tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def compare(result_csv: Path, answer_rows: list[dict], ranked: bool,
            rel_tol: float = 1e-3, abs_tol: float = 0.005) -> list[str]:
    """Difference messages between an MDX result CSV and the answer-key rows (empty list = match).

    answer_rows are dicts of STRINGS keyed `Member`, `Value` (and `Rank` first when ranked), exactly
    as parse_sqlcmd returns them from the key's text output. They stay text on purpose: the CLI
    derives the absolute tolerance from the number of decimals the key prints (key_abs_tol), which a
    float would lose. Raises KeyError if the result CSV lacks a required column.
    """
    stem = Path(result_csv).stem
    got = load_result(result_csv)
    need = ("Rank", "Member", "Value") if ranked else ("Member", "Value")
    for r in got:
        missing = [c for c in need if r.get(c) is None]
        if missing:
            raise KeyError(f"result CSV has no column(s) {missing}")
    diffs: list[str] = []
    for side, rows in (("MDX result", got), ("answer key", answer_rows)):
        seen, dups = set(), []
        for r in rows:
            if r["Member"] in seen and r["Member"] not in dups:
                dups.append(r["Member"])
            seen.add(r["Member"])
        for d in dups:
            diffs.append(f"{stem}: duplicate member {d!r} in the {side}")
    if ranked:
        for i in range(max(len(got), len(answer_rows))):
            g = got[i] if i < len(got) else None
            k = answer_rows[i] if i < len(answer_rows) else None
            if g is None:
                diffs.append(f"{stem}: row {i + 1} missing member {k['Member']!r} (key rank {k['Rank']}, value {k['Value']})")
                continue
            if k is None:
                diffs.append(f"{stem}: row {i + 1} extra member {g['Member']!r} (rank {g['Rank']}, value {g['Value']})")
                continue
            if g["Member"] != k["Member"]:
                diffs.append(f"{stem}: row {i + 1} member {g['Member']!r}, key has {k['Member']!r}")
            if _num(g["Rank"]) != _num(k["Rank"]):
                diffs.append(f"{stem}: row {i + 1} ({k['Member']!r}) Rank {g['Rank']}, key {k['Rank']}")
            if not _close(_num(g["Value"]), _num(k["Value"]), rel_tol, abs_tol):
                diffs.append(f"{stem}: row {i + 1} ({g['Member']!r}) Value {g['Value']}, key {k['Value']}")
        return diffs

    got_map = {r["Member"]: r["Value"] for r in got}
    key_map = {r["Member"]: r["Value"] for r in answer_rows}
    for member, value in key_map.items():
        if member not in got_map:
            diffs.append(f"{stem}: missing member {member!r} (key value {value})")
        elif not _close(_num(got_map[member]), _num(value), rel_tol, abs_tol):
            diffs.append(f"{stem}: {member!r} Value {got_map[member]}, key {value}")
    for member, value in got_map.items():
        if member not in key_map:
            diffs.append(f"{stem}: extra member {member!r} (value {value})")
    return diffs


def key_abs_tol(answer_rows: list[dict]) -> float:
    """Half a unit in the last decimal place the key shows (its rounding error), capped at 0.005."""
    scale = 0
    for r in answer_rows:
        v = (r.get("Value") or "").strip()
        if "." in v and "e" not in v.lower():
            scale = max(scale, len(v.split(".", 1)[1]))
    if scale == 0:
        return MAX_ABS_TOL                          # integer keys: exact, any floor below 1 works
    return min(MAX_ABS_TOL, 0.5 * 10 ** -scale + 1e-12)


def run_answer_key(sql_file: Path, sqlcmd: str) -> list[dict]:
    cmd = [sqlcmd, "-S", INSTANCE, "-E", "-b", "-d", "FlightDW", "-f", "65001",
           "-W", "-s", "\t", "-i", str(sql_file)]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)    # list argv, no shell
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise RuntimeError(f"sqlcmd exit {proc.returncode}: {out}{proc.stderr.decode('utf-8', 'replace')}")
    return parse_sqlcmd(out)


def check(stems: list[str], sqlcmd: str, verbose: bool = False) -> dict[str, list[str]]:
    """{stem: difference messages} (empty list = MATCH) for the given stems; never raises per stem."""
    status: dict[str, list[str]] = {}
    for stem in stems:
        result_csv = RESULTS / f"{stem}.csv"
        if not result_csv.exists():
            status[stem] = [f"no result file mdx/results/{stem}.csv (run tools/run_mdx.ps1)"]
        else:
            try:
                rows = run_answer_key(ANSWERS / f"{stem}.sql", sqlcmd)
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                status[stem] = [f"answer key failed: {exc}"]
            else:
                tol = key_abs_tol(rows)
                try:
                    status[stem] = compare(result_csv, rows, stem.startswith(RANKED), DEFAULT_REL_TOL, tol)
                except (KeyError, ValueError, csv.Error) as exc:
                    status[stem] = [f"malformed result CSV mdx/results/{stem}.csv: {exc}"]
                if verbose and not status[stem]:
                    print(f"{stem}: MATCH ({len(rows)} rows, abs_tol {tol:g})")
        if verbose and status[stem]:
            print(f"{stem}: MISMATCH")
            for d in status[stem]:
                print(f"    {d}")
    return status


def summary_line(status: dict[str, list[str]]) -> str:
    ok = sum(1 for d in status.values() if not d)
    return f"{ok} of {len(status)} statements match their answer keys"


def main(argv: list[str]) -> int:
    sqlcmd = shutil.which("sqlcmd")
    if sqlcmd is None:
        print("ERROR: sqlcmd is not on PATH")
        return 1
    stems = argv or sorted(p.stem for p in MDX_DIR.glob("*.mdx"))
    status = check(stems, sqlcmd, verbose=True)
    print(summary_line(status))
    return 1 if any(status.values()) else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
