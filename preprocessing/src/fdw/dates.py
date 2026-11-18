"""Spread fact ticket groups over 2021 (Jan..Aug), keeping flight numbers."""
import numpy as np
import pandas as pd

TARGET_YEAR = 2021
MONTHS = list(range(1, 9))                       # Jan..Aug
HOLIDAY_START = pd.Timestamp("2021-02-11")
HOLIDAY_END = pd.Timestamp("2021-02-17")
MIN_HOLIDAY_GROUPS = 2
MIN_HOLIDAY_ROWS = 5


def _month_key(ts: pd.Series) -> np.ndarray:
    return (ts.dt.year * 12 + ts.dt.month - 1).to_numpy()


def spread_dates(tables: dict, seed: int) -> dict:
    """Move every fact ticket group to another ticket of the same ``FlightNo``.

    Target months are assigned round-robin over Jan..Aug 2021 in seeded group
    order (falling back to the nearest month that has a ticket); a few groups
    are reserved for the spring-festival window (2021-02-11..2021-02-17).
    ``fact.TicketID``, ``DepartureDateID`` and ``ArrivalDateID`` are recomputed
    for ALL rows from the final ticket. Returns a new dict; inputs are untouched.
    """
    rng = np.random.default_rng(seed)
    fact = tables["fact"].copy()
    ticket = tables["ticket"].reset_index(drop=True)
    date_id = tables["date"].set_index("Date")["DateRangeID"]

    dep = pd.to_datetime(ticket["departureTime"])
    mkey = _month_key(dep)
    in_window = ((dep >= HOLIDAY_START) & (dep < HOLIDAY_END + pd.Timedelta(days=1))).to_numpy()
    tid = ticket["TicketID"].to_numpy()
    flight = ticket["FlightNo"].to_numpy()
    flight_of = dict(zip(tid, flight))

    # per flight number: positions of its tickets
    by_flight = {f: np.asarray(ix) for f, ix in ticket.groupby("FlightNo").indices.items()}

    groups = fact["TicketID"].dropna().unique()
    order = [groups[i] for i in rng.permutation(len(groups))]
    rows_of = fact["TicketID"].value_counts().to_dict()

    # reserve groups for the holiday window (only flights that have a window ticket)
    reserved: list = []
    rows_reserved = 0
    for g in order:
        if len(reserved) >= MIN_HOLIDAY_GROUPS and rows_reserved >= MIN_HOLIDAY_ROWS:
            break
        pos = by_flight[flight_of[g]]
        if in_window[pos].any():
            reserved.append(g)
            rows_reserved += rows_of[g]
    reserved_set = set(reserved)

    mapping: dict = {}
    used: set = set()

    def pick(g, window_only, target_key):
        """Ticket for group ``g``: same flight, not its own, not yet taken (if possible)."""
        pos = by_flight[flight_of[g]]
        if window_only:
            pos = pos[in_window[pos]]
        for avoid in ((True, True), (True, False), (False, False)):   # (own, taken)
            ok = np.array([not (avoid[0] and tid[p] == g) and not (avoid[1] and tid[p] in used)
                           for p in pos], dtype=bool)
            if ok.any():
                pos = pos[ok]
                break
        if len(pos) == 0:
            return None
        if target_key is not None:                 # nearest month that has a ticket
            dist = np.abs(mkey[pos] - target_key)
            pos = pos[dist == dist.min()]
        return tid[rng.choice(pos)]

    # holiday groups first so their tickets are not taken by others
    for g in reserved:
        mapping[g] = pick(g, True, None)
        used.add(mapping[g])

    rest = [g for g in order if g not in reserved_set]
    for i, g in enumerate(rest):
        month = MONTHS[i % len(MONTHS)]
        target = pick(g, False, TARGET_YEAR * 12 + month - 1)
        if target is None:                      # flight has no tickets at all: keep
            target = g
        mapping[g] = target
        used.add(target)

    tid_to_pos = {t: i for i, t in enumerate(tid)}
    new_tid = fact["TicketID"].map(mapping)
    pos = new_tid.map(tid_to_pos)
    dep_str = ticket["departureTime"].str[:10].to_numpy()
    arr_str = ticket["arrivalTime"].str[:10].to_numpy()
    fact["TicketID"] = new_tid.astype(fact["TicketID"].dtype)
    fact["DepartureDateID"] = pd.Series(dep_str[pos.to_numpy()], index=fact.index).map(date_id).astype(
        fact["DepartureDateID"].dtype)
    fact["ArrivalDateID"] = pd.Series(arr_str[pos.to_numpy()], index=fact.index).map(date_id).astype(
        fact["ArrivalDateID"].dtype)

    out = dict(tables)
    out["fact"] = fact
    return out
