"""Repository hygiene checks (no database needed): every script starts with its own header comment and parses as text,
and no tracked text file carries an invisible control character."""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SQL = sorted((REPO / "sql").glob("*.sql"))
TEXT_SUFFIXES = {".md", ".txt", ".py", ".ps1", ".sql", ".mdx", ".json", ".csv", ".yml", ".yaml", ".toml", ".cfg", ".ini",
                 ".html", ".css", ".js", ".xmla", ".dtsx", ".dtproj", ".conmgr", ".sln", ".gitignore", ".gitattributes"}
# everything below U+0020 except tab, line feed and carriage return
CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _tracked_text_files():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split("\n")
    return sorted(p for p in out if p and (Path(p).suffix.lower() in TEXT_SUFFIXES or Path(p).name in TEXT_SUFFIXES))


@pytest.mark.parametrize("path", SQL, ids=lambda p: p.name)
def test_sql_script_starts_with_its_header_comment(path):
    """A stray character before the first comment turned 99_checks.sql into 'Could not find stored procedure al'."""
    first = path.read_text(encoding="utf-8-sig").splitlines()[0]
    assert first.startswith("-- " + path.name), f"{path.name}: first line is {first[:60]!r}"


@pytest.mark.parametrize("path", _tracked_text_files())
def test_tracked_text_file_has_no_control_character(path):
    """A command written through a shell that interprets backslash escapes turned `tools\\audit_cube.ps1` into
    `tools<BEL>udit_cube.ps1` (and `\\b`, `\\f` into backspace and form feed): the line looks almost right in an
    editor, but the copied command fails."""
    hits = [(i, line) for i, line in enumerate((REPO / path).read_bytes().splitlines(), 1) if CONTROL.search(line)]
    assert not hits, f"{path} has a control character on line {hits[0][0]}: {hits[0][1][:80]!r}"
