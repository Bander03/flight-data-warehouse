"""Excel -> cached CSV -> dict of DataFrames."""
from pathlib import Path

import pandas as pd

from . import config

# table key -> dimension file stem (fact lives directly in raw_dir)
SOURCES = {
    "fact": None,  # config.FACT_FILE in raw_dir
    "ticket": "DW_Dim_ticket",
    "passenger": "DW_Dim_Passenger",
    "airport": "DW_Dim_Airport",
    "airline": "DW_Dim_Airlines",
    "plane": "DW_Dim_Plane",
    "seat": "DW_Dim_Seat",
    "price_range": "DW_Dim_PriceRange",
    "date": "DW_Dim_DateRange",
}

RENAMES = {"FFP_TIER （会员卡级别）": "FFP_TIER"}

# Columns the pipeline needs in every source table (names as the cached CSV has them, after RENAMES).
REQUIRED_COLUMNS = {
    "fact": ["PriceRangeID", "Departure_ariportID", "Transit_ariportID", "Landing_ariportID", "DepartureDateID",
             "ArrivalDateID", "PassengerID", "TicketID", "PlaneID", "CabinID", "mileage", "Price", "Rate", "ian"],
    "ticket": ["TicketID", "departureTime", "delayTime", "arrivalTime", "FlightNo"],
    "passenger": ["PassengerID", "PassengerGender", "PassengerAge", "PassengerWorkplace", "FFP_TIER", "FLIGHT_COUNT",
                  "PassengerName"],
    "airport": ["AirportID", "ariport", "airportCode", "Ariport_X", "Ariport_y", "city"],
    "airline": ["AirlinesID", "airlines", "airlinesCode", "planeNumber"],
    "plane": ["PlaneID", "planeModel", "SeatNum"],
    "seat": ["CabinID", "CabinClass", "SeatRow", "SeatLine"],
    "price_range": ["PriceRangeID", "MinNum", "MaxNum", "PriceGrade"],
    "date": ["DateRangeID", "Date", "Year", "Month"],
}


class SourceDataError(Exception):
    """The raw data are missing, empty or lack a column the pipeline needs (clear message, no traceback needed)."""


# Only truly empty cells are NaN; strings such as "NA" must survive.
_NA = dict(keep_default_na=False, na_values=[""])


def _xlsx_path(key: str, raw_dir: Path) -> Path:
    if key == "fact":
        return raw_dir / config.FACT_FILE
    return raw_dir / config.DIM_SUBDIR / f"{SOURCES[key]}.xlsx"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAMES)
    for col in df.columns:
        if col.endswith("ID") or col == "ian":
            df[col] = df[col].astype("Int64")
    return df


def _read_one(key: str, raw_dir: Path, cache_dir: Path) -> pd.DataFrame:
    csv_path = cache_dir / f"{key}.csv"
    xlsx = _xlsx_path(key, raw_dir)
    # the cache is rebuilt when the Excel file is newer than its CSV copy (a stale cache would silently hide a changed source)
    if csv_path.exists() and xlsx.exists() and xlsx.stat().st_mtime > csv_path.stat().st_mtime:
        csv_path.unlink()
    if not csv_path.exists():
        if not xlsx.exists():
            raise SourceDataError(
                f"source file for table '{key}' not found: {xlsx}. The raw data folder "
                f"'{config.RAW_DIR.name}' must be in the repository root (see README step 2).")
        df = pd.read_excel(xlsx, **_NA)
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.rename(columns=RENAMES).to_csv(csv_path, index=False, encoding="utf-8-sig")
    # always parse from the CSV so first run and cached runs return identical frames
    df = _normalize(pd.read_csv(csv_path, encoding="utf-8-sig", **_NA))
    missing = [c for c in REQUIRED_COLUMNS[key] if c not in df.columns]
    if missing:
        raise SourceDataError(f"table '{key}' ({csv_path.name}) lacks the column(s) {missing}; found {list(df.columns)}")
    if df.empty:
        raise SourceDataError(f"table '{key}' ({csv_path.name}) has a header but no rows")
    return df


def load_tables(raw_dir: Path = config.RAW_DIR,
                cache_dir: Path = config.CACHE_DIR) -> dict[str, pd.DataFrame]:
    raw_dir, cache_dir = Path(raw_dir), Path(cache_dir)
    return {key: _read_one(key, raw_dir, cache_dir) for key in SOURCES}
