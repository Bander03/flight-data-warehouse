import numpy as np
import pandas as pd
import pytest

from fdw import config
from fdw.airlines import supplement
from fdw.assign import apply_routes_and_attributes, estimate_fare_anchors, full_fare
from fdw.dates import spread_dates
from fdw.geo import airport_distance_km
from fdw.passengers import repair_passenger_keys
from fdw.routes import build_routes
from fdw.validate import validate_fact


@pytest.fixture(scope="module")
def prepared(real_tables):
    """Tables after supplement -> build_routes -> spread_dates (the pipeline order)."""
    sup = supplement(real_tables, config.SEED)
    routes = build_routes(sup, config.SEED)
    spread = spread_dates(sup, config.SEED)
    return spread, routes


@pytest.fixture(scope="module")
def anchors(prepared):
    return estimate_fare_anchors(prepared[0])


@pytest.fixture(scope="module")
def out(prepared):
    tables, routes = prepared
    return apply_routes_and_attributes(tables, routes, config.SEED)


@pytest.fixture(scope="module")
def fact_view(out, prepared):
    """Final fact rows with their flight number and the route of that flight."""
    routes = prepared[1].set_index("FlightNo")
    tk = out["ticket"].drop_duplicates("TicketID").set_index("TicketID")["FlightNo"]
    f = out["fact"].copy()
    f["FlightNo"] = f["TicketID"].map(tk)
    return f.join(routes, on="FlightNo")


def _class_of(fact, seat):
    return fact["CabinID"].map(seat.set_index("CabinID")["CabinClass"])


def test_estimate_fare_anchors(anchors):
    """Anchors = source median of Price / Rate per class at the source's 1178 km."""
    assert set(anchors) == {"Y", "C", "F"}
    assert all(isinstance(v, float) and v > 0 for v in anchors.values())
    assert anchors["Y"] == pytest.approx(1489.13, abs=0.01)
    assert anchors["C"] == pytest.approx(5555.56, abs=0.01)
    assert anchors["F"] == pytest.approx(config.F_OVER_C * anchors["C"])


def test_full_fare_class_order_at_same_distance(anchors):
    for km in (300, 800, 1178, 2000, 3630, 4500):
        y, c, f = (full_fare(anchors[k], km) for k in "YCF")
        assert f > c > y, km
    assert full_fare(anchors["Y"], config.FARE_REF_KM) == pytest.approx(anchors["Y"])


def test_full_fare_monotonic_in_distance(anchors):
    km = np.arange(300, 5000, 50, dtype=float)
    for k in "YCF":
        fares = np.array([full_fare(anchors[k], d) for d in km])
        assert (np.diff(fares) > 0).all(), k


def test_price_monotonic_in_distance_for_fixed_class_and_rate(out):
    """Real rows: same class and Rate, longer flight -> price never lower."""
    f = out["fact"].copy()
    f["cls"] = _class_of(f, out["seat"])
    f["rate2"] = f["Rate"].astype(float).round(2)
    groups = 0
    for _, g in f.groupby(["cls", "rate2"]):
        g = g.sort_values(["mileage", "Price"])
        if g["mileage"].nunique() > 1:
            groups += 1
            assert g["Price"].is_monotonic_increasing, g[["mileage", "Price"]]
    assert groups > 10


def test_airports_set_from_routes(fact_view):
    f = fact_view
    assert (f["Departure_ariportID"] == f["DepAirportID"]).all()
    assert (f["Landing_ariportID"] == f["LandAirportID"]).all()
    assert (f["Transit_ariportID"].fillna(-1) == f["TransitAirportID"].fillna(-1)).all()
    assert (f["Departure_ariportID"] != f["Landing_ariportID"]).all()
    assert str(f["Departure_ariportID"].dtype) == "Int64"
    assert str(f["Transit_ariportID"].dtype) == "Int64"


def test_plane_cabin_not_blank_nor_constant(out):
    f = out["fact"]
    assert f["PlaneID"].notna().all() and f["CabinID"].notna().all()
    assert f["PlaneID"].nunique() >= 5
    assert f["CabinID"].nunique() > 1
    assert f["PlaneID"].isin(out["plane"]["PlaneID"]).all()
    assert f["CabinID"].isin(out["seat"]["CabinID"]).all()


def test_plane_constant_per_flight_number(fact_view):
    assert (fact_view.groupby("FlightNo")["PlaneID"].nunique() == 1).all()


def test_plane_size_matches_route_length(fact_view, out):
    seats = out["plane"].set_index("PlaneID")["SeatNum"]
    airport = out["airport"]
    flights = fact_view.drop_duplicates("FlightNo")
    n_checked = 0
    for _, r in flights.iterrows():
        km = airport_distance_km(airport, int(r["DepAirportID"]), int(r["LandAirportID"]))
        s = seats[r["PlaneID"]]
        if km >= 1500:
            assert s >= 250
            n_checked += 1
        elif km < 800:
            assert s < 250
            n_checked += 1
    assert n_checked > 0


def test_cabin_mix_within_5_points(out):
    cls = _class_of(out["fact"], out["seat"])
    share = cls.value_counts(normalize=True)
    for k, target in config.CABIN_MIX.items():
        assert abs(share.get(k, 0.0) - target) <= 0.05, (k, share.to_dict())


def test_mileage_includes_transit_leg(fact_view, out):
    airport = out["airport"]
    stop = fact_view[fact_view["Transit_ariportID"].notna()]
    assert len(stop) >= 20
    for _, r in stop.drop_duplicates("FlightNo").iterrows():
        d, t, l = (int(r["Departure_ariportID"]), int(r["Transit_ariportID"]),
                   int(r["Landing_ariportID"]))
        direct = airport_distance_km(airport, d, l)
        assert direct < r["mileage"] <= 1.25 * direct + 1
        legs = airport_distance_km(airport, d, t) + airport_distance_km(airport, t, l)
        assert abs(r["mileage"] - legs) <= 1
    direct_rows = fact_view[fact_view["Transit_ariportID"].isna()].drop_duplicates("FlightNo")
    for _, r in direct_rows.head(10).iterrows():
        direct = airport_distance_km(airport, int(r["Departure_ariportID"]),
                                     int(r["Landing_ariportID"]))
        assert abs(r["mileage"] - direct) <= 1
    assert pd.api.types.is_integer_dtype(out["fact"]["mileage"])
    assert out["fact"]["mileage"].nunique() > 20


def test_price_matches_formula(out, prepared):
    """Recompute every price independently from the source fact (no fdw.assign helpers)."""
    src, seat = prepared[0]["fact"], prepared[0]["seat"]
    src_cls = _class_of(src, seat)
    med = (src["Price"].astype(float) / src["Rate"].astype(float)).groupby(src_cls).median()
    anchor = {"Y": med["Y"], "C": med["C"], "F": config.F_OVER_C * med["C"]}
    f = out["fact"]
    cls = _class_of(f, out["seat"])
    full = (cls.map(anchor) * (f["mileage"].astype(float) / 1178.0)
            ** config.FARE_DISTANCE_ALPHA)
    expected = full * f["Rate"].astype(float)
    assert ((f["Price"] - expected).abs() <= 5 + 1e-6).all()
    assert (f["Price"] % 10 == 0).all()


def test_no_clipped_prices(out):
    """The top-band clip is only a safety net: no real row reaches it."""
    f = out["fact"]
    top = int(out["price_range"]["MaxNum"].max()) - 10
    assert int((f["Price"] >= top).sum()) == 0
    assert f["Price"].min() >= int(out["price_range"]["MinNum"].min())


def test_average_price_ordered_by_class(out):
    f = out["fact"]
    avg = f["Price"].groupby(_class_of(f, out["seat"])).mean()
    assert avg["F"] > avg["C"] > avg["Y"]


def test_premium_cabins_only_on_planes_with_100_seats(out):
    f = out["fact"]
    cls = _class_of(f, out["seat"])
    seats = f["PlaneID"].map(out["plane"].drop_duplicates("PlaneID").set_index("PlaneID")["SeatNum"])
    premium = cls.isin(["F", "C"])
    assert (seats[premium] >= config.MIN_PREMIUM_CABIN_SEATS).all()
    assert (seats < config.MIN_PREMIUM_CABIN_SEATS).any()      # small planes are used (class Y)


def test_seat_row_plausible_for_plane(out):
    f = out["fact"]
    seat = out["seat"].drop_duplicates("CabinID").set_index("CabinID")
    seats = f["PlaneID"].map(out["plane"].drop_duplicates("PlaneID").set_index("PlaneID")["SeatNum"])
    rows = f["CabinID"].map(seat["SeatRow"])
    assert (rows <= np.ceil(seats / 4)).all()


def test_price_range_valid(out):
    f = out["fact"]
    pr = out["price_range"].drop_duplicates("PriceRangeID").set_index("PriceRangeID")
    lo = f["PriceRangeID"].map(pr["MinNum"])
    hi = f["PriceRangeID"].map(pr["MaxNum"])
    assert ((f["Price"] >= lo) & (f["Price"] < hi)).all()
    assert f["PriceRangeID"].nunique() > 3


def test_rate_ian_passenger_unchanged(out, prepared):
    old, new = prepared[0]["fact"], out["fact"]
    assert len(new) == len(old) == 600
    for c in ["Rate", "ian", "PassengerID"]:
        assert (old[c].to_numpy() == new[c].to_numpy()).all()


def test_inputs_not_mutated(prepared):
    tables, routes = prepared
    before = {k: v.copy() for k, v in tables.items() if k in ("fact", "seat", "plane")}
    r_before = routes.copy()
    apply_routes_and_attributes(tables, routes, config.SEED)
    for k, v in before.items():
        pd.testing.assert_frame_equal(tables[k], v)
    pd.testing.assert_frame_equal(routes, r_before)


def test_deterministic(prepared, out):
    again = apply_routes_and_attributes(prepared[0], prepared[1], config.SEED)
    pd.testing.assert_frame_equal(again["fact"], out["fact"])


def test_final_tables_pass_validation(out):
    """After the passenger-key repair (ruling R4) all 17 rules pass."""
    repaired = repair_passenger_keys(out, config.SEED)
    results = validate_fact(repaired)
    assert len(results) == 17
    failed = {r.name: r.detail for r in results if not r.passed}
    assert not failed, failed
