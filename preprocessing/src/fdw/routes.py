"""Routes and stopovers: one coherent route per flight number.

A flight number defines its route (departure, landing, optional transit);
every ticket and fact row on that flight inherits it.
"""
import math

import numpy as np
import pandas as pd

from fdw import config
from fdw.airlines import airline_of
from fdw.geo import haversine_km

MIN_ROUTE_KM = 300.0
_COLUMNS = ["FlightNo", "DepAirportID", "LandAirportID", "TransitAirportID"]


def _coords(airport: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """{AirportID: (lat, lon)}; Ariport_y is latitude, Ariport_X longitude."""
    return {int(i): (float(la), float(lo)) for i, la, lo in
            zip(airport["AirportID"], airport["Ariport_y"], airport["Ariport_X"])}


def _coded(airport: pd.DataFrame) -> pd.DataFrame:
    """Airports with a non-blank airportCode (47 of the 184 source airports have none)."""
    code = airport["airportCode"]
    return airport[code.notna() & code.astype(str).str.strip().ne("")]


def _dist(coords: dict, a: int, b: int) -> float:
    return haversine_km(*coords[a], *coords[b])


def _pick_transit(coords: dict, dep_id: int, land_id: int, rng: np.random.Generator):
    direct = _dist(coords, dep_id, land_id)
    cands = []
    for t in sorted(coords):
        if t in (dep_id, land_id):
            continue
        d1, d2 = _dist(coords, dep_id, t), _dist(coords, t, land_id)
        if (d1 >= config.MIN_STOP_KM and d2 >= config.MIN_STOP_KM
                and d1 + d2 <= config.DETOUR_MAX * direct):
            cands.append(t)
    if not cands:
        return None
    return int(cands[int(rng.integers(len(cands)))])


def pick_transit(airport: pd.DataFrame, dep_id: int, land_id: int,
                 rng: np.random.Generator) -> int | None:
    """A random valid transit airport for dep -> land, or None if there is none.

    Valid: differs from both ends, is >= config.MIN_STOP_KM from each, and keeps
    d(dep,t) + d(t,land) <= config.DETOUR_MAX * d(dep,land).
    """
    return _pick_transit(_coords(airport), int(dep_id), int(land_id), rng)


def _flight_rows(tables: dict) -> pd.Series:
    """Number of fact rows per flight number (via the fact row's ticket)."""
    m = tables["fact"][["TicketID"]].merge(
        tables["ticket"][["TicketID", "FlightNo"]].drop_duplicates("TicketID"),
        on="TicketID", how="left")
    return m["FlightNo"].dropna().value_counts().sort_index()


def _hub_ids(airport: pd.DataFrame, airlines: list[str], rng: np.random.Generator) -> dict:
    """Hub AirportIDs per airline; codes absent from the dim are skipped.

    An airline with no usable hub gets one random airport as its hub.
    """
    code_to_id = {c: int(i) for c, i in zip(airport["airportCode"], airport["AirportID"])}
    all_ids = sorted(int(i) for i in airport["AirportID"])
    hubs = {}
    for code in sorted(airlines):
        ids = [code_to_id[c] for c in config.HUBS.get(code, []) if c in code_to_id]
        hubs[code] = ids or [int(rng.choice(all_ids))]
    return hubs


def build_routes(tables: dict, seed: int) -> pd.DataFrame:
    """One route per flight number used by the fact rows.

    Only airports with an airportCode are used (as hub, destination or transit),
    so reports never show an airport without a code. Destinations cycle through
    a seeded shuffle of those airports (so coverage is guaranteed), alternating
    hub->dest and dest->hub flights and rejecting destinations closer than
    300 km to the hub. Stopovers are then assigned flight by flight (seeded
    order) until config.STOP_SHARE of the fact rows is on a flight with a
    stopover; only routes with a direct distance >= config.MIN_STOPOVER_ROUTE_KM
    are eligible, and flights with no valid transit are skipped.
    """
    rng = np.random.default_rng(seed)
    airport = _coded(tables["airport"])
    coords = _coords(airport)
    rows_per_flight = _flight_rows(tables)
    flights = list(rows_per_flight.index)
    hubs = _hub_ids(airport, sorted({airline_of(f) for f in flights}), rng)

    order = [int(x) for x in rng.permutation(sorted(coords))]
    ptr = 0
    dep, land = {}, {}
    for i, f in enumerate(flights):
        hub_choices = hubs[airline_of(f)]
        hub = hub_choices[int(rng.integers(len(hub_choices)))]
        for _ in range(len(order)):
            dest = order[ptr % len(order)]
            ptr += 1
            if dest != hub and _dist(coords, hub, dest) >= MIN_ROUTE_KM:
                break
        else:
            raise ValueError(f"no destination >= {MIN_ROUTE_KM} km from hub {hub}")
        dep[f], land[f] = (hub, dest) if i % 2 == 0 else (dest, hub)

    target = math.ceil(config.STOP_SHARE * int(rows_per_flight.sum()))
    transit = {}
    covered = 0
    for j in rng.permutation(len(flights)):
        if covered >= target:
            break
        f = flights[int(j)]
        if _dist(coords, dep[f], land[f]) < config.MIN_STOPOVER_ROUTE_KM:
            continue
        t = _pick_transit(coords, dep[f], land[f], rng)
        if t is None:
            continue
        transit[f] = t
        covered += int(rows_per_flight[f])
    if covered < target:
        raise ValueError(f"only {covered} stopover rows, need {target}")

    out = pd.DataFrame({
        "FlightNo": flights,
        "DepAirportID": [dep[f] for f in flights],
        "LandAirportID": [land[f] for f in flights],
        "TransitAirportID": [transit.get(f) for f in flights],
    }, columns=_COLUMNS)
    for c in _COLUMNS[1:]:
        out[c] = out[c].astype("Int64")
    return out
