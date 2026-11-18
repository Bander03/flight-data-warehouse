"""Guards report section 3.3: every number quoted in a result sentence must come from the verified results."""
from __future__ import annotations

import csv
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "make_functions_section.py"

spec = importlib.util.spec_from_file_location("make_functions_section", TOOL)
mfs = importlib.util.module_from_spec(spec)
sys.modules["make_functions_section"] = mfs
spec.loader.exec_module(mfs)

NUMBER = re.compile(r"(?<![A-Za-z\d.\-])\d[\d,]*(?:\.\d+)?(?![\d\-])")  # not part of a flight number like CA1517 or a date


def _values(stem: str) -> list[float]:
    hdr, body = mfs.read_results(stem)
    vals: list[float] = []
    for r in body:
        for cell in r:
            try:
                vals.append(float(cell))
            except ValueError:
                pass
    return vals


def test_every_statement_has_notes():
    stems = sorted(p.stem for p in mfs.MDX_DIR.glob("*.mdx"))
    assert len(stems) == 28
    assert sorted(mfs.NOTES) == stems


@pytest.mark.parametrize("stem", sorted(mfs.NOTES))
def test_numbers_in_result_sentence_come_from_results(stem):
    sentence = mfs.NOTES[stem][1]
    values = _values(stem)
    derived = mfs.DERIVED.get(stem, set())
    for token in NUMBER.findall(sentence):
        digits = re.sub(r"\D", "", token)
        if len(digits) < 3:
            continue
        clean = token.replace(",", "")
        number = float(clean)
        places = len(clean.split(".")[1]) if "." in clean else None
        if places is None:
            ok = any(round(v) == number for v in values) or number in derived
        else:
            ok = any(round(v, places) == round(number, places) for v in values) or number in derived
        assert ok, f"{stem}: number {token} in the result sentence is not in mdx/results/{stem}.csv and not in DERIVED"


def test_derived_entries_are_used():
    for stem, nums in mfs.DERIVED.items():
        sentence = mfs.NOTES[stem][1]
        found = {float(t.replace(",", "")) for t in NUMBER.findall(sentence)}
        assert nums <= found, f"{stem}: DERIVED lists numbers that the sentence does not contain: {nums - found}"


def test_generated_markdown_has_all_statements_and_captions_above_tables():
    md = mfs.build_markdown()
    for stem in mfs.NOTES:
        assert f"**{stem}.**" in md
        assert f"Result of `{stem}`" in md
    # each table caption line is directly followed by its table (caption above the table)
    lines = md.splitlines()
    captions = [i for i, line in enumerate(lines) if line.startswith("**Table N**")]
    assert len(captions) == 28
    for i in captions:
        assert lines[i + 2].startswith("| ")
    # captions carry the token N; tools/build_report.py numbers them in document order
    assert not re.search(r"\b(Table|Figure) \d", md)
    # every statement has either its screenshot embedded or a placeholder; captions use the N token
    n_images = sum(1 for line in md.splitlines() if line.startswith("![Figure N SSMS result window of"))
    n_placeholders = md.count("as Figure N:")
    assert n_images + n_placeholders == 28
    assert md.count("```") == 56  # 28 code blocks, opening and closing fence


def test_written_file_uses_lf_line_endings(tmp_path, monkeypatch):
    out = tmp_path / "03_3_functions.md"
    monkeypatch.setattr(mfs, "OUT", out)
    assert mfs.main(["--force"]) == 0
    assert b"\r\n" not in out.read_bytes()
