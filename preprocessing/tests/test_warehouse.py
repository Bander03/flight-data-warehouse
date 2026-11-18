"""Opt-in tests: build the FlightDW warehouse from data/processed with the T-SQL scripts in sql/.

These tests DROP and recreate the database FlightDW (and only that database), so they run only
when the environment variable FDW_WAREHOUSE_TESTS=1 is set:

    cmd.exe:   set FDW_WAREHOUSE_TESTS=1
               pytest preprocessing/tests/test_warehouse.py -v
    Git Bash:  FDW_WAREHOUSE_TESTS=1 pytest preprocessing/tests/test_warehouse.py -v

They are also skipped when sqlcmd is not on PATH, the instance is unreachable, or data/processed
does not hold all nine CSVs (run `python -m fdw.cli` first; there is no fallback to older copies).
The CSVs are copied from data/processed to a folder the SQL Server service account can read
(default C:\\fdw_data, override with FDW_SQL_DATA_DIR); instance override: FDW_SQL_INSTANCE.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
SQL_DIR = REPO / "sql"
PROCESSED = REPO / "data" / "processed"
INSTANCE = os.environ.get("FDW_SQL_INSTANCE", r"localhost\SQLEXPRESS")
DATA_DIR = Path(os.environ.get("FDW_SQL_DATA_DIR", r"C:\fdw_data"))
SQLCMD = shutil.which("sqlcmd")
OPT_IN = os.environ.get("FDW_WAREHOUSE_TESTS", "").strip() == "1"

pytestmark = pytest.mark.skipif(
    not OPT_IN, reason="warehouse tests rebuild the FlightDW database; set FDW_WAREHOUSE_TESTS=1 to run them")

CSV_FILES = ["fact_flight_segment.csv", "dim_ticket.csv", "dim_passenger.csv",
             "dim_airport.csv", "dim_airline.csv", "dim_plane.csv", "dim_seat.csv",
             "dim_price_range.csv", "dim_date.csv"]
# warehouse table -> (csv file, extra rows the warehouse adds)
TABLE_CSV = {
    "dw.Fact_FlightSegment": ("fact_flight_segment.csv", 0),
    "dw.DimTicket": ("dim_ticket.csv", 0),
    "dw.DimPassenger": ("dim_passenger.csv", 0),
    "dw.DimAirport": ("dim_airport.csv", 1),   # + the 'No stopover' row
    "dw.DimAirline": ("dim_airline.csv", 0),
    "dw.DimPlane": ("dim_plane.csv", 0),
    "dw.DimSeat": ("dim_seat.csv", 0),
    "dw.DimPriceRange": ("dim_price_range.csv", 0),
    "dw.DimDate": ("dim_date.csv", 0),
}


def _sqlcmd(args, data_dir=None, timeout=900):
    """Run sqlcmd. sqlcmd rejects `-v DataDir=C:/path` (it chokes on the drive-letter colon) unless the
    value is quoted on the raw command line, so the command line is built as one string here."""
    cmd = subprocess.list2cmdline([SQLCMD, "-S", INSTANCE, "-E", "-b", "-f", "65001", *args])
    if data_dir is not None:
        cmd += f' -v DataDir="{data_dir}"'
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def _run_script(name):
    proc = _sqlcmd(["-i", str(SQL_DIR / name)], data_dir=DATA_DIR)
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    return proc.returncode, out


def _query(sql):
    """Run one query against FlightDW; return a list of rows (list of str columns)."""
    proc = _sqlcmd(["-d", "FlightDW", "-h", "-1", "-W", "-s", "|", "-Q",
                    "SET NOCOUNT ON; " + sql])
    text = proc.stdout.decode("utf-8", "replace").lstrip("\ufeff")
    assert proc.returncode == 0, text + proc.stderr.decode("utf-8", "replace")
    return [line.split("|") for line in text.splitlines() if line.strip()]


def _scalar(sql):
    return _query(sql)[0][0]


def _csv_rows(name):
    with open(DATA_DIR / name, "rb") as fh:
        return sum(1 for _ in fh) - 1   # no embedded newlines (checked in the task report)


@pytest.fixture(scope="module")
def data_dir():
    if SQLCMD is None:
        pytest.skip("sqlcmd not on PATH")
    try:
        probe = subprocess.run([SQLCMD, "-S", INSTANCE, "-E", "-l", "5", "-Q", "SELECT 1"],
                               capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        pytest.skip(f"SQL Server instance {INSTANCE} not reachable (timeout)")
    if probe.returncode != 0:
        pytest.skip(f"SQL Server instance {INSTANCE} not reachable")
    missing = [f for f in CSV_FILES if not (PROCESSED / f).is_file()]
    if missing:
        pytest.skip(f"data/processed is missing {missing} (run python -m fdw.cli first)")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in CSV_FILES:
        shutil.copyfile(PROCESSED / f, DATA_DIR / f)
    return DATA_DIR


@pytest.fixture(scope="module")
def built(data_dir):
    """Run 01-04 once for the module."""
    for name in ["01_create_db.sql", "02_stg_tables.sql", "03_dw_tables.sql", "04_load.sql"]:
        code, out = _run_script(name)
        assert code == 0, f"{name} failed:\n{out}"
    return True


def test_scripts_run_and_checks_pass(built):
    code, out = _run_script("99_checks.sql")
    assert code == 0, f"99_checks.sql failed:\n{out}"


def test_load_is_idempotent(built):
    tables = list(TABLE_CSV)
    count_sql = " UNION ALL ".join(
        f"SELECT '{t}', COUNT(*) FROM {t}" for t in tables)
    before = dict(_query(count_sql))
    for _ in range(2):
        code, out = _run_script("04_load.sql")
        assert code == 0, f"04_load.sql failed:\n{out}"
    after = dict(_query(count_sql))
    assert after == before
    assert after["dw.Fact_FlightSegment"] == "600"
    code, out = _run_script("99_checks.sql")
    assert code == 0, f"99_checks.sql failed after reload:\n{out}"


def test_row_counts_match_csv(built):
    for table, (csv, extra) in TABLE_CSV.items():
        assert int(_scalar(f"SELECT COUNT(*) FROM {table}")) == _csv_rows(csv) + extra, table


def test_chinese_roundtrip(built):
    rows = _query("SELECT AirlineName FROM dw.DimAirline WHERE AirlineCode = 'CA'")
    assert rows == [["中国国际航空"]]


def test_warehouse_matches_csv_aggregates(built):
    """Measures and key counts in dw equal the same figures computed by pandas on the CSV."""
    fact = pd.read_csv(PROCESSED / "fact_flight_segment.csv", encoding="utf-8-sig")
    ticket = pd.read_csv(PROCESSED / "dim_ticket.csv", encoding="utf-8-sig",
                         usecols=["TicketID", "FlightNo"])
    row = _query("SELECT SUM(CAST(Price AS BIGINT)), SUM(CAST(Mileage AS BIGINT)), "
                 "SUM(CASE WHEN HasStopover = 1 THEN 1 ELSE 0 END), "
                 "COUNT(DISTINCT DepartureAirportKey), COUNT(DISTINCT LandingAirportKey) "
                 "FROM dw.Fact_FlightSegment")[0]
    assert [int(v) for v in row] == [
        int(fact["Price"].sum()), int(fact["mileage"].sum()),
        int(fact["Transit_ariportID"].notna().sum()),
        int(fact["Departure_ariportID"].nunique()), int(fact["Landing_ariportID"].nunique())]

    per_airline = {code: int(n) for code, n in _query(
        "SELECT a.AirlineCode, COUNT(*) FROM dw.Fact_FlightSegment f "
        "JOIN dw.DimTicket t ON t.TicketKey = f.TicketKey "
        "JOIN dw.DimAirline a ON a.AirlineKey = t.AirlineKey GROUP BY a.AirlineCode")}
    flight = fact["TicketID"].map(ticket.drop_duplicates("TicketID").set_index("TicketID")["FlightNo"])
    expected = {k: int(v) for k, v in flight.str[:2].value_counts().items()}
    assert per_airline == expected
    assert len(per_airline) == 11


def test_new_dimension_attributes(built):
    rows = _query("SELECT MonthName, YearMonth, QuarterName, DayName FROM dw.DimDate "
                  "WHERE FullDate = '2021-02-11'")
    assert rows == [["February", "2021-02", "2021 Q1", "Thursday"]]
    bands = _query("SELECT AgeBand, MIN(AgeBandOrder), MAX(AgeBandOrder) FROM dw.DimPassenger "
                   "GROUP BY AgeBand ORDER BY MIN(AgeBandOrder)")
    assert all(lo == hi for _, lo, hi in bands)
    assert bands[-1][0] == "Unknown"
    assert [b for b, _, _ in bands][:-1] == ["<25", "25-34", "35-44", "45-54", "55-64", "65+"]
