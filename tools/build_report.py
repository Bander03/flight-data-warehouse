"""Builds the course project report (.docx) from the Markdown files in report/sections/.

Formatting follows the teacher's guide #4:
  * cover page: course name bold, size 18, Heiti; the other cover lines bold, size 16;
  * body (sections 2 to 6): Times New Roman, size 11 (Chinese characters in FangSong);
  * code blocks: Times New Roman, size 10.5 (size "5 hao");
  * table captions ABOVE tables, figure captions BELOW figures (write them that way in the Markdown);
  * tables and figures numbered separately, in document order;
  * page numbers in the footer.

Captions carry the token N instead of a number: `**Table N** text` on the line above a pipe table,
`![Figure N text](path)` for a picture and `Figure N` inside a screenshot placeholder. The builder numbers
them in document order with two counters (Table 1, 2, ...; Figure 1, 2, ...), so adding a figure never
means renumbering by hand. In the running text refer to "the table below" rather than to a number.

Instruction paragraphs for the authors are written as one line `*(Instruction: ...)*`; they are not
printed (use --keep-instructions to print them), and --check lists them together with empty reference
entries such as `[1]`, the remaining placeholders and every table without a `**Table N**` caption.

Supported Markdown subset: '#', '##', '###' headings, paragraphs, **bold**, *italic*, `code`,
'- ' bullets, '1. ' numbered items, pipe tables, ``` code fences, and ![caption](image path) figures
(the image path is relative to the Markdown file; the caption is printed below the figure).
Layout lines: `{{row 6.6 9.4}}` ... `{{col}}` ... `{{end-row}}` puts blocks side by side (column widths in cm);
`{{keep}}` ... `{{end-keep}}` keeps the blocks between them on one page.

Usage (repo root):
    python tools/build_report.py            # writes report/build/FlightDW_Course_Project_Report.docx
    python tools/build_report.py --keep-instructions   # same, but also prints the *(Instruction: ...)* lines
    python tools/build_report.py --check    # lists placeholders, instructions and caption problems; exit 1 if any
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.table import _Cell
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[1]
SECTIONS_DIR = ROOT / "report" / "sections"
OUT_FILE = ROOT / "report" / "build" / "FlightDW_Course_Project_Report.docx"

LATIN = "Times New Roman"
EAST_BODY = "仿宋"
EAST_HEAD = "黑体"
BODY_PT = 11
CODE_PT = 10.5
TABLE_PT = 9
WIDE_TABLE_COLS = 10          # a table with more columns than this uses the smaller table font
WIDE_TABLE_PT = 8
WIDE_TABLE_CELL_MARGIN_CM = 0.08
DEFAULT_CELL_MARGIN_CM = 0.19  # Word's default left and right cell padding
DIGIT_CM_PER_PT = 0.0176       # width of a Times New Roman digit per point of font size (0.141 cm at 8 pt)
TEXT_WIDTH = Cm(16.0)         # A4 (21 cm) minus 2 x 2.5 cm margins
MIN_COLUMN_CHARS = 2

INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*|`[^`]+`)")
PLACEHOLDER = re.compile(r"\*\((?:write here|Insert|Add|Write|per statement|Draft|Screenshot).*?\)\*", re.I)
INSTRUCTION = re.compile(r"^\*\(Instruction:.*\)\*$")
EMPTY_REFERENCE = re.compile(r"^\[\d+\]\s*$")
MAX_FIGURE_HEIGHT_CM = 8.0
FIGURE_MAX_WIDTH_CM = 9.0    # full-bleed width for a wide/short screenshot, kept well under the 16 cm text width
ROW_GAP_PT = 8               # space between a block and the side-by-side row below it (a blank line would be ~13 pt)
TABLE_CAPTION = "**Table N**"
FIXED_TABLE_CAPTION = re.compile(r"^\*\*Table \d[\d.]*\*\*")
FIXED_FIGURE_CAPTION = re.compile(r"^!\[Figure \d[\d.]*\b")
FIGURE_TOKEN = re.compile(r"\bFigure N\b")


# ---------------------------------------------------------------- caption numbering
class CaptionCounter:
    """Replaces the caption tokens `**Table N**` and `Figure N` with consecutive numbers (two counters)."""

    def __init__(self):
        self.table = 0
        self.figure = 0

    def line(self, line: str) -> str:
        s = line.strip()
        if s.startswith(TABLE_CAPTION):
            self.table += 1
            return line.replace(TABLE_CAPTION, f"**Table {self.table}**", 1)
        if FIGURE_TOKEN.search(s) and (s.startswith("![") or PLACEHOLDER.search(s)):
            self.figure += 1
            return FIGURE_TOKEN.sub(f"Figure {self.figure}", line, count=1)
        return line

    def text(self, text: str) -> str:
        out, in_code = [], False
        for line in text.splitlines():
            if line.strip().startswith("```"):
                in_code = not in_code
                out.append(line)
            else:
                out.append(line if in_code else self.line(line))
        return "\n".join(out)


# ---------------------------------------------------------------- fonts and inline text
def _font(run, size, bold=None, italic=None, east=EAST_BODY, latin=LATIN):
    run.font.name = latin
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), latin)
    rfonts.set(qn("w:eastAsia"), east)


def _inline(par, text, size=BODY_PT, bold=False, east=EAST_BODY, force_bold=False):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = par.add_run(part[2:-2])
            _font(run, size, bold=True, east=east)
        elif part.startswith("`") and part.endswith("`"):
            run = par.add_run(part[1:-1])
            _font(run, size, bold=bold or force_bold, east=east)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            run = par.add_run(part[1:-1])
            _font(run, size, bold=bold or force_bold, italic=True, east=east)
        else:
            run = par.add_run(part)
            _font(run, size, bold=bold or force_bold, east=east)


def _page_number_footer(section):
    par = section.footer.paragraphs[0] if section.footer.paragraphs else section.footer.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = par.add_run()
    _font(run, 10)
    for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._element.append(el)


# ---------------------------------------------------------------- block builders
def _heading(doc, text, level):
    par = doc.add_heading(level=min(level, 3))
    size = {1: 16, 2: 14, 3: 12}.get(level, 12)
    for part in [text]:
        run = par.add_run(part)
        _font(run, size, bold=True, east=EAST_HEAD)
        run.font.color.rgb = None
    return par


def _paragraph(doc, text, style=None):
    par = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    _inline(par, text)
    par.paragraph_format.space_after = Pt(3)
    return par


def _split_row(row):
    """Cells of a pipe-table row; a pipe escaped with a backslash is part of the cell text."""
    row = row.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
    return re.split(r"(?<!\\)\|", row)


def _table(doc, rows, text_width=TEXT_WIDTH):
    header = rows[0]
    body = [r for r in rows[1:] if not re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", r)]
    cells = [[c.strip().replace("\\|", "|") for c in _split_row(r)] for r in [header] + body]
    ncols = max(len(r) for r in cells)
    wide = ncols > WIDE_TABLE_COLS
    size = WIDE_TABLE_PT if wide else TABLE_PT
    widths = _column_widths(cells, ncols, size, WIDE_TABLE_CELL_MARGIN_CM if wide else DEFAULT_CELL_MARGIN_CM,
                            text_width)
    table = doc.add_table(rows=len(cells), cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    if wide:
        _set_cell_margins(table, WIDE_TABLE_CELL_MARGIN_CM)
    for j, w in enumerate(widths):
        table.columns[j].width = w
    for i, row in enumerate(cells):
        for j in range(ncols):
            cell = table.cell(i, j)
            cell.width = widths[j]
            par = cell.paragraphs[0]
            _inline(par, row[j] if j < len(row) else "", size=size, force_bold=(i == 0))
    if not isinstance(doc, _Cell):          # _Cell.add_table already appends the paragraph a cell must end with
        doc.add_paragraph()
    return table


def _text_units(text):
    """Rough width of a text in digit widths of Times New Roman (a digit is 0.5 em): a capital 1.5, a lower-case
    letter 0.9, punctuation 0.65, a space 0.5, a CJK character 2."""
    units = 0.0
    for ch in text:
        if ord(ch) > 0x2E7F:
            units += 2
        elif ch.isupper():
            units += 1.5
        elif ch.isdigit():
            units += 1
        elif ch.isalpha():
            units += 0.9
        elif ch == " ":
            units += 0.5
        else:
            units += 0.65
    return units


def _column_widths(cells, ncols, pt, margin_cm, text_width=TEXT_WIDTH):
    """Column widths in EMU that share the text width in proportion to what each column needs: its longest
    unbreakable word (a value such as 257286 or MU5116 must not be split; text wraps at spaces) or about a third
    of its longest cell so that long sentences get room, converted to centimetres for the table font plus the
    cell padding. Equal widths wrapped numbers mid-value in the 15-column fact sample, and widths by whole cell
    length squeezed 'PASS' into a vertical column."""
    needs = []
    for j in range(ncols):
        units = MIN_COLUMN_CHARS
        for row in cells:
            if j < len(row):
                text = row[j]
                words = max((_text_units(w) for w in text.split()), default=0)
                units = max(units, words, _text_units(text) / 3)
        needs.append(units * 1.03 * DIGIT_CM_PER_PT * pt + 2 * margin_cm + 0.05)   # 3 % safety against a split word
    total = sum(needs)
    return [int(text_width * n / total) for n in needs]


def _set_cell_margins(table, cm):
    """Left and right cell padding of a table (Word's default 0.19 cm per side eats 5.7 cm on 15 columns)."""
    tbl_pr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side in ("left", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(int(cm / 2.54 * 1440)))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tbl_pr.append(mar)


def _code(doc, lines):
    for line in lines:
        par = doc.add_paragraph()
        par.paragraph_format.left_indent = Cm(0.6)
        par.paragraph_format.space_after = Pt(0)
        run = par.add_run(line)
        _font(run, CODE_PT)


def _figure(doc, caption, image_path, max_width_cm=FIGURE_MAX_WIDTH_CM):
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    with Image.open(image_path) as im:
        px_w, px_h = im.size
    width = Cm(min(max_width_cm, MAX_FIGURE_HEIGHT_CM * px_w / px_h))   # tall screenshots must not fill a page
    par.add_run().add_picture(str(image_path), width=width)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _inline(cap, caption, size=10)


def _cover_table(doc, rows):
    """The cover's one table (the member list): every cell bold, size 16, like the other cover lines (guide #4)."""
    header = rows[0]
    body = [r for r in rows[1:] if not re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", r)]
    cells = [[c.strip() for c in _split_row(r)] for r in [header] + body]
    ncols = max(len(r) for r in cells)
    table = doc.add_table(rows=len(cells), cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(cells):
        for j in range(ncols):
            cell = table.cell(i, j)
            par = cell.paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            text = row[j] if j < len(row) else ""
            run = par.add_run(text)
            _font(run, 16, bold=True, east=EAST_HEAD)
    doc.add_paragraph()
    return table


def _cover(doc, text):
    lines = text.splitlines()
    first = True
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            _cover_table(doc, block)
            continue
        raw = re.sub(r"^#+\s*", "", line)
        par = doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_before = Pt(18 if not first else 60)
        par.paragraph_format.space_after = Pt(12)
        if first:
            run = par.add_run(re.sub(r"\*+", "", raw))
            _font(run, 18, bold=True, east=EAST_HEAD)
            first = False
        else:
            _inline(par, raw, size=16, force_bold=True, east=EAST_HEAD)
        i += 1
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _block_element(container):
    return container._tc if isinstance(container, _Cell) else container.element.body


def _keep_together(element, before):
    """Children of `element` added since `before` stay on one page: keep-with-next on every paragraph except the
    last, and no table row splits across a page."""
    new = [c for c in element if c not in before and c.tag != qn("w:sectPr")]
    pars = [p for c in new for p in c.iter(qn("w:p"))]
    for p in pars[:-1]:
        p.get_or_add_pPr().keepNext_val = True
    for c in new:
        for tr in c.iter(qn("w:tr")):
            if tr.find(qn("w:trPr")) is None or tr.find(qn("w:trPr")).find(qn("w:cantSplit")) is None:
                tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def _layout_row(container, widths_cm, columns, base, keep_instructions):
    """Blocks side by side (for example a result table next to its screenshot): a borderless one-row table."""
    above = [c for c in _block_element(container) if c.tag != qn("w:sectPr")]
    if above and above[-1].tag == qn("w:p"):
        Paragraph(above[-1], container).paragraph_format.space_after = Pt(ROW_GAP_PT)
    table = container.add_table(rows=1, cols=len(widths_cm))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for j, (w, lines) in enumerate(zip(widths_cm, columns)):
        table.columns[j].width = Cm(w)
        cell = table.cell(0, j)
        cell.width = Cm(w)
        first = cell.paragraphs[0]
        _body(cell, "\n".join(lines), base, keep_instructions, width_cm=w - 2 * DEFAULT_CELL_MARGIN_CM)
        if not first.text and len(cell._tc.findall(qn("w:p")) + cell._tc.findall(qn("w:tbl"))) > 1:
            cell._tc.remove(first._element)
    if not isinstance(container, _Cell):
        container.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def _body(doc, text, base: Path, keep_instructions: bool = False, width_cm: float | None = None):
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s == "{{keep}}":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "{{end-keep}}":
                j += 1
            element = _block_element(doc)
            before = list(element)
            _body(doc, "\n".join(lines[i + 1:j]), base, keep_instructions, width_cm)
            _keep_together(element, before)
            i = j + 1
            continue
        m_row = re.match(r"^\{\{row((?:\s+[\d.]+)+)\s*\}\}$", s)
        if m_row:
            widths = [float(w) for w in m_row.group(1).split()]
            columns, j = [[]], i + 1
            while j < len(lines) and lines[j].strip() != "{{end-row}}":
                if lines[j].strip() == "{{col}}":
                    columns.append([])
                else:
                    columns[-1].append(lines[j])
                j += 1
            if len(columns) != len(widths):
                raise ValueError(f"{{{{row}}}} gives {len(widths)} widths but has {len(columns)} columns: {s}")
            _layout_row(doc, widths, columns, base, keep_instructions)
            i = j + 1
            continue
        m_inc = re.match(r"^\{\{include:\s*(.+?)\s*\}\}$", s)
        if m_inc:
            target = (ROOT / m_inc.group(1)).resolve()
            if not target.exists():
                raise FileNotFoundError(f"include file not found: {target}")
            _code(doc, target.read_text(encoding="utf-8-sig").splitlines())
            i += 1
            continue
        m_inc_code = re.match(r"^\{\{include-code:\s*(.+?)\s*\}\}$", s)
        if m_inc_code:
            target = (ROOT / m_inc_code.group(1)).resolve()
            if not target.exists():
                raise FileNotFoundError(f"include file not found: {target}")
            code_lines = [l for l in target.read_text(encoding="utf-8-sig").splitlines() if not l.strip().startswith("--")]
            while code_lines and not code_lines[0].strip():
                code_lines.pop(0)
            while code_lines and not code_lines[-1].strip():
                code_lines.pop()
            _code(doc, code_lines)
            i += 1
            continue
        if s.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            _code(doc, block)
            continue
        if s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            _table(doc, block, Cm(width_cm) if width_cm else TEXT_WIDTH)
            continue
        if not keep_instructions and (INSTRUCTION.match(s) or EMPTY_REFERENCE.match(s)):
            i += 1
            continue
        if re.match(r"^\*\*Table \d+\*\*", s):
            _paragraph(doc, s).alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            _heading(doc, m.group(2), len(m.group(1)))
            i += 1
            continue
        m = re.match(r"^!\[(.*?)\]\((.*?)\)$", s)
        if m:
            _figure(doc, m.group(1), (base / m.group(2)).resolve(),
                    min(FIGURE_MAX_WIDTH_CM, width_cm) if width_cm else FIGURE_MAX_WIDTH_CM)
            i += 1
            continue
        if re.match(r"^[-*]\s+", s):
            _paragraph(doc, re.sub(r"^[-*]\s+", "", s), style="List Bullet")
            i += 1
            continue
        if re.match(r"^\d+\.\s+", s):
            _paragraph(doc, re.sub(r"^\d+\.\s+", "", s), style="List Number")
            i += 1
            continue
        # a paragraph: join following non-blank, non-special lines
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|```|\||!\[|[-*]\s|\d+\.\s)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        _paragraph(doc, " ".join(para))


# ---------------------------------------------------------------- public API
def build(sections_dir: Path | None = None, out_file: Path | None = None, keep_instructions: bool = False) -> Path:
    sections_dir = Path(sections_dir or SECTIONS_DIR)
    out_file = Path(out_file or OUT_FILE)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.5)
    sec.top_margin = sec.bottom_margin = Cm(2.5)
    normal = doc.styles["Normal"]
    normal.font.name = LATIN
    normal.font.size = Pt(BODY_PT)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.0
    for level, before, after in ((1, 10, 4), (2, 8, 3), (3, 6, 2)):
        h = doc.styles[f"Heading {level}"]
        h.paragraph_format.space_before = Pt(before)
        h.paragraph_format.space_after = Pt(after)
    _page_number_footer(sec)

    files = sorted(sections_dir.glob("*.md"))
    counter = CaptionCounter()
    for f in files:
        text = f.read_text(encoding="utf-8")
        if f.name.startswith("00_"):
            _cover(doc, text)
        else:
            _body(doc, counter.text(text), f.parent, keep_instructions)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_file))
    return out_file


def _section_lines(sections_dir: Path | None, skip_code: bool = False):
    """(file name, line number, stripped line) of every section file, optionally outside code fences."""
    for f in sorted(Path(sections_dir or SECTIONS_DIR).glob("*.md")):
        in_code = False
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("```"):
                in_code = not in_code
                continue
            if skip_code and in_code:
                continue
            yield f, n, s


def find_placeholders(sections_dir: Path | None = None) -> list[str]:
    return [f"{f.name}:{n}: {s[:110]}" for f, n, s in _section_lines(sections_dir) if PLACEHOLDER.search(s)]


def find_instructions(sections_dir: Path | None = None) -> list[str]:
    """Author instructions (`*(Instruction: ...)*`) and empty reference entries (`[1]`) left in the text."""
    found = []
    for f, n, s in _section_lines(sections_dir, skip_code=True):
        if INSTRUCTION.match(s):
            found.append(f"{f.name}:{n}: {s[:110]}")
        elif EMPTY_REFERENCE.match(s):
            found.append(f"{f.name}:{n}: empty reference entry {s}")
    return found


def find_caption_problems(sections_dir: Path | None = None) -> list[str]:
    """Tables without a `**Table N**` caption directly above, and captions written with a fixed number."""
    problems = []
    prev: dict[str, tuple[int, str]] = {}          # file -> last non-blank line (number, text)
    in_table: dict[str, bool] = {}
    for f, n, s in _section_lines(sections_dir, skip_code=True):
        if f.name.startswith("00_") or not s:
            continue
        if FIXED_TABLE_CAPTION.match(s) or FIXED_FIGURE_CAPTION.match(s):
            problems.append(f"{f.name}:{n}: caption with a fixed number (write N): {s[:80]}")
        if s.startswith("|"):
            if not in_table.get(f.name):
                pn, ps = prev.get(f.name, (0, ""))
                if not (ps.startswith(TABLE_CAPTION) or FIXED_TABLE_CAPTION.match(ps)):
                    problems.append(f"{f.name}:{n}: table has no 'Table N' caption line above it: {s[:60]}")
            in_table[f.name] = True
        else:
            in_table[f.name] = False
        prev[f.name] = (n, s)
    return problems


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Chinese text in listed lines
    if "--check" in argv:
        groups = [("placeholder(s) still need text", find_placeholders()),
                  ("instruction paragraph(s) or empty reference(s) to replace before printing", find_instructions()),
                  ("caption problem(s)", find_caption_problems())]
        for title, items in groups:
            print(f"{len(items)} {title}:")
            for it in items:
                print("  " + it)
        return 1 if any(items for _, items in groups) else 0
    out = build(keep_instructions="--keep-instructions" in argv)
    print("wrote", out)
    left = len(find_placeholders()) + len(find_instructions()) + len(find_caption_problems())
    if left:
        print(f"note: {left} item(s) still to finish (run with --check to list them)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
