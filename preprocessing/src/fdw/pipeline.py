"""End-to-end preprocessing: raw tables -> cleaned tables -> CSV files + profile."""
from pathlib import Path

import pandas as pd

from . import config
from .airlines import supplement
from .assign import apply_routes_and_attributes
from .dates import spread_dates
from .load import load_tables
from .passengers import repair_passenger_keys
from .routes import build_routes
from .validate import RuleResult, _airlines, _dates, assert_valid, validate_fact

# table key -> output file
OUTPUT_FILES = {
    "fact": "fact_flight_segment.csv",
    "ticket": "dim_ticket.csv",
    "passenger": "dim_passenger.csv",
    "airport": "dim_airport.csv",
    "airline": "dim_airline.csv",
    "plane": "dim_plane.csv",
    "seat": "dim_seat.csv",
    "price_range": "dim_price_range.csv",
    "date": "dim_date.csv",
}
PROFILE_FILE = "profile_before_after.md"

# float columns that only hold whole numbers: written without ".0"
INTEGRAL_FLOAT_COLUMNS = ("PassengerAge",)

FACT_COLUMNS = ["PriceRangeID", "Departure_ariportID", "Transit_ariportID",
                "Landing_ariportID", "DepartureDateID", "ArrivalDateID", "PassengerID",
                "TicketID", "PlaneID", "CabinID", "mileage", "Price", "Rate", "ian"]


def run(raw_dir: Path = config.RAW_DIR, out_dir: Path = config.OUT_DIR,
        seed: int = config.SEED, cache_dir: Path = config.CACHE_DIR) -> list[RuleResult]:
    """Run the whole pipeline, write the CSV files and the profile, return the 17 results.

    Raises ``ValidationError`` (and writes nothing) when a rule fails on the final tables.
    """
    raw = load_tables(Path(raw_dir), Path(cache_dir))
    before = validate_fact(raw)

    tables = supplement(raw, seed)
    routes = build_routes(tables, seed)
    tables = spread_dates(tables, seed)
    tables = apply_routes_and_attributes(tables, routes, seed)
    unrepaired = tables
    tables = repair_passenger_keys(tables, seed)
    assert_valid(tables)
    after = validate_fact(tables)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, name in OUTPUT_FILES.items():
        _write_csv(_ordered(key, tables[key]), out_dir / name)
    profile = _profile(raw, tables, unrepaired, before, after, seed)
    with open(out_dir / PROFILE_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(profile)
    return after


# --- CSV output ---------------------------------------------------------------

def _ordered(key: str, df: pd.DataFrame) -> pd.DataFrame:
    return df[FACT_COLUMNS] if key == "fact" else df


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    """UTF-8 with BOM, LF line ends, integers without '.0', nulls as empty cells."""
    df = df.copy()
    for col in INTEGRAL_FLOAT_COLUMNS:
        if col in df.columns:
            vals = df[col].dropna()
            if (vals == vals.round()).all():
                df[col] = df[col].round().astype("Int64")
    if "Rate" in df.columns:                     # source stores 0.719999999999999 for 0.72
        rate = df["Rate"].astype(float)
        if (rate - rate.round(2)).abs().max() < 1e-9:
            df["Rate"] = rate.round(2)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        df.to_csv(f, index=False, na_rep="", lineterminator="\n")


# --- profile -------------------------------------------------------------------

def _counts(tables: dict) -> dict[str, int]:
    fact = tables["fact"]
    months = _dates(tables, "DepartureDateID").dropna().dt.to_period("M").nunique()
    ticket = tables["ticket"]
    supplemented = int(ticket["IsSupplemented"].sum()) if "IsSupplemented" in ticket else 0
    return {
        "Fact rows": len(fact),
        "Distinct departure airports": int(fact["Departure_ariportID"].nunique()),
        "Distinct landing airports": int(fact["Landing_ariportID"].nunique()),
        "Distinct transit airports": int(fact["Transit_ariportID"].nunique()),
        "Rows with a stopover": int(fact["Transit_ariportID"].notna().sum()),
        "Distinct airlines (via ticket flight number)": int(_airlines(tables).dropna().nunique()),
        "Distinct planes": int(fact["PlaneID"].nunique()),
        "Distinct cabins": int(fact["CabinID"].nunique()),
        "Distinct passengers": int(fact["PassengerID"].nunique()),
        "Calendar months of departure dates": int(months),
        "Distinct departure dates": int(fact["DepartureDateID"].nunique()),
        "Supplemental tickets": supplemented,
    }


def _md_cell(value) -> str:
    return "" if pd.isna(value) else str(value).replace("|", "/")


def _sample_rows(tables: dict) -> pd.DataFrame:
    """Five stopover rows and five direct rows (first ones in fact order)."""
    fact = tables["fact"]
    stop = fact[fact["Transit_ariportID"].notna()].head(5)
    direct = fact[fact["Transit_ariportID"].isna()].head(5)
    return pd.concat([stop, direct]).sort_index()


def _profile(raw: dict, final: dict, unrepaired: dict,
             before: list[RuleResult], after: list[RuleResult], seed: int) -> str:
    out = ["# Preprocessing profile: before vs after", ""]
    out += ["Generated by `python -m fdw.cli` (deterministic, seed "
            f"{seed}). \"Before\" is the raw fact with its raw dimensions, "
            "\"after\" is the cleaned output written next to this file.", ""]

    out += ["## Guide #2 rules: before vs after", "",
            "| Rule | Before | After | Detail (before) | Detail (after) |",
            "|---|---|---|---|---|"]
    for b, a in zip(before, after):
        out.append(f"| {b.name} | {'PASS' if b.passed else 'FAIL'} | "
                   f"{'PASS' if a.passed else 'FAIL'} | {_md_cell(b.detail)} | "
                   f"{_md_cell(a.detail)} |")
    out.append(f"\nRules passed: before {sum(r.passed for r in before)}/{len(before)}, "
               f"after {sum(r.passed for r in after)}/{len(after)}.\n")

    cb, ca = _counts(raw), _counts(final)
    out += ["## Counts", "", "| Measure | Before | After |", "|---|---|---|"]
    out += [f"| {k} | {cb[k]} | {ca[k]} |" for k in ca]
    out.append("")

    airport = final["airport"].drop_duplicates("AirportID").set_index("AirportID")["airportCode"]
    dates = final["date"].drop_duplicates("DateRangeID").set_index("DateRangeID")["Date"]
    tk = final["ticket"].drop_duplicates("TicketID").set_index("TicketID")["FlightNo"]

    def code(v):
        if pd.isna(v):
            return ""
        c = airport.get(int(v))                  # some source airports have no code
        return f"{int(v)} ({'no code' if pd.isna(c) else c})"

    out += ["## Sample fact rows", "",
            "Airport columns show `AirportID (airportCode)`; a blank transit means no stopover.",
            "",
            "| ian | FlightNo | Departure | Transit | Landing | DepartureDate | ArrivalDate "
            "| PassengerID | TicketID | PlaneID | CabinID | mileage | Price | Rate "
            "| PriceRangeID |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in _sample_rows(final).iterrows():
        out.append("| " + " | ".join(_md_cell(v) for v in [
            r["ian"], tk.get(r["TicketID"], ""), code(r["Departure_ariportID"]),
            code(r["Transit_ariportID"]), code(r["Landing_ariportID"]),
            dates.get(r["DepartureDateID"], ""), dates.get(r["ArrivalDateID"], ""),
            r["PassengerID"], r["TicketID"], r["PlaneID"], r["CabinID"], r["mileage"],
            r["Price"], round(float(r["Rate"]), 2), r["PriceRangeID"]]) + " |")
    out.append("")

    old, new = unrepaired["fact"], final["fact"]
    changed = old["PassengerID"].ne(new["PassengerID"])
    out += ["## Remapped passenger keys (ruling R4)", "",
            f"{int(changed.sum())} fact rows carried a PassengerID that is missing from "
            "the passenger dimension (source defect). Only those rows were remapped to "
            "existing, previously unused passengers; no dimension rows were added.", "",
            "| ian | Old PassengerID | New PassengerID |", "|---|---|---|"]
    out += [f"| {new.at[i, 'ian']} | {old.at[i, 'PassengerID']} | {new.at[i, 'PassengerID']} |"
            for i in new.index[changed]]
    out.append("")

    top = int(final["price_range"]["MaxNum"].max()) - 10
    cls = new["CabinID"].map(final["seat"].drop_duplicates("CabinID")
                             .set_index("CabinID")["CabinClass"])
    out += ["## Price clipping", "",
            "Price = round(full fare x Rate, -1). A price above the top band would be clipped "
            f"to {top} (the top band's MaxNum - 10); rows at that cap per cabin class:", "",
            "| Class | Clipped rows | Rows | Share |", "|---|---|---|---|"]
    for k in ["F", "C", "Y"]:
        price = new["Price"][cls == k]
        n = int((price >= top).sum())
        out.append(f"| {k} | {n} | {len(price)} | {n / len(price) if len(price) else 0:.1%} |")
    n_all = int((new["Price"] >= top).sum())
    out += [f"| All | {n_all} | {len(new)} | {n_all / len(new):.1%} |", ""]
    return "\n".join(out)
