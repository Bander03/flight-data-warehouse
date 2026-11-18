"""Checks the exported report PDF against the teacher's 2026-11-17 length notes.

  * the report has at most MAX_PAGES pages;
  * every worked MDX example of section 3.3 (question line to the end of its Result paragraph) stays on one page and
    takes at most half a page.

The PDF is exported from Word (report/build/FlightDW_Course_Project_Report.pdf, not in git), so run this after the
export:
    python tools/check_pdf_layout.py            # prints every example's span; exit 1 if a rule is broken
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "report" / "build" / "FlightDW_Course_Project_Report.pdf"
MAX_PAGES = 29
WORKED = ["01_drill_down_1", "02_roll_up_1", "03_slice_1", "04_dice_1", "05_rank_1", "06_top_n_1",
          "07_moving_avg_1", "08_running_total_1", "09_stopover_2"]
LEFT_MARGIN_PT = 80          # a question starts at the left margin; mentions inside running text are further right


def measure(pdf: Path = PDF) -> dict:
    doc = fitz.open(str(pdf))
    height = doc[0].rect.height
    marks = []                                   # (page, y_top, kind, y_bottom)
    for pno, page in enumerate(doc, 1):
        for name in WORKED:
            for r in page.search_for(name + "."):
                if r.x0 < LEFT_MARGIN_PT:
                    marks.append((pno, r.y0, name, r.y1))
        blocks = page.get_text("blocks")
        for r in page.search_for("Result."):
            ends = [b[3] for b in blocks if b[1] <= r.y0 + 1 and b[3] >= r.y1 - 1 and b[0] <= r.x0 + 1]
            marks.append((pno, r.y0, "Result.", max(ends) if ends else r.y1))
    marks.sort(key=lambda m: (m[0], m[1]))
    examples = {}
    for i, m in enumerate(marks):
        if m[2] == "Result." or m[2] in examples:
            continue
        end = next(x for x in marks[i + 1:] if x[2] == "Result.")
        one_page = end[0] == m[0]
        span = end[3] - m[1] if one_page else None
        examples[m[2]] = {"page": m[0], "one_page": one_page, "span_pt": span,
                          "share": span / height if one_page else None}
    return {"pages": doc.page_count, "page_height_pt": height, "examples": examples}


def problems(result: dict) -> list[str]:
    out = []
    if result["pages"] > MAX_PAGES:
        out.append(f"{result['pages']} pages (at most {MAX_PAGES})")
    for name in WORKED:
        ex = result["examples"].get(name)
        if ex is None:
            out.append(f"{name}: worked example not found in the PDF")
        elif not ex["one_page"]:
            out.append(f"{name}: runs over a page break (page {ex['page']})")
        elif ex["share"] > 0.5:
            out.append(f"{name}: {ex['share']:.0%} of a page (at most half)")
    return out


def main() -> int:
    if not PDF.exists():
        print(f"no PDF at {PDF}; build the report and export it from Word first")
        return 1
    result = measure()
    print(f"{result['pages']} pages")
    for name, ex in result["examples"].items():
        where = f"page {ex['page']}: {ex['span_pt']:.0f} pt = {ex['share']:.0%} of a page" if ex["one_page"] \
            else f"page {ex['page']}: over a page break"
        print(f"  {name:<20} {where}")
    found = problems(result)
    for p in found:
        print("PROBLEM:", p)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
