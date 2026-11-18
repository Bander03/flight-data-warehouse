"""tools/compare_results.py: compares an MDX result CSV (mdx/results/<stem>.csv, written by
tools/run_mdx.ps1) with the rows of its T-SQL answer key. Synthetic data only; no server needed."""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("compare_results", REPO / "tools" / "compare_results.py")
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

TOL = dict(rel_tol=1e-3, abs_tol=0.005)


def _csv(tmp_path, stem, text):
    p = tmp_path / f"{stem}.csv"
    p.write_bytes(text.encode("utf-8"))          # UTF-8 without BOM, as run_mdx.ps1 writes it
    return p


def _rows(*pairs, ranked=False):
    if ranked:
        return [{"Rank": str(r), "Member": m, "Value": str(v)} for r, m, v in pairs]
    return [{"Member": m, "Value": str(v)} for m, v in pairs]


def test_equal_passes(tmp_path):
    p = _csv(tmp_path, "01_drill_down_1", "Member,Value\nJanuary,10\nFebruary,20\n")
    assert cr.compare(p, _rows(("January", 10), ("February", 20)), False, **TOL) == []


def test_value_mismatch_fails_and_names_stem(tmp_path):
    p = _csv(tmp_path, "02_roll_up_1", "Member,Value\nJanuary,10\nFebruary,21\n")
    diffs = cr.compare(p, _rows(("January", 10), ("February", 20)), False, **TOL)
    assert len(diffs) == 1
    assert "02_roll_up_1" in diffs[0] and "February" in diffs[0]


def test_missing_member_fails(tmp_path):
    p = _csv(tmp_path, "03_slice_1", "Member,Value\nJanuary,10\n")
    diffs = cr.compare(p, _rows(("January", 10), ("March", 5)), False, **TOL)
    assert diffs and any("missing" in d and "March" in d for d in diffs)


def test_extra_member_fails(tmp_path):
    p = _csv(tmp_path, "03_slice_2", "Member,Value\nJanuary,10\nApril,7\n")
    diffs = cr.compare(p, _rows(("January", 10)), False, **TOL)
    assert diffs and any("extra" in d and "April" in d for d in diffs)


def test_order_ignored_for_unranked(tmp_path):
    p = _csv(tmp_path, "02_roll_up_2", "Member,Value\nB,2\nA,1\n")
    assert cr.compare(p, _rows(("A", 1), ("B", 2)), False, **TOL) == []


def test_order_enforced_for_ranked(tmp_path):
    p = _csv(tmp_path, "05_rank_1", "Rank,Member,Value\n1,B,20\n2,A,10\n")
    assert cr.compare(p, _rows((1, "B", 20), (2, "A", 10), ranked=True), True, **TOL) == []
    swapped = _rows((1, "A", 10), (2, "B", 20), ranked=True)
    assert cr.compare(p, swapped, True, **TOL), "rows in a different order must not match"
    wrong_rank = _rows((1, "B", 20), (3, "A", 10), ranked=True)
    diffs = cr.compare(p, wrong_rank, True, **TOL)
    assert diffs and any("Rank" in d for d in diffs)


def test_chinese_member_roundtrip(tmp_path):
    text = 'Member,Value\n"首都机场 | 浦东国际机场",1234.5\n中国东方航空,99\n'
    p = _csv(tmp_path, "06_top_n_1", text)
    rows = _rows(("首都机场 | 浦东国际机场", 1234.5), ("中国东方航空", 99))
    assert cr.compare(p, rows, False, **TOL) == []
    loaded = cr.load_result(p)
    assert [r["Member"] for r in loaded] == ["首都机场 | 浦东国际机场", "中国东方航空"]


def test_tolerance_accepts_rounding(tmp_path):
    # the key rounds to DECIMAL(12, 2) / DECIMAL(8, 4); the cube returns the raw double
    p = _csv(tmp_path, "09_stopover_3", "Member,Value\nA,2334.1033333333\nB,0.15833333\nC,1.1E1\n")
    rows = _rows(("A", "2334.10"), ("B", "0.1583"), ("C", "11"))
    assert cr.compare(p, rows, False, **TOL) == []


def test_tolerance_rejects_real_difference(tmp_path):
    p = _csv(tmp_path, "07_moving_avg_1", "Member,Value\nA,2334.10\nB,0.20\n")
    rows = _rows(("A", "2336.50"), ("B", "0.1583"))
    diffs = cr.compare(p, rows, False, **TOL)
    assert len(diffs) == 2


def test_duplicate_key_member_fails(tmp_path):
    p = _csv(tmp_path, "02_roll_up_3", "Member,Value\nA,20\n")
    diffs = cr.compare(p, _rows(("A", 10), ("A", 20)), False, **TOL)
    assert diffs and any("duplicate" in d and "answer key" in d and "'A'" in d for d in diffs)


def test_trailing_ideographic_space_in_key_member_is_a_difference(tmp_path):
    # sqlcmd -W trims ASCII spaces only; a key member ending in U+3000 must survive parsing and
    # must not compare equal to the cube caption without it (the 06_top_n_3 WorkplaceLabel case).
    out = "Member\tValue\n------\t-----\n中国北京　\t57\n"
    rows = cr.parse_sqlcmd(out)
    assert rows == [{"Member": "中国北京　", "Value": "57"}]
    p = _csv(tmp_path, "06_top_n_3", "Member,Value\n中国北京,57\n")
    assert cr.compare(p, rows, False, **TOL)


def test_production_tolerance_path(tmp_path):
    # the CLI uses rel 1e-6 and half a unit of the key's last decimal (DECIMAL(8, 4) -> 0.00005)
    rows = _rows(("A", "0.1583"), ("B", "2334.10"))
    tol = cr.key_abs_tol(rows)
    assert tol == pytest.approx(0.00005)
    inside = _csv(tmp_path, "09_stopover_3", "Member,Value\nA,0.15834\nB,2334.10004\n")
    assert cr.compare(inside, rows, False, cr.DEFAULT_REL_TOL, tol) == []
    outside = _csv(tmp_path, "09_stopover_4", "Member,Value\nA,0.15836\nB,2334.10004\n")
    diffs = cr.compare(outside, rows, False, cr.DEFAULT_REL_TOL, tol)
    assert len(diffs) == 1 and "'A'" in diffs[0]


def test_malformed_result_csv_is_reported_not_raised(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    (results / "01_drill_down_1.csv").write_text("Member,Amount\nJanuary,61\n", encoding="utf-8")
    monkeypatch.setattr(cr, "RESULTS", results)
    monkeypatch.setattr(cr, "run_answer_key", lambda path, sqlcmd: _rows(("January", 61)))
    status = cr.check(["01_drill_down_1"], "sqlcmd")
    assert status["01_drill_down_1"] and "malformed" in status["01_drill_down_1"][0]


def test_parse_sqlcmd_output():
    out = ("Rank\tMember\tValue\n----\t------\t-----\n1\t中国东方航空\t500\n2\tB\t40\n\n(2 rows affected)\n")
    assert cr.parse_sqlcmd(out) == _rows((1, "中国东方航空", 500), (2, "B", 40), ranked=True)
