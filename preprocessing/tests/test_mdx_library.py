"""Lint of the MDX library: mdx/NN_<operation>_<k>.mdx (one statement per answer key).

Static checks only (no Analysis Services needed): file set, headers, cube name, every bracketed
name in docs/cube-spec.md's Names registry (or defined in the file), per-operation MDX keywords,
no near-duplicates within an operation, length, balanced brackets, dimension coverage and the
Member/Value (Rank first for 05/06) result shape.
"""
import itertools
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MDX = REPO / "mdx"
ANSWERS = MDX / "answers"
SPEC = REPO / "docs" / "cube-spec.md"

OPERATIONS = {
    "01_drill_down": 3, "02_roll_up": 3, "03_slice": 3, "04_dice": 3,
    "05_rank": 3, "06_top_n": 3, "07_moving_avg": 3, "08_running_total": 3,
    "09_stopover": 4,
}
STEMS = sorted(f"{op}_{k}" for op, n in OPERATIONS.items() for k in range(1, n + 1))
RANKED = ("05_rank", "06_top_n")
MAX_LINES = 12

NAME = r"\[[^\[\]]+\]"
CHAIN = re.compile(rf"&?{NAME}(?:\s*\.\s*&?{NAME})*")
PART = re.compile(r"(&?)\[([^\[\]]+)\]")


def _registry():
    text = SPEC.read_text(encoding="utf-8")
    block = text.split("## 6. Names registry", 1)[1]
    reg = {}
    for line in block.splitlines():
        m = re.match(r"^([a-z ]+):\s+(.+)$", line.strip())
        if m:
            reg.setdefault(m.group(1), set()).add(m.group(2).strip())
    return reg


REG = _registry()
DIMENSIONS = REG["dimension"]
MEASURES = REG["measure"] | REG["calculated member"]
# hierarchies, levels and attribute (hierarchy / level) names below a dimension
SUBNAMES = REG["hierarchy"] | REG["level"] | REG["attribute"] | REG["member"]


def _files():
    return sorted(MDX.glob("*.mdx"))


def _text(p):
    return p.read_text(encoding="utf-8")


def _header(p, tag):
    m = re.search(rf"^--\s*{tag}:[ \t]*(.+)$", _text(p), re.M)
    return m.group(1).strip() if m else None


def _code(p):
    """Query text without comment lines and blank lines."""
    return "\n".join(l for l in _text(p).splitlines() if l.strip() and not l.strip().startswith("--"))


def _defined(code):
    """Names introduced by WITH MEMBER ... / SET [...] in the file."""
    members = set(re.findall(rf"\bMEMBER\s+(?:{NAME}\s*\.\s*)*\[([^\[\]]+)\]", code, re.I))
    sets = set(re.findall(r"\bSET\s+\[([^\[\]]+)\]", code, re.I))
    return members, sets


def _chains(code):
    """Each bracketed identifier chain as a list of (is_key, name)."""
    return [[(bool(a), n) for a, n in PART.findall(c.group(0))] for c in CHAIN.finditer(code)]


def _op(stem):
    return stem.rsplit("_", 1)[0]


def _normalise(code):
    """Mask member keys, string literals and numbers; collapse whitespace."""
    s = re.sub(r"&\[[^\[\]]*\]", "&[K]", code)
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "S", s)
    s = re.sub(r"\b\d+(\.\d+)?\b", "N", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def test_file_set_matches_answer_keys():
    assert sorted(p.stem for p in _files()) == STEMS
    assert sorted(p.stem for p in ANSWERS.glob("*.sql")) == STEMS


def test_headers():
    problems = []
    for p in _files():
        for tag in ("Operation", "Question", "Answer key"):
            if not _header(p, tag):
                problems.append(f"{p.name}: no '-- {tag}:' line")
        key = _header(p, "Answer key")
        if key and key != f"mdx/answers/{p.stem}.sql":
            problems.append(f"{p.name}: answer key path {key!r}")
        if key and not (REPO / key).is_file():
            problems.append(f"{p.name}: {key} does not exist")
        sql = ANSWERS / f"{p.stem}.sql"
        if sql.is_file() and _header(p, "Question") != _header(sql, "Question"):
            problems.append(f"{p.name}: question differs from the answer key")
    assert _files(), "no MDX files"
    assert not problems, "\n".join(problems)


def test_cube_name():
    bad = []
    for p in _files():
        code = _code(p)
        if len(re.findall(r"\bFROM\s+\[FlightCube\]", code, re.I)) != 1:
            bad.append(f"{p.name}: needs exactly one FROM [FlightCube]")
        if len(re.findall(r"\bFROM\b", code, re.I)) != 1 or len(re.findall(r"\bSELECT\b", code, re.I)) != 1:
            bad.append(f"{p.name}: one SELECT ... FROM per file")
    assert _files(), "no MDX files"
    assert not bad, "\n".join(bad)


def test_names_exist_in_spec():
    bad = []
    for p in _files():
        code = re.sub(r"\bFROM\s+\[FlightCube\]", "", _code(p), flags=re.I)
        members, sets = _defined(code)
        for chain in _chains(code):
            names = [n for k, n in chain if not k]
            if not names or chain[0][0]:
                bad.append(f"{p.name}: chain starts with a key: {chain}")
                continue
            head, rest = names[0], names[1:]
            if head == "Measures":
                if len(rest) != 1 or rest[0] not in MEASURES | members:
                    bad.append(f"{p.name}: unknown measure {rest}")
            elif head in sets and not rest:
                continue
            elif head not in DIMENSIONS:
                bad.append(f"{p.name}: unknown dimension or set [{head}]")
            else:
                for n in rest:
                    if n not in SUBNAMES | members:
                        bad.append(f"{p.name}: [{n}] not in the Names registry")
    assert _files(), "no MDX files"
    assert not bad, "\n".join(bad)


def _dimensions_with_keys(code):
    """Distinct cube DIMENSIONS (first name of a member path) that are filtered by an explicit member key.

    Two attribute hierarchies of one dimension (e.g. Passenger FFP Tier x Passenger Age Band) count once:
    a dice must cut the cube along at least two different dimensions.
    """
    out = set()
    for chain in _chains(code):
        if any(k for k, _ in chain) and len(chain) >= 3 and not chain[0][0] and chain[0][1] != "Measures":
            out.add(chain[0][1])
    return out


def _moving_avg_shape(code):
    """(window construct, row grain) of a moving-average statement, e.g. ('LASTPERIODS', 'Month')."""
    construct = "LASTPERIODS" if re.search(r"LASTPERIODS\s*\(", code, re.I) else (
        "LAG" if re.search(r"\.LAG\s*\(", code, re.I) else None)
    rows = code[code.upper().index("ON COLUMNS"):] if "ON COLUMNS" in code.upper() else code
    levels = re.findall(r"\.\[(Year|Quarter|Month|Day)\]", rows)
    return construct, (levels[0] if levels else None)


def _check_operation(stem, code, header_text):
    u = code.upper()
    op = _op(stem)
    if op == "01_drill_down":
        return re.search(r"DRILLDOWNLEVEL|DRILLDOWNMEMBER|\.CHILDREN\b|DESCENDANTS\s*\(", u)
    if op == "02_roll_up":
        return re.search(r"\.PARENT\b|ANCESTOR\s*\(|ASCENDANTS\s*\(", u)
    if op == "03_slice":
        return re.search(r"\bWHERE\b", u)
    if op == "04_dice":
        return len(_dimensions_with_keys(code)) >= 2
    if op == "05_rank":
        return "RANK(" in u.replace(" ", "")
    if op == "06_top_n":
        return "TOPCOUNT(" in u.replace(" ", "")
    if op == "07_moving_avg":
        return "AVG(" in u.replace(" ", "") and re.search(r"LASTPERIODS\s*\(|\.LAG\s*\(", u)
    if op == "08_running_total":
        return re.search(r"YTD\s*\(|PERIODSTODATE\s*\(", u) or (re.search(r"\bSUM\s*\(", u) and ":" in code)
    if op == "09_stopover":
        if "[Transit Airport]" not in code or "&[0]" not in code:
            return False
        keeps = "No stopover" in header_text and re.search(r"^--\s*Members:", header_text, re.M)
        excludes = re.search(r"EXCEPT\s*\([^;]*&\[0\]", u, re.S) or re.search(r"-\s*\(\s*\[Measures\][^)]*&\[0\]", code)
        return bool(keeps or excludes)
    return False


def test_operation_keywords():
    bad = [p.name for p in _files() if not _check_operation(p.stem, _code(p), _text(p))]
    assert _files(), "no MDX files"
    assert not bad, "operation keyword missing in: " + ", ".join(bad)


OLD_DICE_ONE_DIMENSION = """WITH MEMBER [Measures].[Value] AS [Measures].[Distinct Passengers]
SELECT {[Measures].[Value]} ON COLUMNS,
  NONEMPTY({[Passenger].[FFP Tier].&[5], [Passenger].[FFP Tier].&[6]}
         * {[Passenger].[Age Band].&[2], [Passenger].[Age Band].&[3]},
           [Measures].[Distinct Passengers]) ON ROWS
FROM [FlightCube]"""


def test_dice_rule_counts_dimensions_not_hierarchies():
    # two hierarchies of the same dimension are not a multi-dimension dice
    assert _dimensions_with_keys(OLD_DICE_ONE_DIMENSION) == {"Passenger"}
    assert not _check_operation("04_dice_3", OLD_DICE_ONE_DIMENSION, "")


def test_every_dice_uses_two_dimensions():
    for p in _files():
        if p.stem.startswith("04_dice"):
            assert len(_dimensions_with_keys(_code(p))) >= 2, p.name


OLD_MOVING_AVG_3 = """WITH MEMBER [Measures].[Value] AS
  AVG(LASTPERIODS(3, [Departure Date].[Calendar].CurrentMember), [Measures].[Average Rate])
SELECT {[Measures].[Value]} ON COLUMNS,
  FILTER([Departure Date].[Calendar].[Month].Members, NOT ISEMPTY([Measures].[Segment Count])) ON ROWS
FROM [FlightCube]"""


def test_moving_averages_differ_in_construct_or_grain():
    shapes = {p.stem: _moving_avg_shape(_code(p)) for p in _files() if p.stem.startswith("07_moving_avg")}
    assert len(shapes) == 3
    assert all(c and g for c, g in shapes.values()), shapes
    assert len(set(shapes.values())) == 3, f"two moving averages share window construct and grain: {shapes}"
    # 07_3 works at day grain, 07_1 at month grain
    assert shapes["07_moving_avg_1"][1] == "Month" and shapes["07_moving_avg_3"][1] == "Day"


def test_same_construct_trio_would_be_caught():
    one = _moving_avg_shape(_code(MDX / "07_moving_avg_1.mdx"))
    assert _moving_avg_shape(OLD_MOVING_AVG_3) == one == ("LASTPERIODS", "Month")


def test_normalise_masks_constants():
    a = "SELECT [Cabin].[Cabin Class].&[F] ON 0 FROM [FlightCube] WHERE ([Price Range].[Price Grade].&[3])"
    b = "SELECT [Cabin].[Cabin Class].&[Y] ON 0 FROM [FlightCube] WHERE ([Price Range].[Price Grade].&[7])"
    assert _normalise(a) == _normalise(b)


def test_near_duplicates_rejected():
    by_op = {}
    for p in _files():
        by_op.setdefault(_op(p.stem), []).append(p)
    dups = []
    for op, files in by_op.items():
        for a, b in itertools.combinations(files, 2):
            if _normalise(_code(a)) == _normalise(_code(b)):
                dups.append(f"{a.name} ~ {b.name}")
    assert by_op, "no MDX files"
    assert not dups, "near-duplicate statements: " + ", ".join(dups)


def test_length():
    long = [f"{p.name}: {len(_code(p).splitlines())}" for p in _files() if len(_code(p).splitlines()) > MAX_LINES]
    assert _files(), "no MDX files"
    assert not long, "more than 12 query lines: " + ", ".join(long)


def test_balanced_brackets():
    pairs = {")": "(", "]": "[", "}": "{"}
    bad = []
    for p in _files():
        stack = []
        code = re.sub(r"'[^']*'|\"[^\"]*\"", "''", _code(p))
        for ch in code:
            if ch in "([{":
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack.pop() != pairs[ch]:
                    bad.append(p.name)
                    break
        else:
            if stack:
                bad.append(p.name)
    assert _files(), "no MDX files"
    assert not bad, "unbalanced brackets: " + ", ".join(bad)


def test_every_dimension_used():
    used = set()
    for p in _files():
        for chain in _chains(_code(p)):
            if not chain[0][0]:
                used.add(chain[0][1])
    assert _files(), "no MDX files"
    assert DIMENSIONS - used == set(), f"dimensions never used: {sorted(DIMENSIONS - used)}"


def test_value_measure_defined():
    bad = []
    for p in _files():
        code = _code(p)
        flat = re.sub(r"\s+", " ", code)
        if not re.search(r"\bWITH\b", code) or not re.search(r"\bMEMBER\s+\[Measures\]\.\[Value\]\s+AS\b", code, re.I):
            bad.append(f"{p.name}: no WITH MEMBER [Measures].[Value]")
        if p.stem.startswith(RANKED):
            if not re.search(r"\bMEMBER\s+\[Measures\]\.\[Rank\]\s+AS\b", code, re.I):
                bad.append(f"{p.name}: no WITH MEMBER [Measures].[Rank]")
            if "{[Measures].[Rank], [Measures].[Value]} ON COLUMNS" not in flat:
                bad.append(f"{p.name}: COLUMNS must be {{[Measures].[Rank], [Measures].[Value]}}")
        elif "{[Measures].[Value]} ON COLUMNS" not in flat:
            bad.append(f"{p.name}: COLUMNS must be {{[Measures].[Value]}}")
        if not re.search(r"\bON\s+ROWS\b", code, re.I):
            bad.append(f"{p.name}: members must be ON ROWS")
    assert _files(), "no MDX files"
    assert not bad, "\n".join(bad)


def test_run_mdx_has_outdir_parameter():
    """The website runs one statement live into a temporary folder: -OutDir must exist and the default
    (mdx\results) must apply only when -OutDir is empty, so a live run never touches committed results."""
    text = (REPO / "tools" / "run_mdx.ps1").read_text(encoding="utf-8")
    param_block = text[text.index("param("):text.index(")\n$ErrorActionPreference")]
    assert "[string]$OutDir" in param_block
    assert "$OutDir = Join-Path $MdxDir 'results'\n" not in text
    assert "if (-not $OutDir)" in text
