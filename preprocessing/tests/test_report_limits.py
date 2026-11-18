"""Guide #4 limits on code in the report: a code listing in the body is at most one third of an A4 page (A4 = 842 pt, so
281 pt of height), and the warehouse creation statements (appendix A) are at most one third of the whole report."""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SECTIONS = REPO / "report" / "sections"
ONE_THIRD_PAGE_PT = 842 / 3
CODE_PT, LINE_FACTOR = 10.5, 1.15
CHARS_PER_LINE = 92          # Times New Roman 10.5 pt over a 16 cm text width minus the 0.6 cm indent


def _body_blocks():
    out = []
    for f in sorted(SECTIONS.glob("0*.md")):
        if f.name.startswith("07"):
            continue
        block, start = None, 0
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("```"):
                if block is None:
                    block, start = [], i
                else:
                    out.append((f"{f.name}:{start}", block))
                    block = None
            elif block is not None:
                block.append(line)
    return out


def _height_pt(lines):
    rows = sum(max(1, -(-len(l) // CHARS_PER_LINE)) for l in lines)       # wrapped lines
    return rows * CODE_PT * LINE_FACTOR


@pytest.mark.parametrize("where,lines", _body_blocks(), ids=lambda v: v if isinstance(v, str) else "")
def test_body_code_block_within_one_third_of_a_page(where, lines):
    assert _height_pt(lines) <= ONE_THIRD_PAGE_PT, f"{where}: about {_height_pt(lines):.0f} pt, limit {ONE_THIRD_PAGE_PT:.0f} pt"


def test_there_are_code_blocks_to_check():
    assert len(_body_blocks()) >= 10          # one full MDX example per OLAP operation (9) plus the creation excerpt


def test_creation_statements_below_one_third_of_the_report():
    """Appendix A (the SQL scripts, attached because they are long) is counted in full as creation statements.
    Appendix B (the complete MDX statements) is excluded: it is a separate allowance (the course guide lets the
    complete MDX text go to an appendix), not part of the "creation statements <= 1/3 of the report" rule."""
    appendix = (SECTIONS / "07_appendix.md").read_text(encoding="utf-8")
    included = [REPO / m.group(1) for m in re.finditer(r"\{\{include:\s*(.+?)\s*\}\}", appendix) if m.group(1).endswith(".sql")]
    code_lines = sum(max(1, -(-len(l) // CHARS_PER_LINE)) for p in included
                     for l in p.read_text(encoding="utf-8-sig").splitlines())
    appendix_pages = 1.3 * code_lines * CODE_PT * LINE_FACTOR / (842 - 2 * 71)     # 2.5 cm margins, 30 % safety (measured: 14 pages)
    body = [p.read_text(encoding="utf-8") for p in SECTIONS.glob("0*.md") if not p.name.startswith("07")]
    body_pages = (sum(len(t) for t in body) / 3300                                  # text
                  + 0.45 * sum(t.count("![") for t in body)                         # figures (measured: about 0.4 page each)
                  + 0.2 * sum(len(re.findall(r"^\*\*Table N\*\*", t, re.M)) for t in body))   # tables
    share = appendix_pages / (appendix_pages + body_pages)
    assert share < 1 / 3, f"estimated share of the creation statements: {share:.0%} (measured on the PDF: 3 of 29 pages = 10 %)"


FUNCTIONS = SECTIONS / "03_3_functions.md"
STATEMENTS = sorted(p.stem for p in (REPO / "mdx").glob("*.mdx"))
WORKED = ["01_drill_down_1", "02_roll_up_1", "03_slice_1", "04_dice_1", "05_rank_1", "06_top_n_1",
          "07_moving_avg_1", "08_running_total_1", "09_stopover_2"]


def test_every_statement_has_its_screenshot_in_section_3_3():
    """Guide #1 item 7 asks for running-result screenshots of the queries: all 28, not one per operation."""
    text = FUNCTIONS.read_text(encoding="utf-8")
    assert len(STATEMENTS) == 28
    for stem in STATEMENTS:
        shot = f"M{stem[:2]}.{stem.rsplit('_', 1)[1]}.jpg"
        assert f"`{stem}`.](../figures/{shot})" in text, f"no screenshot of {stem} in section 3.3"
        assert (REPO / "report" / "figures" / shot).exists()


def test_every_worked_example_is_kept_on_one_page():
    """Each full example (question to Result) sits inside a {{keep}} block, with its operation heading, so it never runs
    over a page break and the heading never stays alone at the foot of a page."""
    text = FUNCTIONS.read_text(encoding="utf-8")
    blocks = re.findall(r"\{\{keep\}\}(.*?)\{\{end-keep\}\}", text, re.S)
    for stem in WORKED:
        inside = [b for b in blocks if re.search(rf"^\*\*{stem}\.\*\*", b, re.M)]
        assert len(inside) == 1, f"{stem} is not wrapped in one keep block"
        assert "```" in inside[0] and "*Result.*" in inside[0] and f"`{stem}`.](../figures/" in inside[0]


def _pdf_is_current(pdf):
    sources = list(SECTIONS.glob("*.md")) + list((REPO / "report" / "figures").glob("*.jpg")) + \
        [REPO / "tools" / "build_report.py"]
    return pdf.exists() and pdf.stat().st_mtime >= max(p.stat().st_mtime for p in sources)


def test_exported_pdf_meets_page_and_half_page_limits():
    """Teacher's 2026-11-17 note: one MDX example within half a page, and the report kept short (team cap 29 pages).
    Needs the PDF exported from Word after the last change (report/build/, not in git)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_pdf_layout", REPO / "tools" / "check_pdf_layout.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not _pdf_is_current(mod.PDF):
        pytest.skip("no PDF exported from Word after the last change of the report sources")
    result = mod.measure()
    assert mod.problems(result) == []
    assert set(result["examples"]) == set(WORKED)
