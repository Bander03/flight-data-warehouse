"""Airline helpers and supplementation of extra airlines."""
import numpy as np
import pandas as pd

from fdw import config

NEW_AIRLINES = ["3U", "SC", "ZH", "9C"]
FLIGHT_NUMBERS = [9001, 9002, 9003]
TICKETS_PER_FLIGHT = 20
FIRST_DAY = pd.Timestamp("2021-01-04")
LAST_DAY = pd.Timestamp("2021-08-22")
FLIGHT_DURATION = pd.Timedelta(hours=2, minutes=30)
MAX_DELAY = 60
_FMT = "%Y-%m-%d %H:%M:%S"


def airline_of(flight_no: str) -> str:
    """Airline code of a flight number: its first two characters (e.g. MU5138 -> MU)."""
    return flight_no[:2]


def _new_tickets(first_id: int, rng: np.random.Generator) -> pd.DataFrame:
    """Dated supplemental tickets: 3 flight numbers x 20 dates for every new airline."""
    span_days = (LAST_DAY - FIRST_DAY).days
    rows = []
    tid = first_id
    for code in NEW_AIRLINES:
        for num in FLIGHT_NUMBERS:
            # 20 distinct days spread over the whole period, incl. both endpoints
            days = np.unique(np.round(np.linspace(0, span_days, TICKETS_PER_FLIGHT)).astype(int))
            hours = rng.integers(6, 21, size=len(days))
            minutes = rng.choice([0, 15, 30, 45], size=len(days))
            delays = rng.integers(0, MAX_DELAY + 1, size=len(days))
            for d, h, m, delay in zip(days, hours, minutes, delays):
                dep = FIRST_DAY + pd.Timedelta(days=int(d), hours=int(h), minutes=int(m))
                rows.append({
                    "TicketID": tid,
                    "departureTime": dep.strftime(_FMT),
                    "delayTime": int(delay),
                    "arrivalTime": (dep + FLIGHT_DURATION).strftime(_FMT),
                    "FlightNo": f"{code}{num}",
                    "IsSupplemented": 1,
                })
                tid += 1
    return pd.DataFrame(rows)


def supplement(tables: dict, seed: int) -> dict:
    """Add the supplemental airlines' tickets and re-point whole fact ticket groups.

    Returns a new dict; ``ticket`` gets an ``IsSupplemented`` column (0 for the
    original rows, 1 for the new ones) and ``fact.TicketID`` of randomly chosen
    ticket groups (all rows sharing a TicketID move together) is re-pointed to
    supplemental tickets until the fact rows cover ``config.TARGET_AIRLINES``
    distinct airlines. All other fact columns and rows are unchanged.
    """
    rng = np.random.default_rng(seed)
    ticket = tables["ticket"].copy()
    fact = tables["fact"].copy()
    ticket["IsSupplemented"] = 0

    new = _new_tickets(int(ticket["TicketID"].max()) + 1, rng)
    new["TicketID"] = new["TicketID"].astype(ticket["TicketID"].dtype)
    new["delayTime"] = new["delayTime"].astype(ticket["delayTime"].dtype)
    new_by_airline = {c: new.loc[new["FlightNo"].map(airline_of) == c, "TicketID"].to_numpy()
                      for c in NEW_AIRLINES}

    # airline of every ticket group used by the fact rows
    airline_by_ticket = ticket.set_index("TicketID")["FlightNo"].map(airline_of)
    groups = fact["TicketID"].dropna().unique()
    group_airline = {g: airline_by_ticket.loc[g] for g in groups}
    remaining = pd.Series(list(group_airline.values())).value_counts().to_dict()

    missing = [c for c in NEW_AIRLINES if c not in remaining]
    n_needed = config.TARGET_AIRLINES - len(remaining)
    if n_needed > len(missing):
        raise ValueError("not enough supplemental airlines to reach the target")

    mapping = {}
    order = [groups[i] for i in rng.permutation(len(groups))]
    for code in missing[:max(n_needed, 0)]:
        for g in order:
            old = group_airline[g]
            # never move the last group of an original airline (that would lose it)
            if g in mapping or remaining[old] <= 1:
                continue
            mapping[g] = rng.choice(new_by_airline[code])
            remaining[old] -= 1
            break
        else:
            raise ValueError("no movable ticket group left")

    fact["TicketID"] = fact["TicketID"].map(lambda t: mapping.get(t, t)).astype(fact["TicketID"].dtype)
    out = dict(tables)
    out["ticket"] = pd.concat([ticket, new], ignore_index=True)
    out["fact"] = fact
    return out
