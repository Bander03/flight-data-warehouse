"""Data layer of the local website (web/data.py): the 28 analyses, their saved results, the match badge, the overview."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from web import data  # noqa: E402


def test_list_stems_is_28():
    stems = data.list_stems()
    assert len(stems) == 28 and stems == sorted(stems)


def test_every_statement_loads():
    for stem in data.list_stems():
        s = data.load_statement(stem)
        assert s["question"] and s["measure"] and s["operation"] and s["mdx"] and s["answer_sql"], stem
        assert s["rows"], stem
        ranked = stem.startswith(("05_rank", "06_top_n"))
        assert s["columns"] == (["Rank", "Member", "Value"] if ranked else ["Member", "Value"]), stem
        assert all(isinstance(r["Value"], float) for r in s["rows"]), stem


def test_groups_cover_all_nine_operations():
    groups = {s["group"] for s in data.list_statements()}
    assert groups == {t for _, t in data.OPERATIONS} and len(groups) == 9


@pytest.mark.parametrize("bad", ["", "../README", "01_drill_down_1.mdx", "%2e%2e", "nope", "01_drill_down_1/../x"])
def test_is_stem_rejects_unknown(bad):
    assert data.is_stem(bad) is False
    with pytest.raises(ValueError):
        data.load_statement(bad)


def test_chinese_member_survives():
    s = data.load_statement("05_rank_1")
    assert s["rows"][0]["Member"] == "中国东方航空"
    assert s["rows"][0]["Value"] == 699600.0 and s["rows"][0]["Rank"] == 1


def test_member_with_pipe_and_comma_is_one_member():
    """Dice results join two members with ' | ' and a caption may hold a comma; csv parsing must keep them together."""
    members = [r["Member"] for r in data.load_statement("04_dice_1")["rows"]]
    assert any(" | " in m for m in members)


def test_match_summary_is_28_of_28():
    m = data.match_summary()
    assert (m["matched"], m["total"]) == (28, 28)


def test_rows_equal_detects_value_and_member_changes():
    a = [{"Member": "x", "Value": 10.0}, {"Member": "y", "Value": 2.0}]
    assert data.rows_equal(a, [dict(r) for r in a]) == []
    assert data.rows_equal(a, [{"Member": "x", "Value": 11.0}, {"Member": "y", "Value": 2.0}])
    assert any("z" in d for d in data.rows_equal(a, [{"Member": "x", "Value": 10.0}, {"Member": "z", "Value": 2.0}]))
    assert data.rows_equal(a, a[:1])           # a missing row is a difference


def test_rows_equal_ranked_order_matters():
    a = [{"Rank": 1, "Member": "x", "Value": 5.0}, {"Rank": 2, "Member": "y", "Value": 4.0}]
    b = [a[1], a[0]]
    assert data.rows_equal(a, b)


def test_overview_from_snapshot_when_no_data(tmp_path):
    o = data.overview(processed_dir=tmp_path)
    assert o["source"] == "snapshot"
    assert o["segments"] == 600


def test_snapshot_equals_counted_data():
    processed = REPO / "data" / "processed"
    if not (processed / "fact_flight_segment.csv").exists():
        pytest.skip("data/processed not built")
    counted = data.overview(processed_dir=processed)
    snap = json.loads((REPO / "web" / "overview_snapshot.json").read_text(encoding="utf-8"))
    assert counted["source"] == "data"
    assert (counted["segments"], counted["stopover_segments"], counted["passengers"]) == (600, 95, 599)
    assert counted["total_revenue"] == 1400460 and counted["total_mileage"] == 1001283
    assert counted["airports_used"] <= counted["airports"]
    for key in ("segments", "passengers", "stopover_segments", "airports_used", "airports", "airlines", "aircraft", "dates", "total_revenue", "total_mileage"):
        assert counted[key] == snap[key], key


def test_every_statement_has_its_screenshot():
    assert all(data.screenshot_path(s) for s in data.list_stems())
    assert data.screenshot_path("../README") is None and data.screenshot_path("01_drill_down_9") is None


def test_profile_falls_back_to_the_committed_snapshot(tmp_path):
    snap = data.profile(tmp_path)
    assert snap["source"] == "snapshot" and len(snap["rules"]) == 17
    assert (snap["passed_before"], snap["passed_after"]) == (9, 17)
    real = data.PROCESSED / "profile_before_after.md"
    if real.exists():
        assert {k: v for k, v in data.profile().items() if k != "source"} == \
               {k: v for k, v in snap.items() if k != "source"}, "snapshot is stale: python -m web.data --write-snapshot"


def test_project_reads_the_cover():
    p = data.project()
    assert len(p["members"]) == 3 and sum(m["leader"] for m in p["members"]) == 1
    assert p["teacher"] == "Prof Yan Zhu" and p["date"] == "2026-12-21"
