import numpy as np
import pandas as pd
import pytest

from fdw import config
from fdw.airlines import airline_of, supplement
from fdw.geo import airport_distance_km
from fdw.routes import build_routes, pick_transit


@pytest.fixture(scope="module")
def tables(real_tables):
    return supplement(real_tables, config.SEED)


@pytest.fixture(scope="module")
def routes(tables):
    return build_routes(tables, config.SEED)


@pytest.fixture(scope="module")
def fact_routes(tables, routes):
    """One row per fact row, joined to the route of its ticket's flight number."""
    m = tables["fact"][["TicketID"]].merge(
        tables["ticket"][["TicketID", "FlightNo"]], on="TicketID", how="left")
    return m.merge(routes, on="FlightNo", how="left")


def _id(airport, code):
    return int(airport.loc[airport["airportCode"] == code, "AirportID"].iloc[0])


def test_pick_transit_between(real_tables):
    ap = real_tables["airport"]
    pek, can = _id(ap, "PEK"), _id(ap, "CAN")
    rng = np.random.default_rng(1)
    t = pick_transit(ap, pek, can, rng)
    assert t is not None and t not in (pek, can)
    d = airport_distance_km(ap, pek, can)
    d1, d2 = airport_distance_km(ap, pek, t), airport_distance_km(ap, t, can)
    assert d1 >= config.MIN_STOP_KM and d2 >= config.MIN_STOP_KM
    assert d1 + d2 <= config.DETOUR_MAX * d + 1e-9


def test_pick_transit_none_for_short_route():
    ap = pd.DataFrame({
        "AirportID": [1, 2, 3],
        "airportCode": ["AAA", "BBB", "CCC"],
        "Ariport_X": [116.40, 116.41, 121.0],
        "Ariport_y": [39.90, 39.91, 31.0],
        "city": ["X", "X", "Y"],
    })
    assert pick_transit(ap, 1, 2, np.random.default_rng(0)) is None


def test_pick_transit_does_not_mutate(real_tables):
    ap = real_tables["airport"]
    before = ap.copy()
    pick_transit(ap, _id(ap, "PEK"), _id(ap, "CAN"), np.random.default_rng(0))
    pd.testing.assert_frame_equal(ap, before)


def test_routes_shape(tables, routes):
    assert list(routes.columns) == ["FlightNo", "DepAirportID", "LandAirportID", "TransitAirportID"]
    assert all(str(routes[c].dtype) == "Int64" for c in routes.columns[1:])
    f = tables["fact"].merge(tables["ticket"][["TicketID", "FlightNo"]], on="TicketID", how="left")
    assert routes["FlightNo"].is_unique
    assert set(routes["FlightNo"]) == set(f["FlightNo"].dropna())


def test_routes_airport_ids_exist(tables, routes):
    ids = set(tables["airport"]["AirportID"])
    for col in ["DepAirportID", "LandAirportID"]:
        assert routes[col].notna().all() and set(routes[col]) <= ids
    assert set(routes["TransitAirportID"].dropna()) <= ids


def test_routes_dep_ne_land_and_min_distance_300(tables, routes):
    ap = tables["airport"]
    assert (routes["DepAirportID"] != routes["LandAirportID"]).all()
    for r in routes.itertuples():
        assert airport_distance_km(ap, int(r.DepAirportID), int(r.LandAirportID)) >= 300


def test_hub_used(tables, routes):
    ap = tables["airport"]
    code_to_id = dict(zip(ap["airportCode"], ap["AirportID"]))
    checked = 0
    for r in routes.itertuples():
        hubs = {int(code_to_id[c]) for c in config.HUBS[airline_of(r.FlightNo)] if c in code_to_id}
        if not hubs:
            continue
        checked += 1
        assert int(r.DepAirportID) in hubs or int(r.LandAirportID) in hubs, r.FlightNo
    assert checked > 0


def test_coverage(fact_routes):
    deps = set(fact_routes["DepAirportID"])
    lands = set(fact_routes["LandAirportID"])
    assert len(deps) >= config.MIN_DEP
    assert len(lands) >= config.MIN_LAND
    assert len(deps | lands) >= 25


def test_stopover_share(fact_routes):
    stop_rows = int(fact_routes["TransitAirportID"].notna().sum())
    assert stop_rows >= config.MIN_STOP_ROWS
    assert stop_rows >= config.STOP_SHARE * len(fact_routes)


def test_stopover_rules(tables, routes):
    ap = tables["airport"]
    for r in routes[routes["TransitAirportID"].notna()].itertuples():
        d, t, l = int(r.DepAirportID), int(r.TransitAirportID), int(r.LandAirportID)
        assert t not in (d, l)
        d1, d2 = airport_distance_km(ap, d, t), airport_distance_km(ap, t, l)
        assert d1 >= config.MIN_STOP_KM and d2 >= config.MIN_STOP_KM
        assert d1 + d2 <= config.DETOUR_MAX * airport_distance_km(ap, d, l) + 1e-9


def test_stopovers_only_on_long_routes(tables, routes):
    ap = tables["airport"]
    stops = routes[routes["TransitAirportID"].notna()]
    assert len(stops) > 0
    for r in stops.itertuples():
        direct = airport_distance_km(ap, int(r.DepAirportID), int(r.LandAirportID))
        assert direct >= config.MIN_STOPOVER_ROUTE_KM, (r.FlightNo, direct)


def test_routes_use_only_coded_airports(tables, routes):
    ap = tables["airport"]
    code = ap.set_index("AirportID")["airportCode"]
    used = (set(routes["DepAirportID"]) | set(routes["LandAirportID"])
            | set(routes["TransitAirportID"].dropna()))
    blank = sorted(int(i) for i in used
                   if pd.isna(code[int(i)]) or not str(code[int(i)]).strip())
    assert blank == [], blank


def test_long_route_selection_keeps_coverage(fact_routes):
    """Coded-only destinations and long-route-only stopovers keep guide #2 coverage."""
    assert fact_routes["DepAirportID"].nunique() >= config.MIN_DEP
    assert fact_routes["LandAirportID"].nunique() >= config.MIN_LAND
    stop_rows = int(fact_routes["TransitAirportID"].notna().sum())
    assert stop_rows >= max(config.MIN_STOP_ROWS, config.STOP_SHARE * len(fact_routes))


def test_deterministic(tables, routes):
    pd.testing.assert_frame_equal(routes, build_routes(tables, config.SEED))


def test_inputs_not_mutated(tables):
    snap = {k: v.copy() for k, v in tables.items()}
    build_routes(tables, config.SEED)
    for k in snap:
        pd.testing.assert_frame_equal(tables[k], snap[k])
