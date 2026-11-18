"""Planes, cabins, mileage, price and price range for the fact rows.

Everything here is derived from the flight number of each fact row (fact ->
ticket.FlightNo -> routes), so the fact table stays internally consistent:
airports, plane, mileage and price all agree with the route.
"""
import numpy as np
import pandas as pd

from fdw import config
from fdw.geo import haversine_km

# Plane size classes from SeatNum (the plane dim's model names are Chinese with
# inconsistent size markers, so seat count is the simpler, uniform signal; the
# warehouse's DimPlane.SizeClass uses the same thresholds):
#   wide-body : SeatNum >= WIDE_MIN_SEATS
#   narrow    : SeatNum <  WIDE_MIN_SEATS (includes the small regional jets,
#               SeatNum < config.MIN_PREMIUM_CABIN_SEATS, which carry class Y only)
WIDE_MIN_SEATS = 250
WIDE_ROUTE_KM = 1500.0     # routes at least this long fly wide-body planes
NARROW_ROUTE_KM = 800.0    # routes shorter than this fly narrow planes
SEATS_PER_ROW = 4          # seat rows above ceil(SeatNum / 4) do not fit the plane


def _coords(airport: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """{AirportID: (lat, lon)}; Ariport_y is latitude, Ariport_X longitude."""
    return {int(i): (float(la), float(lo)) for i, la, lo in
            zip(airport["AirportID"], airport["Ariport_y"], airport["Ariport_X"])}


def _dist(coords: dict, a: int, b: int) -> float:
    return haversine_km(*coords[a], *coords[b])


def estimate_fare_anchors(tables: dict) -> dict[str, float]:
    """Full fare per cabin class at config.FARE_REF_KM, from the SOURCE fact rows.

    For Y and C: median over the class's source rows (fact joined to seat) of
    Price / Rate, normalised to the reference distance with the same taper as
    full_fare (the source mileage is 1178 km = FARE_REF_KM on every row, so this
    is simply the median full fare). The source has no F rows, so
    F = config.F_OVER_C x C. Call this before the fact's Price, mileage and
    CabinID are overwritten.
    """
    fact = tables["fact"]
    cls = fact["CabinID"].map(tables["seat"].drop_duplicates("CabinID")
                              .set_index("CabinID")["CabinClass"])
    at_ref = (fact["Price"].astype(float) / fact["Rate"].astype(float)
              / (fact["mileage"].astype(float) / config.FARE_REF_KM) ** config.FARE_DISTANCE_ALPHA)
    med = at_ref.groupby(cls).median()
    for k in ("Y", "C"):
        if k not in med.index or not med[k] > 0:
            raise ValueError(f"cannot estimate the full fare for class {k}")
    return {"Y": float(med["Y"]), "C": float(med["C"]), "F": config.F_OVER_C * float(med["C"])}


def full_fare(anchor: float, km):
    """Full (Rate 1.0) fare for a flight of ``km`` km: tapers with distance (ALPHA < 1)."""
    return anchor * (np.asarray(km, dtype=float) / config.FARE_REF_KM) ** config.FARE_DISTANCE_ALPHA


def _quota_counts(n: int, mix: dict[str, float]) -> dict[str, int]:
    """Integer counts per class summing to n (largest-remainder rounding)."""
    raw = {k: n * v for k, v in mix.items()}
    counts = {k: int(v) for k, v in raw.items()}
    short = n - sum(counts.values())
    for k in sorted(raw, key=lambda k: (raw[k] - counts[k], k), reverse=True)[:short]:
        counts[k] += 1
    return counts


def _assign_planes(plane: pd.DataFrame, flights: list[str], km: dict[str, float],
                   rng: np.random.Generator) -> dict[str, int]:
    """One PlaneID per flight number, by route length; cycles pools for variety."""
    p = plane.drop_duplicates("PlaneID").sort_values("PlaneID")
    pools = {
        "wide": [int(i) for i in p.loc[p["SeatNum"] >= WIDE_MIN_SEATS, "PlaneID"]],
        "narrow": [int(i) for i in p.loc[p["SeatNum"] < WIDE_MIN_SEATS, "PlaneID"]],
        "any": [int(i) for i in p["PlaneID"]],
    }
    queues = {k: [] for k in pools}

    def draw(kind: str) -> int:
        if not pools[kind]:
            kind = "any"
        if not queues[kind]:
            queues[kind] = [pools[kind][int(j)] for j in rng.permutation(len(pools[kind]))]
        return queues[kind].pop()

    out = {}
    for f in flights:
        d = km[f]
        kind = "wide" if d >= WIDE_ROUTE_KM else "narrow" if d < NARROW_ROUTE_KM else "any"
        out[f] = draw(kind)
    return out


def apply_routes_and_attributes(tables: dict, routes: pd.DataFrame, seed: int) -> dict:
    """Return new tables whose fact rows are consistent with their flight's route.

    Sets Departure/Transit/Landing airport, PlaneID (one per flight number),
    CabinID (deterministic quotas following config.CABIN_MIX), mileage (km,
    haversine incl. the transit leg), Price (= round(full fare x Rate, -1)) and
    PriceRangeID. ian, PassengerID, Rate and the row count are untouched.
    F and C cabins are only given to rows whose plane has at least
    config.MIN_PREMIUM_CABIN_SEATS seats; the seat row fits the plane.
    """
    anchors = estimate_fare_anchors(tables)      # needs the source Price/mileage/CabinID
    rng = np.random.default_rng(seed)

    fact = tables["fact"].copy()
    airport = tables["airport"]
    coords = _coords(airport)

    # --- flight number of every fact row -> its route -------------------------
    tk = tables["ticket"].drop_duplicates("TicketID").set_index("TicketID")["FlightNo"]
    flight = fact["TicketID"].map(tk)
    r = routes.drop_duplicates("FlightNo").set_index("FlightNo")
    if flight.isna().any() or not flight.isin(r.index).all():
        missing = sorted(set(flight[~flight.isin(r.index)].dropna()))
        raise ValueError(f"fact rows without a route (flights {missing}, "
                         f"{int(flight.isna().sum())} rows without a ticket)")
    dep = flight.map(r["DepAirportID"]).astype("Int64")
    land = flight.map(r["LandAirportID"]).astype("Int64")
    transit = flight.map(r["TransitAirportID"]).astype("Int64")
    fact["Departure_ariportID"] = dep
    fact["Transit_ariportID"] = transit
    fact["Landing_ariportID"] = land

    # --- mileage per flight (computed once per route) -------------------------
    flights = sorted(set(flight))
    direct_km, mileage = {}, {}
    for f in flights:
        d, l, t = r.at[f, "DepAirportID"], r.at[f, "LandAirportID"], r.at[f, "TransitAirportID"]
        direct_km[f] = _dist(coords, int(d), int(l))
        if pd.isna(t):
            mileage[f] = direct_km[f]
        else:
            mileage[f] = _dist(coords, int(d), int(t)) + _dist(coords, int(t), int(l))
    fact["mileage"] = flight.map(mileage).round().astype("int64")

    # --- plane: one per flight number -----------------------------------------
    plane_of = _assign_planes(tables["plane"], flights, direct_km, rng)
    fact["PlaneID"] = flight.map(plane_of).astype("Int64")

    # --- cabin: class quotas over the rows, F/C only on planes with >= 100 seats --
    n = len(fact)
    counts = _quota_counts(n, config.CABIN_MIX)
    seat_num = fact["PlaneID"].map(tables["plane"].drop_duplicates("PlaneID")
                                   .set_index("PlaneID")["SeatNum"]).astype(int).to_numpy()
    eligible = np.flatnonzero(seat_num >= config.MIN_PREMIUM_CABIN_SEATS)
    premium = [k for k in sorted(counts) if k != "Y"]          # C, F
    if sum(counts[k] for k in premium) > len(eligible):
        raise ValueError(f"only {len(eligible)} rows on planes with >= "
                         f"{config.MIN_PREMIUM_CABIN_SEATS} seats for the F/C quotas")
    labels = np.full(n, "Y", dtype=object)
    picked = eligible[rng.permutation(len(eligible))]
    start = 0
    for k in premium:
        labels[picked[start:start + counts[k]]] = k
        start += counts[k]

    seat = tables["seat"].drop_duplicates("CabinID").sort_values("CabinID")
    by_class = {k: seat[seat["CabinClass"] == k] for k in counts}
    for k, rows in by_class.items():
        if rows.empty and counts[k] > 0:
            raise ValueError(f"no seat rows of class {k}")
    cabin = []
    for k, seats in zip(labels, seat_num):
        rows = by_class[k]
        fit = rows.loc[rows["SeatRow"] <= np.ceil(seats / SEATS_PER_ROW), "CabinID"].to_numpy()
        ids = fit if len(fit) else rows["CabinID"].to_numpy()
        cabin.append(int(ids[int(rng.integers(len(ids)))]))
    fact["CabinID"] = pd.array(cabin, dtype="Int64")

    # --- price = round(full fare x Rate, -1); the top-band clip is a safety net --
    cls = pd.Series(labels, index=fact.index)
    full = pd.Series(np.nan, index=fact.index)
    for k, a in anchors.items():
        m = cls == k
        full[m] = full_fare(a, fact.loc[m, "mileage"].to_numpy())
    price = np.floor(full * fact["Rate"].astype(float) / 10.0 + 0.5) * 10.0

    pr = tables["price_range"].drop_duplicates("PriceRangeID").sort_values("MinNum")
    mins, maxs = pr["MinNum"].to_numpy(), pr["MaxNum"].to_numpy()
    price = price.clip(lower=float(mins[0]), upper=float(maxs[-1] - 10))
    pos = np.searchsorted(mins, price.to_numpy(), side="right") - 1
    fact["Price"] = price.astype("int64")
    fact["PriceRangeID"] = pd.array(pr["PriceRangeID"].to_numpy()[pos], dtype="Int64")

    new = dict(tables)
    new["fact"] = fact
    return new
