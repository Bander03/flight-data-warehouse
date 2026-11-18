# preprocessing

Python package `fdw` (in `src/`) that fixes the fact table and validates it against the rules in guide #2. Owner: Yohannes.

Python 3.10 to 3.12 (tested on 3.10.5 with the versions pinned in `requirements.txt`). Run from the repo root (not from this folder):

```
pip install -r preprocessing/requirements.txt
PYTHONPATH=preprocessing/src python -m fdw.cli        # Git Bash; in cmd.exe: set PYTHONPATH=preprocessing/src first
pytest preprocessing/tests -v
```

`python -m fdw.cli` takes optional `--raw-dir`, `--out-dir` and `--seed` (default seed `20261112`; the output is deterministic).
It prints one line per rule and ends with `17/17 rules passed`. It exits with code 1 and `VALIDATION FAILED` if a rule fails.

## What the pipeline does

`fdw.pipeline.run` applies these steps in order (each takes the table dict and returns a new one; raw files are never modified):

| Step | Module | Effect |
|---|---|---|
| load | `load.py` | Reads the raw Excel files, caches them as CSV in `data/raw` (fast on later runs) |
| supplement | `airlines.py` | Adds 240 flagged tickets (`IsSupplemented = 1`) for airlines 3U, SC, ZH, 9C so 11 airlines appear |
| routes | `routes.py` | One route per flight number between airports that have an `airportCode`; stopovers on at least 15% of the fact rows, only on routes >= 900 km direct (detour <= 1.25x, transit >= 150 km from both ends) |
| dates | `dates.py` | Spreads ticket groups over Jan to Aug 2021, with some in the spring-festival window |
| attributes | `assign.py` | Plane, cabin (Y 70 / C 22 / F 8; F and C only on planes with >= 100 seats), mileage (haversine km), price (full fare x `Rate`, rounded to 10; full fare = class anchor x (km / 1178) ^ 0.25, no row clipped), price range |
| passengers | `passengers.py` | Remaps the 9 fact `PassengerID`s missing from the passenger dimension to unused existing passengers |
| validate | `validate.py` | The 17 rules, before (on the raw tables, for the profile) and after (must all pass) |

The decisions behind each step are in [../docs/DATA_FINDINGS.md](../docs/DATA_FINDINGS.md).

## Output (`data/processed`, not in git)

`fact_flight_segment.csv`, `dim_airline.csv`, `dim_airport.csv`, `dim_date.csv`, `dim_passenger.csv`, `dim_plane.csv`,
`dim_price_range.csv`, `dim_seat.csv`, `dim_ticket.csv` (includes `IsSupplemented`), and `profile_before_after.md` (rule results
before and after, counts, sample rows, remapped passengers, clipped-price rows per cabin class). CSVs are UTF-8 with BOM and LF line endings;
the transit key is empty when a row has no stopover.

## Tests

`tests/test_*.py`, one file per module, plus `test_warehouse.py`, which builds the SQL Server warehouse in `sql/` and checks it
against the CSVs. Tests on the real data need the raw data folder at the repo root.

The warehouse tests drop and rebuild the database `FlightDW`, so they are **opt-in**: skipped unless `FDW_WAREHOUSE_TESTS=1`,
and also skipped when `sqlcmd` or the instance `localhost\SQLEXPRESS` is unavailable or `data/processed` lacks one of the nine
CSVs. Run the pipeline first, then, in cmd.exe (two separate lines; `set X=1 && ...` would put a trailing space in the value):

```
set FDW_WAREHOUSE_TESTS=1
pytest preprocessing/tests/test_warehouse.py -v
```

In Git Bash: `FDW_WAREHOUSE_TESTS=1 pytest preprocessing/tests/test_warehouse.py -v`.
