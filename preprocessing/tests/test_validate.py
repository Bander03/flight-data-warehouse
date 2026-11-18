"""Tests for the guide #2 rule validator (pure, synthetic data only)."""
import pandas as pd
import pytest

from conftest import make_valid_tables
from fdw.validate import RuleResult, ValidationError, assert_valid, validate_fact

RULE_NAMES = [
    "departure_airports_ge_20", "landing_airports_ge_20", "departure_ne_landing",
    "transit_ne_ends", "stopover_rows_ge_20", "passengers_ge_50",
    "date_span_ge_6_months", "airlines_ge_10", "plane_not_blank",
    "plane_not_constant", "cabin_not_blank", "cabin_not_constant",
    "row_count_preserved", "ian_unique", "foreign_keys_exist",
    "price_in_range", "arrival_ge_departure",
]

DEP, TRA, LAN = "Departure_ariportID", "Transit_ariportID", "Landing_ariportID"


def _run(tables, expected_rows=None):
    n = len(make_valid_tables()["fact"]) if expected_rows is None else expected_rows
    return validate_fact(tables, expected_rows=n)


def _by_name(results):
    return {r.name: r for r in results}


def _remap(fact, col, pool):
    """Reassign ``col`` from ``pool`` so it never equals the row's other airport columns.

    Keeps departure != landing and transit != ends intact while shrinking the
    number of distinct airports in ``col``.
    """
    others = [c for c in (DEP, TRA, LAN) if c != col]
    new = []
    for i, (_, row) in enumerate(fact.iterrows()):
        taken = {row[c] for c in others if not pd.isna(row[c])}
        cands = [p for p in pool[i % len(pool):] + pool[:i % len(pool)] if p not in taken]
        new.append(cands[0])
    fact[col] = pd.array(new, dtype="Int64")


# --- one mutation per rule: break exactly that rule --------------------------

def _m_departure_airports(t):
    _remap(t["fact"], DEP, list(range(1, 11)))        # 10 distinct departures


def _m_landing_airports(t):
    _remap(t["fact"], LAN, list(range(1, 11)))        # 10 distinct landings


def _m_departure_eq_landing(t):
    # row 1 has no stopover; landing := departure
    t["fact"].loc[1, LAN] = t["fact"].loc[1, DEP]


def _m_transit_eq_end(t):
    # row 0 has a stopover; transit := departure (30 stopover rows remain)
    t["fact"].loc[0, TRA] = t["fact"].loc[0, DEP]


def _m_stopover_rows(t):
    f = t["fact"]
    has = f.index[f[TRA].notna()]
    f.loc[has[19:], TRA] = pd.NA                      # keep only 19 stopover rows


def _m_passengers(t):
    f = t["fact"]
    f["PassengerID"] = pd.array([1000 + i % 40 for i in range(len(f))], dtype="Int64")


def _m_date_span(t):
    f = t["fact"]
    ids = pd.array([1 + i % 28 for i in range(len(f))], dtype="Int64")  # all January
    f["DepartureDateID"] = ids
    f["ArrivalDateID"] = ids


def _m_airlines(t):
    t["ticket"]["FlightNo"] = ["MU" + no[2:] for no in t["ticket"]["FlightNo"]]


def _m_plane_blank(t):
    t["fact"].loc[3, "PlaneID"] = pd.NA


def _m_plane_constant(t):
    t["fact"]["PlaneID"] = pd.array([2] * len(t["fact"]), dtype="Int64")


def _m_cabin_blank(t):
    t["fact"].loc[3, "CabinID"] = pd.NA


def _m_cabin_constant(t):
    t["fact"]["CabinID"] = pd.array([5] * len(t["fact"]), dtype="Int64")


def _m_row_count(t):
    t["fact"] = t["fact"].iloc[:-1].reset_index(drop=True)


def _m_ian_dup(t):
    t["fact"].loc[1, "ian"] = t["fact"].loc[0, "ian"]


def _m_foreign_key(t):
    t["fact"].loc[0, "PassengerID"] = 99999           # not in the passenger table


def _m_price(t):
    t["fact"].loc[0, "Price"] = 99990                 # far above the row's range


def _m_arrival_before_departure(t):
    f = t["fact"]
    f.loc[5, "ArrivalDateID"] = f.loc[5, "DepartureDateID"] - 1


MUTATIONS = {
    "departure_airports_ge_20": _m_departure_airports,
    "landing_airports_ge_20": _m_landing_airports,
    "departure_ne_landing": _m_departure_eq_landing,
    "transit_ne_ends": _m_transit_eq_end,
    "stopover_rows_ge_20": _m_stopover_rows,
    "passengers_ge_50": _m_passengers,
    "date_span_ge_6_months": _m_date_span,
    "airlines_ge_10": _m_airlines,
    "plane_not_blank": _m_plane_blank,
    "plane_not_constant": _m_plane_constant,
    "cabin_not_blank": _m_cabin_blank,
    "cabin_not_constant": _m_cabin_constant,
    "row_count_preserved": _m_row_count,
    "ian_unique": _m_ian_dup,
    "foreign_keys_exist": _m_foreign_key,
    "price_in_range": _m_price,
    "arrival_ge_departure": _m_arrival_before_departure,
}


# --- tests --------------------------------------------------------------------

def test_mutations_cover_every_rule():
    assert list(MUTATIONS) == RULE_NAMES


def test_synthetic_set_is_deterministic():
    a, b = make_valid_tables(), make_valid_tables()
    for key in a:
        pd.testing.assert_frame_equal(a[key], b[key])


def test_valid_tables_pass(valid_tables):
    results = _run(valid_tables)
    assert [r.name for r in results] == RULE_NAMES
    assert all(isinstance(r, RuleResult) for r in results)
    failed = [(r.name, r.detail) for r in results if not r.passed]
    assert failed == []


@pytest.mark.parametrize("rule", RULE_NAMES)
def test_rule_fails(rule, valid_tables):
    MUTATIONS[rule](valid_tables)
    results = _by_name(_run(valid_tables))
    assert results[rule].passed is False
    assert results[rule].detail                        # explains the failure
    others = {n: r.passed for n, r in results.items() if n != rule}
    assert all(others.values()), f"unexpectedly failing: {[n for n, ok in others.items() if not ok]}"


def test_mutation_does_not_touch_other_fixture_instances():
    t = make_valid_tables()
    _m_passengers(t)
    assert all(r.passed for r in _run(make_valid_tables()))


@pytest.mark.parametrize("col, table, key", [
    ("PriceRangeID", "price_range", "PriceRangeID"),
    (DEP, "airport", "AirportID"),
    (TRA, "airport", "AirportID"),
    (LAN, "airport", "AirportID"),
    ("DepartureDateID", "date", "DateRangeID"),
    ("ArrivalDateID", "date", "DateRangeID"),
    ("PassengerID", "passenger", "PassengerID"),
    ("TicketID", "ticket", "TicketID"),
    ("PlaneID", "plane", "PlaneID"),
    ("CabinID", "seat", "CabinID"),
])
def test_every_foreign_key_is_checked(col, table, key, valid_tables):
    row = valid_tables["fact"].index[valid_tables["fact"][col].notna()][0]
    valid_tables["fact"].loc[row, col] = 99999
    assert _by_name(_run(valid_tables))["foreign_keys_exist"].passed is False


def test_null_transit_is_not_a_foreign_key_error(valid_tables):
    f = valid_tables["fact"]
    assert f[TRA].isna().any()
    assert _by_name(_run(valid_tables))["foreign_keys_exist"].passed is True


@pytest.mark.parametrize("col", ["PriceRangeID", DEP, LAN, "DepartureDateID",
                                 "ArrivalDateID", "PassengerID", "TicketID"])
def test_null_required_foreign_key_fails(col, valid_tables):
    valid_tables["fact"].loc[0, col] = pd.NA
    assert _by_name(_run(valid_tables))["foreign_keys_exist"].passed is False


def test_exactly_twenty_departures_passes(valid_tables):
    _remap(valid_tables["fact"], DEP, list(range(1, 21)))
    results = _by_name(_run(valid_tables))
    assert results["departure_airports_ge_20"].passed is True
    assert results["departure_ne_landing"].passed is True


def test_nineteen_departures_fails(valid_tables):
    _remap(valid_tables["fact"], DEP, list(range(1, 20)))
    assert _by_name(_run(valid_tables))["departure_airports_ge_20"].passed is False


def test_exactly_twenty_stopover_rows_passes(valid_tables):
    f = valid_tables["fact"]
    has = f.index[f[TRA].notna()]
    f.loc[has[20:], TRA] = pd.NA
    assert f[TRA].notna().sum() == 20
    assert _by_name(_run(valid_tables))["stopover_rows_ge_20"].passed is True


def test_five_months_fails_six_months_passes(valid_tables):
    f = valid_tables["fact"]
    dates = valid_tables["date"].set_index("DateRangeID")["Date"]
    months = pd.to_datetime(dates.loc[f["DepartureDateID"].astype(int)]).dt.month

    def with_months(allowed):
        out = f.copy()
        keep = months.isin(allowed).to_numpy()
        # rows outside ``allowed`` take the date of the first row inside it
        first = f.loc[keep, "DepartureDateID"].iloc[0]
        for c in ("DepartureDateID", "ArrivalDateID"):
            out.loc[~keep, c] = first
        return out

    valid_tables["fact"] = with_months({1, 2, 3, 4, 5})
    assert _by_name(_run(valid_tables))["date_span_ge_6_months"].passed is False
    valid_tables["fact"] = with_months({1, 2, 3, 4, 5, 6})
    assert _by_name(_run(valid_tables))["date_span_ge_6_months"].passed is True


def test_months_are_counted_from_the_date_table(valid_tables):
    # relabel every February date as January: 8 distinct months become 7
    d = valid_tables["date"]
    d.loc[d["Date"].str.startswith("2021-02"), "Date"] = (
        d.loc[d["Date"].str.startswith("2021-02"), "Date"].str.replace("2021-02", "2021-01"))
    results = _by_name(_run(valid_tables))
    assert results["date_span_ge_6_months"].passed is True    # 8 -> 7 months


def test_blank_string_plane_counts_as_blank(valid_tables):
    valid_tables["fact"]["PlaneID"] = valid_tables["fact"]["PlaneID"].astype(object)
    valid_tables["fact"].loc[0, "PlaneID"] = "  "
    assert _by_name(_run(valid_tables))["plane_not_blank"].passed is False


def test_null_ian_is_not_unique(valid_tables):
    valid_tables["fact"].loc[0, "ian"] = pd.NA
    assert _by_name(_run(valid_tables))["ian_unique"].passed is False


def test_price_on_range_boundary_is_in_range(valid_tables):
    f = valid_tables["fact"]
    rid = int(f.loc[0, "PriceRangeID"])
    pr = valid_tables["price_range"].set_index("PriceRangeID")
    f.loc[0, "Price"] = int(pr.loc[rid, "MaxNum"])
    assert _by_name(_run(valid_tables))["price_in_range"].passed is True


def test_assert_valid_returns_none_when_valid(valid_tables):
    assert assert_valid(valid_tables, expected_rows=len(valid_tables["fact"])) is None


def test_assert_valid_lists_all_failures(valid_tables):
    _m_ian_dup(valid_tables)
    _m_airlines(valid_tables)
    with pytest.raises(ValidationError) as exc:
        assert_valid(valid_tables, expected_rows=len(valid_tables["fact"]))
    msg = str(exc.value)
    assert "ian_unique" in msg and "airlines_ge_10" in msg
    assert "plane_not_blank" not in msg                # passing rules are not listed


def test_default_expected_rows_is_600(valid_tables):
    # the synthetic set has 60 rows, so the default of 600 must flag it
    results = _by_name(validate_fact(valid_tables))
    assert results["row_count_preserved"].passed is False


def test_null_nullable_int_price_fails_price_in_range(valid_tables):
    f = valid_tables["fact"]
    f["Price"] = f["Price"].astype("Int64")            # nullable, like the real loader
    f.loc[0, "Price"] = pd.NA
    results = _by_name(_run(valid_tables))
    assert results["price_in_range"].passed is False
    others = {n: r.passed for n, r in results.items() if n != "price_in_range"}
    assert all(others.values())


@pytest.mark.parametrize("missing", [None, pd.NA, float("nan"), "", "   "])
def test_null_or_blank_flight_numbers_are_not_airlines(missing, valid_tables):
    # 9 real airlines; the tickets of the other 2 get a null/blank FlightNo
    t = valid_tables["ticket"]
    t["FlightNo"] = t["FlightNo"].astype(object)
    drop = t["FlightNo"].str[:2].isin(["9C", "ZH"])
    assert drop.sum() >= 2                              # at least two bogus-code tickets
    t.loc[drop, "FlightNo"] = missing
    results = _by_name(_run(valid_tables))
    assert results["airlines_ge_10"].passed is False
    assert "9 distinct" in results["airlines_ge_10"].detail
    others = {n: r.passed for n, r in results.items() if n != "airlines_ge_10"}
    assert all(others.values())
