import pandas as pd
import pytest

from fdw import config
from fdw.airlines import airline_of, supplement

NEW_CODES = ["3U", "SC", "ZH", "9C"]


@pytest.fixture(scope="module")
def supplemented(real_tables):
    return supplement(real_tables, config.SEED)


def test_airline_of():
    assert airline_of("MU5138") == "MU"
    assert airline_of("3U8881") == "3U"
    assert airline_of("9C9001") == "9C"


def test_originals_untouched(real_tables, supplemented):
    src = real_tables["ticket"]
    n = len(src)
    assert n == 568917
    out = supplemented["ticket"]
    head = out.iloc[:n]
    pd.testing.assert_frame_equal(
        head.drop(columns="IsSupplemented").reset_index(drop=True),
        src.reset_index(drop=True))
    assert (head["IsSupplemented"] == 0).all()
    assert "IsSupplemented" not in src.columns  # input not mutated


def test_supplement_flags(real_tables, supplemented):
    out = supplemented["ticket"]
    new = out[out["IsSupplemented"] == 1]
    assert len(new) == 4 * 3 * 20
    assert out["TicketID"].is_unique
    assert new["TicketID"].min() == real_tables["ticket"]["TicketID"].max() + 1
    assert set(new["FlightNo"].map(airline_of)) == set(NEW_CODES)
    assert set(new["FlightNo"]) == {f"{c}{n}" for c in NEW_CODES for n in (9001, 9002, 9003)}
    assert (new.groupby("FlightNo").size() == 20).all()
    assert new["delayTime"].between(0, 60).all()
    dep = pd.to_datetime(new["departureTime"])
    arr = pd.to_datetime(new["arrivalTime"])
    assert ((arr - dep) == pd.Timedelta(hours=2, minutes=30)).all()
    assert dep.min() >= pd.Timestamp("2021-01-04")
    assert dep.max() < pd.Timestamp("2021-08-23")


def test_airline_count(supplemented):
    fact, ticket = supplemented["fact"], supplemented["ticket"]
    assert len(fact) == 600
    flight = fact.merge(ticket, on="TicketID", how="left")["FlightNo"]
    assert flight.notna().all()
    assert flight.map(airline_of).nunique() >= config.TARGET_AIRLINES


def test_groups_stay_together(real_tables, supplemented):
    before, after = real_tables["fact"], supplemented["fact"]
    pairs = pd.DataFrame({"old": before["TicketID"].to_numpy(),
                          "new": after["TicketID"].to_numpy()})
    assert (pairs.groupby("old")["new"].nunique() == 1).all()
    # moved groups go to supplemental tickets, and no two old groups share one
    moved = pairs[pairs["old"] != pairs["new"]]
    assert len(moved) > 0
    flags = supplemented["ticket"].set_index("TicketID")["IsSupplemented"]
    assert (flags.loc[moved["new"]] == 1).all()
    assert moved.groupby("new")["old"].nunique().max() == 1


def test_other_fact_columns_unchanged(real_tables, supplemented):
    cols = [c for c in real_tables["fact"].columns if c != "TicketID"]
    pd.testing.assert_frame_equal(real_tables["fact"][cols], supplemented["fact"][cols])


def test_deterministic_and_no_mutation(real_tables):
    fact_before = real_tables["fact"].copy()
    a = supplement(real_tables, 7)
    b = supplement(real_tables, 7)
    pd.testing.assert_frame_equal(a["fact"], b["fact"])
    pd.testing.assert_frame_equal(a["ticket"], b["ticket"])
    pd.testing.assert_frame_equal(real_tables["fact"], fact_before)
    assert a["airline"] is real_tables["airline"] or a["airline"].equals(real_tables["airline"])
