# sql

Warehouse DDL and load/ETL scripts. Owner: Bander.

Relational warehouse `FlightDW` on SQL Server (tested on 2022 Express, instance `localhost\SQLEXPRESS`, Windows
authentication). `BULK INSERT ... FORMAT = 'CSV'` needs SQL Server 2017 or later. The SSAS cube is a later step: Express
has no Analysis Services or Integration Services, so install the (free) Developer edition before it.

| Script | What it does |
|---|---|
| `01_create_db.sql` | Drops and recreates the database named exactly `FlightDW` (the only database these scripts ever touch), schemas `stg` and `dw`. |
| `02_stg_tables.sql` | Staging tables `stg.*` mirroring the CSVs, all `NVARCHAR`. |
| `03_dw_tables.sql` | Star schema in `dw`: `DimDate, DimPassenger, DimAirline, DimTicket, DimAirport, DimPlane, DimSeat, DimPriceRange, Fact_FlightSegment` with primary and foreign keys. |
| `04_load.sql` | `BULK INSERT` of the CSVs into `stg` (`MAXERRORS = 0`: any rejected row fails the load), then empties and refills `dw`. Idempotent: run it twice, same row counts. |
| `05_grant_ssas_read.sql` | Lets the Analysis Services service account `NT Service\MSOLAP$DEV` read `FlightDW` (`db_datareader` only). **Re-run it after every rebuild of `FlightDW`**: `01_create_db.sql` drops the database and with it this user, and the next Process Full of the cube then fails with a login error. Idempotent. |
| `99_checks.sql` | Ten assertions (`RAISERROR(..., 16, 1)` on failure, so `sqlcmd -b` exits non-zero): 600 fact rows, ticket counts, dw row counts equal stg, no orphan keys, stopovers, 11 airlines, Chinese text, dimension rules, date names, age band order. |

## Data folder (permissions)

`BULK INSERT` is executed by the SQL Server service account, which cannot read a user's Desktop. Copy the CSVs from
`data/processed` to a folder it can read and pass that folder as sqlcmd variable `DataDir`:

```
mkdir C:\fdw_data
copy data\processed\*.csv C:\fdw_data\
```

The pytest wrapper does this copy itself (override the folder with `FDW_SQL_DATA_DIR`, the instance with `FDW_SQL_INSTANCE`).

## Run

From the repo root, in cmd.exe:

```
sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\01_create_db.sql
sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\02_stg_tables.sql
sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\03_dw_tables.sql
sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -v DataDir="C:\fdw_data" -i sql\04_load.sql
sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\99_checks.sql
sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\05_grant_ssas_read.sql
```

The last line (the cube's read access) is needed after every rebuild, also after the warehouse tests below, which rebuild
`FlightDW` too; then re-process the cube (README step 5).

Or run the tests. They drop and rebuild `FlightDW`, so they are opt-in: skipped unless `FDW_WAREHOUSE_TESTS=1`, and when
`sqlcmd`, the instance or one of the nine CSVs in `data/processed` is missing (there is no fallback to older copies in
`C:\fdw_data`). Run `python -m fdw.cli` first, then, in cmd.exe:

```
set FDW_WAREHOUSE_TESTS=1
pytest preprocessing/tests/test_warehouse.py -v
```

In Git Bash: `FDW_WAREHOUSE_TESTS=1 pytest preprocessing/tests/test_warehouse.py -v`. Besides running `99_checks.sql` and
reloading twice, they compare the warehouse with pandas on `data/processed/fact_flight_segment.csv` (`SUM(Price)`,
`SUM(Mileage)`, stopover rows, distinct departure and landing airports, rows per airline).

Gotchas found while building this:

- **Quote the DataDir value.** `sqlcmd -v DataDir=C:\fdw_data` fails with `Invalid argument` (it chokes on the drive-letter
  colon); `-v DataDir="C:\fdw_data"` works. In PowerShell write `-v 'DataDir="C:\fdw_data"'`.
- **LF files need `ROWTERMINATOR = '0x0a'`.** `fdw.cli` writes LF line endings; `FORMAT = 'CSV'` without an explicit row
  terminator expects CRLF and fails with the obscure `Cannot obtain the required interface ("IID_IColumnsInfo") from OLE DB
  provider "BULK"`. `04_load.sql` sets it.
- **No embedded newlines** in any CSV field (row count equals line count minus one for all nine files), so a fixed row
  terminator is safe. Quoted fields do occur (workplace values containing commas), which is why `FORMAT = 'CSV'` is used.
- Use `-f 65001` when you want Chinese text in sqlcmd output.

## Modelling notes

- Keys equal the source IDs (`DateKey` = `DateRangeID`, `SegmentID` = `ian`, and so on).
- `dw.DimAirport` has `AirportKey = 0`, `No stopover`; the fact stores `TransitAirportKey = 0` when the CSV transit is empty,
  with `HasStopover` 0/1 and `SegmentCount` = 1. `AirportCode` is nullable (blank in the source for 47 of 184 airports; the fact only uses airports that have a code).
- `DimTicket.AirlineKey` comes from the two-letter `FlightNo` prefix joined to `DimAirline.AirlineCode`; `IsSupplemented` kept.
- `DimDate.DayOfWeek`: 1 = Monday .. 7 = Sunday; `IsSpringFestival` = 1 for 2021-02-11 .. 2021-02-17. Labels for the cube:
  `MonthName` (`February`), `YearMonth` (`2021-02`, sorts naturally), `QuarterName` (`2021 Q1`), `DayName` (`Thursday`); the
  names are built with `CHOOSE`, so they are English whatever the server language is.
- `DimPlane.SizeClass` is derived from the seat count: `Wide` >= 250 seats, `Narrow` 100-249, `Small` < 100. It ignores the size
  label in the source's `planeModel` (the 767, labelled large, has 220 seats and is `Narrow`). F and C cabins only occur on
  planes with >= 100 seats.
- `DimPassenger.AgeBand`: `<25`, `25-34`, `35-44`, `45-54`, `55-64`, `65+`, `Unknown` (age missing), with `AgeBandOrder` 1 .. 7
  as its sort key (`Unknown` last). Group passengers by `PassengerKey`: `PassengerName` has NULLs and duplicates.
- Transit-hub analyses must exclude `AirportKey = 0` (`No stopover`), which every direct flight uses in the transit role.
- Reload: `TRUNCATE` is not allowed on a table referenced by a foreign key, so `04_load.sql` truncates the fact and the staging
  tables and empties the referenced dimensions with `DELETE`, keeping all foreign keys enabled and trusted.
