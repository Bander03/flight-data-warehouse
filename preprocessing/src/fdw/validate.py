"""Guide #2 rule validator.

Pure functions over the ``tables`` dict (keys: fact, ticket, passenger, airport,
airline, plane, seat, price_range, date) using the source column names.
"""
from dataclasses import dataclass

import pandas as pd

from . import config
from .airlines import airline_of

DEP, TRA, LAN = "Departure_ariportID", "Transit_ariportID", "Landing_ariportID"

# fact column -> (dimension table key, dimension key column, nulls allowed)
# Blank PlaneID/CabinID are reported by their own rules; null Transit means "no stopover".
FOREIGN_KEYS = {
    "PriceRangeID": ("price_range", "PriceRangeID", False),
    DEP: ("airport", "AirportID", False),
    TRA: ("airport", "AirportID", True),
    LAN: ("airport", "AirportID", False),
    "DepartureDateID": ("date", "DateRangeID", False),
    "ArrivalDateID": ("date", "DateRangeID", False),
    "PassengerID": ("passenger", "PassengerID", False),
    "TicketID": ("ticket", "TicketID", False),
    "PlaneID": ("plane", "PlaneID", True),
    "CabinID": ("seat", "CabinID", True),
}


@dataclass
class RuleResult:
    name: str
    passed: bool
    detail: str


class ValidationError(Exception):
    """Raised by ``assert_valid``; the message lists every failed rule."""


def _blank(s: pd.Series) -> pd.Series:
    """True where a value is missing or an empty / whitespace-only string."""
    out = s.isna()
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        out = out | s.astype("string").str.strip().eq("").fillna(False)
    return out.astype(bool)


def _at_least(name: str, label: str, n: int, minimum: int) -> RuleResult:
    return RuleResult(name, n >= minimum, f"{n} distinct {label} (need >= {minimum})")


def _not_blank(name: str, col: str, fact: pd.DataFrame) -> RuleResult:
    n = int(_blank(fact[col]).sum())
    return RuleResult(name, n == 0, f"{n} blank {col} values")


def _not_constant(name: str, col: str, fact: pd.DataFrame) -> RuleResult:
    n = int(fact[col].dropna().nunique())
    return RuleResult(name, n > 1, f"{n} distinct {col} values (need > 1)")


def _dates(tables: dict, id_col: str) -> pd.Series:
    """Fact date ID column -> Timestamps through the date dimension (NaT if unknown)."""
    dim = tables["date"]
    lookup = pd.Series(pd.to_datetime(dim["Date"]).to_numpy(),
                       index=dim["DateRangeID"].astype("int64"))
    ids = tables["fact"][id_col]
    out = pd.Series(pd.NaT, index=ids.index, dtype="datetime64[ns]")
    ok = ids.notna() & ids.isin(lookup.index)
    out[ok] = lookup.loc[ids[ok].astype("int64")].to_numpy()
    return out


def _airlines(tables: dict) -> pd.Series:
    """Airline code per fact row via its ticket's flight number (NA if no ticket)."""
    ticket = tables["ticket"]
    flight = ticket["FlightNo"]
    # null / blank flight numbers have no airline; never turn them into bogus codes
    usable = ~_blank(flight) & ticket["TicketID"].notna()
    code = pd.Series([airline_of(str(no).strip()) for no in flight[usable]],
                     index=ticket.loc[usable, "TicketID"].astype("int64").to_numpy())
    code = code[~code.index.duplicated()]
    ids = tables["fact"]["TicketID"]
    out = pd.Series(pd.NA, index=ids.index, dtype=object)
    ok = ids.notna() & ids.isin(code.index)
    out[ok] = code.loc[ids[ok].astype("int64")].to_numpy()
    return out


def _foreign_keys(tables: dict) -> RuleResult:
    fact = tables["fact"]
    problems = []
    for col, (dim, key, nullable) in FOREIGN_KEYS.items():
        values = fact[col]
        nulls = int(values.isna().sum())
        if nulls and not nullable:
            problems.append(f"{col}: {nulls} null")
        present = values.dropna()
        missing = int((~present.isin(tables[dim][key].dropna())).sum())
        if missing:
            problems.append(f"{col}: {missing} not in {dim}.{key}")
    return RuleResult("foreign_keys_exist", not problems,
                      "; ".join(problems) if problems else "all foreign keys resolve")


def _price_in_range(tables: dict) -> RuleResult:
    fact = tables["fact"]
    pr = tables["price_range"].drop_duplicates("PriceRangeID").set_index("PriceRangeID")
    known = fact["PriceRangeID"].isin(pr.index)   # unknown ranges are a foreign-key problem
    lo = fact.loc[known, "PriceRangeID"].map(pr["MinNum"])
    hi = fact.loc[known, "PriceRangeID"].map(pr["MaxNum"])
    price = fact.loc[known, "Price"]
    # nullable Int64 comparisons give NA for a null Price: fillna(False) makes it fail
    ok = ((price >= lo) & (price <= hi)).fillna(False).astype(bool)
    n = int((~ok).sum())
    return RuleResult("price_in_range", n == 0, f"{n} rows with Price outside their price range")


def validate_fact(tables: dict[str, pd.DataFrame], expected_rows: int = 600) -> list[RuleResult]:
    """Check the 17 guide #2 rules and invariants; return one result per rule."""
    fact = tables["fact"]
    dep, tra, lan = fact[DEP], fact[TRA], fact[LAN]
    results = [
        _at_least("departure_airports_ge_20", "departure airports",
                  dep.nunique(), config.MIN_DEP),
        _at_least("landing_airports_ge_20", "landing airports",
                  lan.nunique(), config.MIN_LAND),
    ]

    n = int((dep == lan).sum())
    results.append(RuleResult("departure_ne_landing", n == 0,
                              f"{n} rows with departure == landing"))

    n = int(((tra == dep) | (tra == lan)).sum())    # null transit compares False
    results.append(RuleResult("transit_ne_ends", n == 0,
                              f"{n} rows with transit equal to departure or landing"))

    stops = int(tra.notna().sum())
    results.append(RuleResult("stopover_rows_ge_20", stops >= config.MIN_STOP_ROWS,
                              f"{stops} stopover rows (need >= {config.MIN_STOP_ROWS})"))
    results.append(_at_least("passengers_ge_50", "passengers",
                             fact["PassengerID"].nunique(), config.MIN_PASSENGERS))

    months = _dates(tables, "DepartureDateID").dropna().dt.to_period("M").nunique()
    results.append(_at_least("date_span_ge_6_months", "calendar months of departure dates",
                             months, config.MIN_MONTHS))
    results.append(_at_least("airlines_ge_10", "airlines",
                             _airlines(tables).dropna().nunique(), config.MIN_AIRLINES))

    results += [
        _not_blank("plane_not_blank", "PlaneID", fact),
        _not_constant("plane_not_constant", "PlaneID", fact),
        _not_blank("cabin_not_blank", "CabinID", fact),
        _not_constant("cabin_not_constant", "CabinID", fact),
        RuleResult("row_count_preserved", len(fact) == expected_rows,
                   f"{len(fact)} fact rows (expected {expected_rows})"),
    ]

    ian = fact["ian"]
    dups = int(ian.dropna().duplicated().sum())
    nulls = int(ian.isna().sum())
    results.append(RuleResult("ian_unique", dups == 0 and nulls == 0,
                              f"{dups} duplicated and {nulls} null ian values"))

    results.append(_foreign_keys(tables))
    results.append(_price_in_range(tables))

    arr, dpt = _dates(tables, "ArrivalDateID"), _dates(tables, "DepartureDateID")
    n = int((arr < dpt).sum())
    results.append(RuleResult("arrival_ge_departure", n == 0,
                              f"{n} rows with arrival date before departure date"))
    return results


def assert_valid(tables: dict[str, pd.DataFrame], expected_rows: int = 600) -> None:
    """Raise ``ValidationError`` listing every failed rule; return None when all pass."""
    failed = [r for r in validate_fact(tables, expected_rows) if not r.passed]
    if failed:
        lines = "\n".join(f"  - {r.name}: {r.detail}" for r in failed)
        raise ValidationError(f"{len(failed)} rule(s) failed:\n{lines}")
