import pandas as pd
import pytest

from fdw import config
from fdw.airlines import supplement
from fdw.dates import spread_dates


@pytest.fixture(scope="module")
def tables(real_tables):
    return supplement(real_tables, config.SEED)


@pytest.fixture(scope="module")
def spread(tables):
    return spread_dates(tables, config.SEED)


@pytest.fixture(scope="module")
def fact_dates(spread):
    """Fact rows joined to their date strings and ticket."""
    date = spread["date"].set_index("DateRangeID")["Date"]
    f = spread["fact"]
    out = pd.DataFrame({
        "dep": pd.to_datetime(f["DepartureDateID"].map(date)),
        "arr": pd.to_datetime(f["ArrivalDateID"].map(date)),
    })
    return out


def test_groups_preserved(tables, spread):
    old, new = tables["fact"]["TicketID"], spread["fact"]["TicketID"]
    assert len(spread["fact"]) == len(tables["fact"]) == 600
    pairs = pd.DataFrame({"old": old, "new": new})
    # rows that shared a ticket still share exactly one ticket ...
    assert (pairs.groupby("old")["new"].nunique() == 1).all()
    # ... and distinct groups do not collapse onto the same ticket
    assert (pairs.groupby("new")["old"].nunique() == 1).all()
    # every new ticket exists
    assert new.isin(tables["ticket"]["TicketID"]).all()


def test_same_flight_number(tables, spread):
    fn = tables["ticket"].set_index("TicketID")["FlightNo"]
    assert (tables["fact"]["TicketID"].map(fn) == spread["fact"]["TicketID"].map(fn)).all()


def test_span_ge_6_months(fact_dates):
    months = fact_dates["dep"].dt.to_period("M").unique()
    assert len(months) >= 6
    assert fact_dates["dep"].min() >= pd.Timestamp("2021-01-01")
    assert fact_dates["dep"].max() < pd.Timestamp("2021-09-01")


def test_many_dates(fact_dates):
    assert fact_dates["dep"].nunique() >= 40


def test_spring_festival_rows(fact_dates):
    in_window = fact_dates["dep"].between("2021-02-11", "2021-02-17")
    assert in_window.sum() >= 5


def test_dates_match_ticket_and_arrival_not_before_departure(spread):
    t = spread["ticket"].set_index("TicketID")
    date = spread["date"].set_index("Date")["DateRangeID"]
    f = spread["fact"]
    dep = f["TicketID"].map(t["departureTime"]).str[:10].map(date)
    arr = f["TicketID"].map(t["arrivalTime"]).str[:10].map(date)
    assert (f["DepartureDateID"] == dep).all()
    assert (f["ArrivalDateID"] == arr).all()
    assert (f["ArrivalDateID"] >= f["DepartureDateID"]).all()
    assert str(f["DepartureDateID"].dtype) == "Int64" and str(f["ArrivalDateID"].dtype) == "Int64"


def test_other_columns_unchanged_and_inputs_not_mutated(tables, spread):
    keep = [c for c in tables["fact"].columns
            if c not in ("TicketID", "DepartureDateID", "ArrivalDateID")]
    pd.testing.assert_frame_equal(tables["fact"][keep], spread["fact"][keep])
    assert spread["fact"] is not tables["fact"]
    pd.testing.assert_frame_equal(tables["ticket"], spread["ticket"])


def test_deterministic(tables, spread):
    again = spread_dates(tables, config.SEED)
    pd.testing.assert_frame_equal(spread["fact"], again["fact"])


def _tiny(tickets):
    days = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    date = pd.DataFrame({"DateRangeID": range(1, len(days) + 1),
                         "Date": [d.strftime("%Y-%m-%d") for d in days]})
    ticket = pd.DataFrame(tickets)
    ticket["TicketID"] = ticket["TicketID"].astype("Int64")
    fact = pd.DataFrame({"TicketID": pd.array([1, 1], dtype="Int64"),
                         "DepartureDateID": pd.array([1, 1], dtype="Int64"),
                         "ArrivalDateID": pd.array([1, 1], dtype="Int64"),
                         "ian": [10, 11]})
    return {"fact": fact, "ticket": ticket, "date": date}


def test_overnight_arrival():
    t = _tiny([{"TicketID": 1, "departureTime": "2021-03-05 08:00:00",
                "arrivalTime": "2021-03-05 10:30:00", "FlightNo": "CA1"},
               {"TicketID": 2, "departureTime": "2021-03-09 21:30:00",
                "arrivalTime": "2021-03-10 00:05:00", "FlightNo": "CA1"}])
    out = spread_dates(t, 1)
    f = out["fact"]
    assert (f["TicketID"] == 2).all()           # moved to the other ticket of CA1
    assert (f["ArrivalDateID"] == f["DepartureDateID"] + 1).all()
    assert (f["ArrivalDateID"] >= f["DepartureDateID"]).all()


def test_single_ticket_flight_stays_put():
    t = _tiny([{"TicketID": 1, "departureTime": "2021-03-09 21:30:00",
                "arrivalTime": "2021-03-10 00:05:00", "FlightNo": "CA1"}])
    out = spread_dates(t, 1)
    assert (out["fact"]["TicketID"] == 1).all()
    assert (out["fact"]["ArrivalDateID"] == out["fact"]["DepartureDateID"] + 1).all()
