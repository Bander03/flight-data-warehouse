"""Data layer of the local website: the 28 MDX analyses, their saved results, the match badge and the overview.

Everything is read from files committed in the repository (mdx/*.mdx, mdx/answers/*.sql, mdx/results/*.csv,
mdx/results/SUMMARY.md), so the website works without the cube. Nothing here is typed by hand: the numbers
shown come from these files and from data/processed (or its committed snapshot web/overview_snapshot.json).

    python -m web.data --write-snapshot     # refresh web/overview_snapshot.json from data/processed
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MDX_DIR = REPO / "mdx"
ANSWERS_DIR = MDX_DIR / "answers"
RESULTS_DIR = MDX_DIR / "results"
SNAPSHOT = REPO / "web" / "overview_snapshot.json"
PROFILE_SNAPSHOT = REPO / "web" / "profile_snapshot.json"
PROCESSED = REPO / "data" / "processed"
FIGURES_DIR = REPO / "report" / "figures"
COVER = REPO / "report" / "sections" / "00_cover.md"
REPORT_PDF = REPO / "report" / "build" / "FlightDW_Course_Project_Report.pdf"

# (stem prefix, group title) in the order of the report
OPERATIONS = [
    ("01_drill_down", "Drill down"), ("02_roll_up", "Roll up"), ("03_slice", "Slice"), ("04_dice", "Dice"),
    ("05_rank", "Rank"), ("06_top_n", "Top N"), ("07_moving_avg", "Moving average"),
    ("08_running_total", "Running total"), ("09_stopover", "Stopover analysis"),
]
RANKED_PREFIXES = ("05_rank", "06_top_n")


def list_stems() -> list[str]:
    return sorted(p.stem for p in MDX_DIR.glob("*.mdx"))


def is_stem(stem: str) -> bool:
    """True only for the exact name of an existing statement (no path, no extension, no encoding tricks)."""
    return isinstance(stem, str) and stem in set(list_stems())


def _group(stem: str) -> str:
    for prefix, title in OPERATIONS:
        if stem.startswith(prefix):
            return title
    return "Other"


def _header(text: str, key: str) -> str:
    m = re.search(rf"^--\s*{key}:\s*(.*)$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def read_result_csv(path: Path) -> tuple[list[str], list[dict]]:
    """(columns, rows) of a runner CSV; Value (and Rank) become numbers, Member stays text."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = []
        for r in reader:
            row = {"Member": r["Member"], "Value": float(r["Value"])}
            if "Rank" in r:
                row = {"Rank": int(float(r["Rank"])), **row}
            rows.append(row)
    return columns, rows


def load_statement(stem: str) -> dict:
    if not is_stem(stem):
        raise ValueError(f"unknown statement: {stem!r}")
    mdx = (MDX_DIR / f"{stem}.mdx").read_text(encoding="utf-8-sig")
    answer = ANSWERS_DIR / f"{stem}.sql"
    columns, rows = read_result_csv(RESULTS_DIR / f"{stem}.csv")
    return {
        "stem": stem,
        "group": _group(stem),
        "operation": _header(mdx, "Operation"),
        "question": _header(mdx, "Question"),
        "measure": _header(mdx, "Measure"),
        "answer_key_path": _header(mdx, "Answer key"),
        "mdx": mdx.strip(),
        "answer_sql": answer.read_text(encoding="utf-8-sig").strip() if answer.exists() else "",
        "columns": columns,
        "ranked": stem.startswith(RANKED_PREFIXES),
        "rows": rows,
    }


def list_statements() -> list[dict]:
    out = []
    for stem in list_stems():
        s = load_statement(stem)
        out.append({k: s[k] for k in ("stem", "group", "operation", "question", "measure")} | {"row_count": len(s["rows"])})
    return out


def match_summary() -> dict:
    """The cross-check outcome written by tools/make_results_summary.py --compare ('28 of 28 statements match ...')."""
    text = (RESULTS_DIR / "SUMMARY.md").read_text(encoding="utf-8-sig")
    m = re.search(r"(\d+) of (\d+) statements match", text)
    if not m:
        return {"matched": None, "total": len(list_stems()), "text": "Cross-check not recorded in SUMMARY.md."}
    return {"matched": int(m.group(1)), "total": int(m.group(2)), "text": m.group(0)}


def _close(a: float, b: float, rel_tol: float, abs_tol: float) -> bool:
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def rows_equal(a: list[dict], b: list[dict], rel_tol: float = 1e-6, abs_tol: float = 0.005) -> list[str]:
    """Differences between two result row lists (empty list = equal). Ranked rows (with 'Rank') are compared in
    order, unranked rows by member; same rules as tools/compare_results.py."""
    diffs: list[str] = []
    if any("Rank" in r for r in a + b):
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else None
            y = b[i] if i < len(b) else None
            if x is None:
                diffs.append(f"row {i + 1}: extra member {y['Member']!r}")
            elif y is None:
                diffs.append(f"row {i + 1}: missing member {x['Member']!r}")
            else:
                if x["Member"] != y["Member"]:
                    diffs.append(f"row {i + 1}: member {y['Member']!r}, saved {x['Member']!r}")
                if x.get("Rank") != y.get("Rank"):
                    diffs.append(f"row {i + 1} ({x['Member']!r}): rank {y.get('Rank')}, saved {x.get('Rank')}")
                if not _close(x["Value"], y["Value"], rel_tol, abs_tol):
                    diffs.append(f"row {i + 1} ({x['Member']!r}): value {y['Value']}, saved {x['Value']}")
        return diffs
    ma = {r["Member"]: r["Value"] for r in a}
    mb = {r["Member"]: r["Value"] for r in b}
    for member, value in ma.items():
        if member not in mb:
            diffs.append(f"missing member {member!r} (saved value {value})")
        elif not _close(value, mb[member], rel_tol, abs_tol):
            diffs.append(f"{member!r}: value {mb[member]}, saved {value}")
    for member, value in mb.items():
        if member not in ma:
            diffs.append(f"extra member {member!r} (value {value})")
    return diffs


def _count_overview(processed_dir: Path) -> dict:
    import pandas as pd
    fact = pd.read_csv(processed_dir / "fact_flight_segment.csv", encoding="utf-8-sig")
    rows = lambda name: len(pd.read_csv(processed_dir / name, encoding="utf-8-sig"))  # noqa: E731
    # a direct segment has no transit airport (empty cell here, key 0 "No stopover" in the warehouse)
    airports = {int(v) for col in ("Departure_ariportID", "Landing_ariportID", "Transit_ariportID")
                for v in fact[col].dropna() if int(v) != 0}
    return {
        "segments": int(len(fact)),
        "passengers": int(fact["PassengerID"].nunique()),
        "stopover_segments": int(fact["Transit_ariportID"].notna().sum()),
        "airports_used": int(len(airports)),
        "airports": rows("dim_airport.csv"),
        "airlines": rows("dim_airline.csv"),
        "aircraft": rows("dim_plane.csv"),
        "dates": rows("dim_date.csv"),
        "total_revenue": int(fact["Price"].sum()),
        "total_mileage": int(fact["mileage"].sum()),
    }


def overview(processed_dir: Path = PROCESSED) -> dict:
    """Warehouse totals counted from the processed CSVs; the committed snapshot when they are not there."""
    processed_dir = Path(processed_dir)
    if (processed_dir / "fact_flight_segment.csv").exists():
        return _count_overview(processed_dir) | {"source": "data"}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")) | {"source": "snapshot"}


def screenshot_path(stem: str) -> Path | None:
    """The SSMS screenshot of a statement (report/figures/M01.1.jpg for 01_drill_down_1), None if there is none."""
    if not is_stem(stem):
        return None
    path = FIGURES_DIR / f"M{stem[:2]}.{stem.rsplit('_', 1)[1]}.jpg"
    return path if path.exists() else None


def _md_table(text: str, heading: str) -> list[list[str]]:
    """Body rows of the first pipe table under a '## heading' line."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not m:
        return []
    rows = [l.strip() for l in m.group(1).splitlines() if l.strip().startswith("|")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]


def _parse_profile(text: str) -> dict:
    rules = [{"rule": r[0], "before": r[1], "after": r[2], "detail_before": r[3], "detail_after": r[4]}
             for r in _md_table(text, "Guide #2 rules: before vs after")]
    counts = [{"measure": r[0], "before": r[1], "after": r[2]} for r in _md_table(text, "Counts")]
    return {"rules": rules, "counts": counts,
            "passed_before": sum(r["before"] == "PASS" for r in rules),
            "passed_after": sum(r["after"] == "PASS" for r in rules)}


def profile(processed_dir: Path = PROCESSED) -> dict:
    """Guide #2 rules before and after preprocessing; the committed snapshot when the profile file is not there."""
    path = Path(processed_dir) / "profile_before_after.md"
    if path.exists():
        return _parse_profile(path.read_text(encoding="utf-8-sig")) | {"source": "data"}
    return json.loads(PROFILE_SNAPSHOT.read_text(encoding="utf-8")) | {"source": "snapshot"}


def project() -> dict:
    """Course, group, team and teacher from the report's cover page, and whether the report PDF is built."""
    text = COVER.read_text(encoding="utf-8")
    field = lambda name: (re.search(rf"\*\*{name}:\*\*\s*(.+)", text) or [None, ""])[1].strip()  # noqa: E731
    table = [l.strip().strip("|").split("|") for l in text.splitlines() if l.strip().startswith("|")][2:]
    members = [{"name": r[0].replace("(group leader)", "").strip(), "leader": "(group leader)" in r[0]} for r in table]
    course = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE).group(1).strip()
    pdf = REPORT_PDF if REPORT_PDF.exists() else None
    return {"course": course, "project": field("Course project name"), "group": field("Group number"),
            "teacher": field("Teacher"), "date": field("Date"), "members": members,
            "report": {"available": pdf is not None, "pages": _pdf_pages(pdf) if pdf else None}}


def _pdf_pages(pdf: Path) -> int | None:
    try:
        import fitz
        with fitz.open(str(pdf)) as doc:
            return doc.page_count
    except Exception:          # PyMuPDF missing or the file is open in Word: the page count is optional
        return None


def main(argv: list[str]) -> int:
    if argv == ["--write-snapshot"]:
        counted = _count_overview(PROCESSED)
        SNAPSHOT.write_text(json.dumps(counted, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {SNAPSHOT}: {counted}")
        prof = _parse_profile((PROCESSED / "profile_before_after.md").read_text(encoding="utf-8-sig"))
        PROFILE_SNAPSHOT.write_text(json.dumps(prof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {PROFILE_SNAPSHOT}: {prof['passed_before']}/{len(prof['rules'])} -> {prof['passed_after']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
