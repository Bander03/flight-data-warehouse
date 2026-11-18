"""Answer keys for the MDX library: mdx/answers/NN_<operation>_<k>.sql (T-SQL over FlightDW).

Static tests (file set, headers, distinct questions, stopover exclusion, column convention) run
anywhere. The execution test runs every answer key read-only (SELECT only) against FlightDW and is
skipped when sqlcmd is not on PATH or the instance / database is unreachable. It never rebuilds the
warehouse. Instance override: FDW_SQL_INSTANCE (default localhost\\SQLEXPRESS).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ANSWERS = REPO / "mdx" / "answers"
INSTANCE = os.environ.get("FDW_SQL_INSTANCE", r"localhost\SQLEXPRESS")
SQLCMD = shutil.which("sqlcmd")

OPERATIONS = {
    "01_drill_down": 3, "02_roll_up": 3, "03_slice": 3, "04_dice": 3,
    "05_rank": 3, "06_top_n": 3, "07_moving_avg": 3, "08_running_total": 3,
    "09_stopover": 4,
}
EXPECTED = sorted(f"{op}_{k}.sql" for op, n in OPERATIONS.items() for k in range(1, n + 1))
RANKED = ("05_rank", "06_top_n")
MAX_ROWS = 30

# an explicit exclusion of the 'No stopover' member (AirportKey 0) on the transit role
EXCLUDE_NO_STOPOVER = re.compile(r"TransitAirportKey\s*(<>|!=|>)\s*0\b")
WHERE_EXCLUDE = re.compile(r"\bWHERE\b[^;]*?TransitAirportKey\s*(<>|!=|>)\s*0\b", re.I | re.S)


def _files():
    return sorted(ANSWERS.glob("*.sql"))


def _text(path):
    return path.read_text(encoding="utf-8")


def _header(path, tag):
    m = re.search(rf"^--\s*{tag}:[ \t]*(.+)$", _text(path), re.M)
    return m.group(1).strip() if m else None


def _code(path):
    """The SQL without comment lines."""
    return "\n".join(l for l in _text(path).splitlines() if not l.strip().startswith("--"))


def test_file_set():
    assert ANSWERS.is_dir(), "mdx/answers/ does not exist"
    assert sorted(p.name for p in _files()) == EXPECTED


def test_headers():
    missing = []
    for p in _files():
        for tag in ("Operation", "Question", "Measure"):
            if not _header(p, tag):
                missing.append(f"{p.name}: no '-- {tag}:' line")
        q = _header(p, "Question")
        if q and not q.endswith("?"):
            missing.append(f"{p.name}: question must end with '?': {q}")
    assert _files(), "no answer keys"
    assert not missing, "\n".join(missing)


def test_questions_distinct():
    questions = [_header(p, "Question") for p in _files()]
    assert len(questions) == len(EXPECTED) == 28
    assert len(set(questions)) == 28, "duplicate question strings"


def test_only_select():
    assert _files(), "no answer keys"
    banned = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|EXEC|EXECUTE)\b", re.I)
    bad = [p.name for p in _files() if banned.search(_code(p))]
    assert not bad, f"answer keys must be read-only SELECTs: {bad}"
    assert all(_code(p).lstrip().upper().startswith(("SELECT", "WITH")) for p in _files())


def test_no_stopover_excluded():
    """The hub list (09_stopover_1) must filter AirportKey 0 in a WHERE clause. The other 09 statements
    (2: stopover vs direct, 3: airline share, 4: all-stopover routes) intentionally use a CASE on
    TransitAirportKey instead of a filter, because they need the direct segments too; they must still
    contain an explicit `TransitAirportKey <> 0` condition (as must any file that touches the transit role)."""
    assert _files(), "no answer keys"
    bad = []
    for p in _files():
        code = _code(p)
        if p.name.startswith("09_stopover") or "TransitAirportKey" in code:
            if not EXCLUDE_NO_STOPOVER.search(code):
                bad.append(p.name)
    assert not bad, f"AirportKey 0 ('No stopover') is not excluded in: {bad}"
    assert WHERE_EXCLUDE.search(_code(ANSWERS / "09_stopover_1.sql")), \
        "09_stopover_1 needs `WHERE ... TransitAirportKey <> 0`"


def test_columns_convention_static():
    assert _files(), "no answer keys"
    for p in _files():
        code = _code(p)
        assert re.search(r"\bAS\s+\[?Member\]?", code, re.I), f"{p.name}: no Member column"
        assert re.search(r"\bAS\s+\[?Value\]?", code, re.I), f"{p.name}: no Value column"
        if p.name.startswith(RANKED):
            assert re.search(r"\bAS\s+\[?Rank\]?", code, re.I), f"{p.name}: no Rank column"
            assert re.search(r"ORDER\s+BY\s+\[?Rank\]?", code, re.I), f"{p.name}: must be ordered by Rank"
        else:
            assert re.search(r"ORDER\s+BY", code, re.I), f"{p.name}: no deterministic ORDER BY"


# --------------------------------------------------------------------------- execution (needs SQL Server)
def _sqlcmd(args, timeout=120):
    cmd = [SQLCMD, "-S", INSTANCE, "-E", "-b", "-f", "65001", "-d", "FlightDW", *args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout)   # list argv, no shell


@pytest.fixture(scope="module")
def sql_server():
    if SQLCMD is None:
        pytest.skip("sqlcmd is not on PATH")
    try:
        proc = _sqlcmd(["-h", "-1", "-W", "-Q", "SET NOCOUNT ON; SELECT COUNT(*) FROM dw.Fact_FlightSegment"], 30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        pytest.skip(f"SQL Server instance {INSTANCE} not reachable: {exc}")
    if proc.returncode != 0:
        pytest.skip(f"FlightDW on {INSTANCE} not reachable (sqlcmd exit {proc.returncode})")
    return True


def _run(path):
    """Execute one answer key. Returns (columns, rows); rows are lists of str with len == len(columns)."""
    proc = _sqlcmd(["-W", "-s", "\t", "-i", str(path)])   # tab: Members contain " | "
    out = proc.stdout.decode("utf-8", "replace").lstrip("\ufeff")
    assert proc.returncode == 0, f"{path.name}: sqlcmd failed\n{out}\n{proc.stderr.decode('utf-8', 'replace')}"
    lines = out.splitlines()
    assert len(lines) >= 2, f"{path.name}: no result set\n{out}"
    columns = [c.strip() for c in lines[0].split("\t")]
    assert set(lines[1].replace("\t", "")) <= {"-"}, f"{path.name}: unexpected output\n{out}"
    rows = []
    for line in lines[2:]:
        if not line.strip():
            break                                   # blank line ends the result set
        parts = [p.strip() for p in line.split("\t")]
        assert len(parts) == len(columns), f"{path.name}: {len(parts)} fields, expected {columns}: {line!r}"
        rows.append(parts)
    return columns, rows


@pytest.fixture(scope="module")
def results(sql_server):
    return {p.name: _run(p) for p in _files()}


def test_runs_and_returns_rows(results):
    assert sorted(results) == EXPECTED
    for name, (columns, rows) in results.items():
        assert rows, f"{name}: no data rows"
        assert len(rows) <= MAX_ROWS, f"{name}: {len(rows)} rows (max {MAX_ROWS})"
        ranked = name.startswith(RANKED)
        assert columns[0] == ("Rank" if ranked else "Member"), f"{name}: first column is {columns[0]}"
        if ranked:
            assert columns[1] == "Member", f"{name}: columns {columns}"
        assert columns[-1] == "Value", f"{name}: last column is {columns[-1]}"
        assert len(set(columns)) == len(columns), f"{name}: duplicate column names {columns}"
        member = columns.index("Member")
        for row in rows:
            float(row[-1])                           # Value is numeric (raises ValueError otherwise)
            assert row[member], f"{name}: empty Member"
        members = [r[member] for r in rows]
        assert len(set(members)) == len(members), f"{name}: duplicate members"


def test_ranked_ordered_by_rank(results):
    for name, (columns, rows) in results.items():
        if not name.startswith(RANKED):
            continue
        ranks = [int(r[0]) for r in rows]
        assert ranks == sorted(ranks) and ranks[0] == 1, f"{name}: Rank must start at 1 and ascend: {ranks}"
        values = [float(r[-1]) for r in rows]
        assert values == sorted(values, reverse=True), f"{name}: Value must be descending"
