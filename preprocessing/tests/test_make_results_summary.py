"""tools/make_results_summary.py builds mdx/results/SUMMARY.md from the result CSVs and the MDX
headers. Synthetic directories only; no server."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("make_results_summary", REPO / "tools" / "make_results_summary.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

HEAD = "-- Operation: {op}\n-- Question: {q}\n-- Measure: {m}\n-- Answer key: mdx/answers/{s}.sql\nSELECT 1 FROM [FlightCube]\n"


def _setup(tmp_path):
    mdx, res = tmp_path / "mdx", tmp_path / "mdx" / "results"
    res.mkdir(parents=True)
    (mdx / "01_drill_down_1.mdx").write_text(HEAD.format(op="Drill down", q="Which months?", m="Segment Count",
                                                         s="01_drill_down_1"), encoding="utf-8")
    (mdx / "05_rank_1.mdx").write_text(HEAD.format(op="Rank", q="Which airlines?", m="Total Price",
                                                   s="05_rank_1"), encoding="utf-8")
    (res / "01_drill_down_1.csv").write_text(
        "Member,Value\nJanuary,61\nFebruary,78\nMarch,91\nApril,1\nMay,2\nJune,3\n", encoding="utf-8")
    (res / "05_rank_1.csv").write_text(
        'Rank,Member,Value\n1,"上海 | 2021 Q1",2334.1033333\n2,B,0.5\n', encoding="utf-8")
    return mdx, res


def test_summary_content(tmp_path):
    mdx, res = _setup(tmp_path)
    text = ms.build_summary(mdx, res)
    assert "## 01_drill_down_1" in text and "## 05_rank_1" in text
    assert "- Question: Which months?" in text and "- Operation: Rank" in text
    assert "- Rows: 6" in text and "- Rows: 2" in text
    assert "| May | 2 |" in text and "June" not in text            # first 5 rows only
    assert "| Rank | Member | Value |" in text
    assert "| 1 | 上海 \\| 2021 Q1 | 2334.1033 |" in text           # '|' escaped, 4 decimals
    assert "of 28" not in text and "match" not in text.lower()     # no hard-coded comparison claim


def test_summary_with_compare_status(tmp_path):
    mdx, res = _setup(tmp_path)
    text = ms.build_summary(mdx, res, compare_status="2 of 2 statements match their answer keys")
    assert "2 of 2 statements match their answer keys" in text


def test_missing_result_is_reported(tmp_path):
    mdx, res = _setup(tmp_path)
    (res / "05_rank_1.csv").unlink()
    text = ms.build_summary(mdx, res)
    assert "no result file" in text


def test_main_writes_file(tmp_path):
    mdx, res = _setup(tmp_path)
    assert ms.main(["--mdx-dir", str(mdx), "--results-dir", str(res)]) == 0
    assert (res / "SUMMARY.md").read_text(encoding="utf-8").startswith("# MDX results summary")
