"""Tests for tools/build_report.py (Markdown sections -> Word report with the guide #4 formatting)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from docx import Document

ROOT = Path(__file__).resolve().parents[2]
NL = chr(10)
BS = chr(92)
TOOL = ROOT / "tools" / "build_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_report", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_report"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def br():
    return _load()


@pytest.fixture()
def sections(tmp_path):
    d = tmp_path / "sections"
    d.mkdir()
    (d / "00_cover.md").write_text(
        "# Big Data Intelligent Management and Analysis\n\n## Course Project Report 2026\n\n"
        "**Group number:** 2\n\n| Name | Student ID |\n|---|---|\n| A B | 1 |\n",
        encoding="utf-8",
    )
    (d / "02_motivation.md").write_text(
        "# 2. Motivation\n\nPlain paragraph with **bold**, *italic* and `code` text. 中文测试。\n\n"
        "- first bullet\n- second bullet\n\n1. one\n2. two\n",
        encoding="utf-8",
    )
    (d / "03_data.md").write_text(
        "## 3.1 Data\n\n**Table N** A small table.\n\n| Col A | Col B |\n|---|---|\n| 1 | two |\n| 3 | four |\n\n"
        "```\nSELECT 1;\nSELECT 2;\n```\n\n![Figure N A picture.](pic.png)\n",
        encoding="utf-8",
    )
    # a tiny valid PNG (1x1)
    import base64

    (d / "pic.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
    return d


def test_build_creates_docx(br, sections, tmp_path):
    out = tmp_path / "out" / "report.docx"
    br.build(sections, out)
    assert out.exists() and out.stat().st_size > 0
    Document(str(out))  # opens without error


def test_cover_page_formatting(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    first = doc.paragraphs[0]
    assert first.text.startswith("Big Data Intelligent Management")
    assert first.runs[0].bold is True
    assert first.runs[0].font.size.pt == 18
    others = [p for p in doc.paragraphs[1:6] if p.text.strip()]
    assert others and all(r.font.size.pt == 16 for p in others for r in p.runs if r.text.strip())


def test_body_font_is_times_new_roman_11(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    para = next(p for p in doc.paragraphs if p.text.startswith("Plain paragraph"))
    for r in para.runs:
        assert r.font.name == "Times New Roman"
        assert r.font.size.pt == 11
    assert any(r.bold for r in para.runs) and any(r.italic for r in para.runs)


def test_page_numbers_in_footer(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    xml = doc.sections[0].footer._element.xml
    assert "PAGE" in xml


def test_table_rendered_with_header(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    tables = [t for t in doc.tables if t.cell(0, 0).text == "Col A"]
    assert len(tables) == 1
    t = tables[0]
    assert len(t.rows) == 3 and t.cell(2, 1).text == "four"
    assert all(r.bold for r in t.cell(0, 0).paragraphs[0].runs)


def test_table_caption_is_above_table(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    body = list(doc.element.body.iterchildren())
    cap_idx = next(i for i, e in enumerate(body) if e.tag.endswith("}p") and "Table 1" in "".join(e.itertext()))
    tbl_idx = next(i for i, e in enumerate(body) if e.tag.endswith("}tbl") and "Col A" in "".join(e.itertext()))
    assert cap_idx < tbl_idx


def test_figure_caption_is_below_picture(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    assert len(doc.inline_shapes) == 1
    body = list(doc.element.body.iterchildren())
    pic_idx = next(i for i, e in enumerate(body) if e.tag.endswith("}p") and e.xpath(".//*[local-name()='drawing']"))
    assert "".join(body[pic_idx + 1].itertext()).startswith("Figure 1 A picture.")


def test_code_block_uses_small_times_new_roman(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    code = [p for p in doc.paragraphs if p.text in ("SELECT 1;", "SELECT 2;")]
    assert len(code) == 2
    assert all(r.font.name == "Times New Roman" and r.font.size.pt == 10.5 for p in code for r in p.runs)


def test_lists_and_headings(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    styles = [p.style.name for p in doc.paragraphs]
    assert "List Bullet" in styles and "List Number" in styles
    assert any(p.text == "2. Motivation" and p.style.name.startswith("Heading") for p in doc.paragraphs)


def test_missing_image_is_reported_not_silently_dropped(br, tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "03_x.md").write_text("![Figure 1 nothing](nope.png)\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        br.build(d, tmp_path / "r.docx")


def test_placeholders_are_listed(br, tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "04_p.md").write_text("# 4\n\n*(write here)*\n\nDone text.\n", encoding="utf-8")
    found = br.find_placeholders(d)
    assert len(found) == 1 and "04_p.md" in found[0] and "write here" in found[0]


def test_section_order_follows_file_names(br, sections, tmp_path):
    out = tmp_path / "report.docx"
    br.build(sections, out)
    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs]
    assert texts.index("2. Motivation") < texts.index("3.1 Data")


# ---------------------------------------------------------------- caption numbering (N tokens)
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture()
def numbered(tmp_path):
    import base64

    d = tmp_path / "num"
    d.mkdir()
    (d / "pic.png").write_bytes(base64.b64decode(PNG))
    (d / "03_a.md").write_text(
        "## A\n\n![Figure N First picture.](pic.png)\n\n**Table N** First table.\n\n| H | I |\n|---|---|\n| 1 | 2 |\n\n"
        "*(Screenshot X1 to insert here as Figure N: a placeholder.)*\n",
        encoding="utf-8")
    (d / "03_b.md").write_text(
        "## B\n\n**Table N** Second table.\n\n| J | K |\n|---|---|\n| 3 | 4 |\n\n"
        "```\n**Table N** inside code is not a caption\n```\n\n![Figure N Last picture.](pic.png)\n",
        encoding="utf-8")
    return d


def _texts(doc):
    return [p.text for p in doc.paragraphs]


def test_captions_numbered_in_document_order_with_separate_counters(br, numbered, tmp_path):
    out = tmp_path / "r.docx"
    br.build(numbered, out)
    texts = _texts(Document(str(out)))
    caps = [t for t in texts if t.startswith(("Table ", "Figure ", "(Screenshot"))]
    assert caps == ["Figure 1 First picture.", "Table 1 First table.",
                    "(Screenshot X1 to insert here as Figure 2: a placeholder.)",
                    "Table 2 Second table.", "Figure 3 Last picture."]
    assert "**Table N** inside code is not a caption" in texts      # code blocks are left alone


def test_every_table_has_its_caption_directly_above(br, numbered, tmp_path):
    out = tmp_path / "r.docx"
    br.build(numbered, out)
    body = list(Document(str(out)).element.body.iterchildren())
    tables = [i for i, e in enumerate(body) if e.tag.endswith("}tbl")]
    assert len(tables) == 2
    for n, i in enumerate(tables, 1):
        assert "".join(body[i - 1].itertext()).startswith(f"Table {n} ")


def test_uncaptioned_table_is_reported(br, tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "00_cover.md").write_text("# Cover\n\n| Name | ID |\n|---|---|\n| A | 1 |\n", encoding="utf-8")
    (d / "03_x.md").write_text(
        "## X\n\n**Table N** Captioned.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "Some text.\n\n| C | D |\n|---|---|\n| 3 | 4 |\n\n**Table 3.2** Fixed number.\n\n| E | F |\n|---|---|\n| 5 | 6 |\n",
        encoding="utf-8")
    problems = br.find_caption_problems(d)
    assert len(problems) == 2                     # the cover table needs no caption
    assert "03_x.md:11" in problems[0] and "no 'Table N' caption" in problems[0]
    assert "03_x.md:15" in problems[1] and "fixed number" in problems[1]


def test_real_report_sections_have_no_caption_problems(br):
    assert br.find_caption_problems() == []


# ---------------------------------------------------------------- instruction paragraphs
@pytest.fixture()
def instructed(tmp_path):
    d = tmp_path / "ins"
    d.mkdir()
    (d / "04_p.md").write_text(
        "# 4. Problems\n\n*(Instruction: each member writes their own part.)*\n\n## Member\n\nReal text.\n\n[1] \n",
        encoding="utf-8")
    return d


def test_instruction_paragraphs_are_not_printed_by_default(br, instructed, tmp_path):
    out = tmp_path / "r.docx"
    br.build(instructed, out)
    texts = _texts(Document(str(out)))
    assert "Real text." in texts
    assert not any("Instruction" in t for t in texts)


def test_keep_instructions_prints_them(br, instructed, tmp_path):
    out = tmp_path / "r.docx"
    br.build(instructed, out, keep_instructions=True)
    assert any("Instruction: each member" in t for t in _texts(Document(str(out))))


def test_check_lists_instructions_and_empty_references(br, instructed):
    found = br.find_instructions(instructed)
    assert len(found) == 2
    assert "04_p.md:3" in found[0] and "Instruction" in found[0]
    assert "04_p.md:9" in found[1] and "empty reference" in found[1]


def test_check_exit_code_and_listing(br, instructed, monkeypatch, capsys):
    monkeypatch.setattr(br, "SECTIONS_DIR", instructed)
    assert br.main(["--check"]) == 1
    assert "instruction" in capsys.readouterr().out.lower()


def test_include_directive_renders_file_as_code(br, tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "07_app.md").write_text("# Appendix\n\n{{include: sql/01_create_db.sql}}\n", encoding="utf-8")
    out = tmp_path / "r.docx"
    br.build(d, out)
    doc = Document(str(out))
    code = [p for p in doc.paragraphs if p.runs and p.runs[0].font.size and p.runs[0].font.size.pt == 10.5]
    assert len(code) >= 5
    assert any("FlightDW" in p.text for p in code)


def test_include_of_missing_file_fails_loudly(br, tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "07_app.md").write_text("{{include: sql/does_not_exist.sql}}\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        br.build(d, tmp_path / "r.docx")


def test_escaped_pipe_stays_inside_the_table_cell(br, tmp_path):
    d = tmp_path / "sections"
    d.mkdir()
    text = "**Table N** Pipes." + NL * 2 + "| Member | Value |" + NL + "|---|---|" + NL + "| 5 " + BS + "| C | 4 |" + NL
    (d / "01.md").write_text(text, encoding="utf-8")
    out = tmp_path / "r.docx"
    br.build(d, out)
    t = [t for t in Document(str(out)).tables if t.cell(0, 0).text == "Member"][0]
    assert len(t.columns) == 2 and t.cell(1, 0).text == "5 | C" and t.cell(1, 1).text == "4"


def test_wide_table_gets_content_proportional_columns_and_smaller_font(br, tmp_path):
    """A 15-column table with equal column widths wrapped numbers mid-value ('257' / '286'): columns must be sized by
    their content, the table must stay inside the 16 cm text width, and a table with more than 10 columns uses 9 pt."""
    d = tmp_path / "sections"
    d.mkdir()
    cols = ["c%d" % i for i in range(15)]
    vals = ["2021-06-11"] + ["7"] * 14
    text = ("**Table N** Wide." + NL * 2 + "| " + " | ".join(cols) + " |" + NL + "|" + "---|" * 15 + NL
            + "| " + " | ".join(vals) + " |" + NL)
    (d / "01.md").write_text(text, encoding="utf-8")
    out = tmp_path / "r.docx"
    br.build(d, out)
    t = [t for t in Document(str(out)).tables if t.cell(0, 0).text == "c0"][0]
    widths = [t.cell(1, j).width for j in range(15)]
    assert widths[0] > 1.5 * widths[1], "the date column must be wider than a one-digit column"
    assert sum(widths) <= br.Cm(16.05), "the table must fit the text width"
    assert t.cell(1, 0).paragraphs[0].runs[0].font.size == br.Pt(br.WIDE_TABLE_PT)
    assert t._tbl.tblPr.find(br.qn("w:tblCellMar")) is not None, "a wide table gets slimmer cell padding"
    # a narrow table keeps the normal table font
    (d / "01.md").write_text("**Table N** Narrow." + NL * 2 + "| a | b |" + NL + "|---|---|" + NL + "| 1 | 2 |" + NL,
                             encoding="utf-8")
    br.build(d, out)
    t = Document(str(out)).tables[-1]
    assert t.cell(1, 0).paragraphs[0].runs[0].font.size == br.Pt(br.TABLE_PT)


def test_tall_figure_height_is_capped(br, tmp_path):
    from PIL import Image
    d = tmp_path / "sections"
    d.mkdir()
    Image.new("RGB", (300, 600), "white").save(tmp_path / "tall.png")
    (d / "01.md").write_text("![Figure N Tall.](../tall.png)" + NL, encoding="utf-8")
    out = tmp_path / "r.docx"
    br.build(d, out)
    shape = Document(str(out)).inline_shapes[0]
    assert shape.height.cm <= br.MAX_FIGURE_HEIGHT_CM + 0.01


def _row_sections(tmp_path, body):
    from PIL import Image
    d = tmp_path / "sections"
    d.mkdir()
    Image.new("RGB", (900, 450), "white").save(tmp_path / "shot.png")
    (d / "01.md").write_text(body, encoding="utf-8")
    return d


def test_row_puts_a_table_beside_a_figure(br, tmp_path):
    d = _row_sections(tmp_path, NL.join([
        "{{row 6.6 9.4}}", "**Table N** Result.", "| Member | Value |", "|---|---|", "| January | 61 |",
        "{{col}}", "![Figure N Shot.](../shot.png)", "{{end-row}}", "After the row."]) + NL)
    out = tmp_path / "r.docx"
    br.build(d, out)
    doc = Document(str(out))
    layout = doc.tables[0]
    assert len(layout.rows) == 1 and len(layout.columns) == 2
    left, right = layout.cell(0, 0), layout.cell(0, 1)
    assert left.tables and left.tables[0].cell(1, 0).text == "January"
    assert "Table 1" in left.paragraphs[0].text                   # caption above the nested table
    assert right._tc.xpath(".//pic:pic") and "Figure 1" in right.paragraphs[-1].text
    assert doc.inline_shapes[0].width.cm <= 9.4 - 2 * br.DEFAULT_CELL_MARGIN_CM + 0.01
    assert any(p.text == "After the row." for p in doc.paragraphs)
    assert layout._tbl.tblPr.find(br.qn("w:tblStyle")) is None   # borderless layout table


def test_row_with_wrong_number_of_widths_fails_loudly(br, tmp_path):
    d = _row_sections(tmp_path, NL.join(["{{row 8 8}}", "only one column", "{{end-row}}"]) + NL)
    with pytest.raises(ValueError):
        br.build(d, tmp_path / "r.docx")


def test_keep_block_holds_its_paragraphs_on_one_page(br, tmp_path):
    d = _row_sections(tmp_path, NL.join([
        "Before.", "", "{{keep}}", "Question.", "", "```", "SELECT 1", "```", "",
        "{{row 8 8}}", "![Figure N A.](../shot.png)", "{{col}}", "![Figure N B.](../shot.png)", "{{end-row}}", "",
        "Result.", "{{end-keep}}", "", "After."]) + NL)
    out = tmp_path / "r.docx"
    br.build(d, out)
    doc = Document(str(out))
    pars = {p.text: p for p in doc.paragraphs}
    assert pars["Question."].paragraph_format.keep_with_next is True
    assert pars["SELECT 1"].paragraph_format.keep_with_next is True
    assert not pars["Result."].paragraph_format.keep_with_next          # the last one does not pull the next block
    assert not pars["Before."].paragraph_format.keep_with_next
    assert not pars["After."].paragraph_format.keep_with_next
    row = doc.tables[0].rows[0]._tr
    assert row.trPr is not None and row.trPr.find(br.qn("w:cantSplit")) is not None
    cell_pars = doc.tables[0].cell(0, 0)._tc.iter(br.qn("w:p"))
    assert all(p.pPr is not None and p.pPr.keepNext_val for p in cell_pars)


def test_block_above_a_row_gets_a_small_gap(br, tmp_path):
    """The paragraph just above a side-by-side row (the last MDX line, or a question) gets ROW_GAP_PT after it."""
    d = _row_sections(tmp_path, NL.join([
        "```", "SELECT 1", "FROM x", "```", "", "{{row 8 8}}", "![Figure N A.](../shot.png)", "{{col}}",
        "![Figure N B.](../shot.png)", "{{end-row}}", "", "Plain after."]) + NL)
    out = tmp_path / "r.docx"
    br.build(d, out)
    pars = {p.text: p for p in Document(str(out)).paragraphs}
    assert pars["FROM x"].paragraph_format.space_after == br.Pt(br.ROW_GAP_PT)
    assert pars["SELECT 1"].paragraph_format.space_after == br.Pt(0)
