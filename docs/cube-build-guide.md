# Cube build guide (Visual Studio + Analysis Services Multidimensional)

The cube `FlightCube` is defined exactly in [docs/cube-spec.md](cube-spec.md): that file is the authority for every name, key, caption, sort order and measure. Screenshot ids (C1 to C4) refer to [screenshot-checklist.md](screenshot-checklist.md).

**Before you start:** `powershell -File tools\check_env.ps1` shows all PASS, the warehouse `FlightDW` is built (`sql\99_checks.sql` passes) and `sql\05_grant_ssas_read.sql` has been run after the last rebuild of `FlightDW` (see README step 3). No password is typed anywhere in this guide: the cube reads `FlightDW` as the Analysis Services service account.

## Primary path: the cube is built by script; screenshots C1-C4 via Visual Studio import or SSMS

**(a) Deploy by script.** Follow README step 5: `python tools\build_cube_xmla.py` (only if `docs\cube-spec.md` changed), then `powershell -File tools\deploy_cube.ps1 -Smoke`. It creates and processes the database `FlightCube` on the instance `DEV` from `ssas\FlightCube.xmla`. The data source uses `ImpersonateServiceAccount`: Analysis Services connects to `FlightDW` as its own service account `NT Service\MSOLAP$DEV`, which `sql\05_grant_ssas_read.sql` made a read-only user of `FlightDW`. No password is stored or typed.

**(b) Designer screenshots C1 to C3 from an imported project.** *UI wording may differ between Visual Studio versions: send a screenshot if a step does not match.*

1. Find the Analysis Services port (Windows PowerShell): `Get-NetTCPConnection -State Listen -OwningProcess (Get-Process msmdsrv).Id | Select-Object LocalPort`. If the SQL Server Browser service is running, the instance name `localhost\DEV` works instead of `localhost:<port>`.
2. Visual Studio 2019 > **File > New > Project** > **Import from Server (Multidimensional and Data Mining)**. Name it `FlightCubeImport` and put it **outside** the repo (for example in `Documents`), so nothing generated is committed by accident.
3. In the wizard: server `localhost:<port>` (from step 1), database **FlightCube**. Finish; the wizard copies the deployed definition into the project.
4. Take the screenshots: **C1** double-click the data source view `FlightDW` (the nine tables and their relationships); **C2** double-click the cube `FlightCube`, tab **Cube Structure** and tab **Dimension Usage** (the 3 airport roles and 2 date roles); **C3** open the dimension `Date` (hierarchy `Calendar`) and the dimension `Airport` (hierarchy `Geography`).
5. Close the project **without deploying** it. Do not use Build > Deploy from this imported project: the script and `ssas\FlightCube.xmla` are the source of truth, and a deploy from the imported copy could overwrite the cube with different settings.

**(c) C4 in SSMS.** Connect to **Analysis Services** `localhost:<port>` (or `localhost\DEV`), open a new **MDX query** on `FlightCube` and run the smoke query of section 8 below (expected `600`, `95`, `1,400,460`, `599`). Screenshot the query with its result.

## Fallback: click-through build (only if the script cannot be used)

This part builds the same cube by hand. Menu wording can differ slightly between Visual Studio versions; if a step does not match what you see, take a screenshot and send it. If you build this way, do not also run `deploy_cube.ps1` afterwards without checking: both write the database `FlightCube`.

### 1. Create the project

1. Visual Studio > **File > New > Project** > **Analysis Services Multidimensional and Data Mining Project**. Name `FlightCube`, location `ssas\` in your copy of the repo (`<repo>\ssas`, where `<repo>` is the folder you cloned the project into). Untick "Create directory for solution" if offered, so the project files sit in `ssas\FlightCube\`.
2. In **Solution Explorer** you will see Data Sources, Data Source Views, Cubes, Dimensions, Mining Structures, Roles, Assemblies, Miscellaneous.

### 2. Data source (`FlightDW`)

1. Right-click **Data Sources > New Data Source** > **New** (connection). Provider: *Microsoft OLE DB Driver for SQL Server* (or *Native OLE DB > SQL Server Native Client*). Server name: `localhost\SQLEXPRESS`. Authentication: Windows. Database: `FlightDW`. **Test Connection** must succeed.
2. **Impersonation Information:** choose **Use the service account** (the same `ImpersonateServiceAccount` the script uses). It works once `sql\05_grant_ssas_read.sql` has given `NT Service\MSOLAP$DEV` read access to `FlightDW`. Never choose an option that stores a typed Windows password in the project, and never put a password in a file. Name the data source `FlightDW`.
3. If the test fails with a "cannot find server" error, start the **SQL Server Browser** service (it is stopped on this machine): Services > SQL Server Browser > Start.

### 3. Data source view (`FlightDW`)

1. Right-click **Data Source Views > New Data Source View**, data source `FlightDW`. Select exactly the nine `dw` tables: `DimDate`, `DimPassenger`, `DimAirline`, `DimTicket`, `DimAirport`, `DimPlane`, `DimSeat`, `DimPriceRange`, `Fact_FlightSegment`. Name the view `FlightDW`.
2. The wizard imports the 11 foreign keys as relationships. Check in the diagram that the fact table has 10 lines and `DimTicket` has one line to `DimAirline` (compare with section 1 of the spec). Screenshot **C1**: the diagram.
3. Add the named calculations from spec section 1 (right-click the table > **New Named Calculation**, give the name and the exact expression): `DimDate`: `DayLabel`, `SpringFestivalKey`, `SpringFestivalLabel`. `DimPassenger`: `PassengerLabel`, `GenderLabel`, `WorkplaceLabel`. `DimAirport`: `AirportCodeLabel`. `DimTicket`: `TicketLabel`, `SupplementedKey`, `SupplementedLabel`. `DimPlane`: `SizeClassOrder`. `DimSeat`: `SeatLabel`. Use the **Explore Data** command on a table to see that the new columns return values and no errors.
4. Set the logical primary keys if the view reports tables without one (the physical primary keys are normally detected).

### 4. Dimensions (spec section 2)

Use **Dimensions > New Dimension > Use an existing table** for each of the seven database dimensions; set the key column and the name column as in the spec tables.

| Database dimension | Table | Key / Name | Notes to apply |
|---|---|---|---|
| `Date` | `DimDate` | `DateKey` / `DayLabel` | attributes Year, Quarter (`QuarterName`), Month (key `YearMonth`, name `MonthName`), Day Name (key `DayOfWeek`, name `DayName`), Is Spring Festival (key `SpringFestivalKey`, name `SpringFestivalLabel`); hierarchy `Calendar` = Year > Quarter > Month > Day |
| `Passenger` | `DimPassenger` | `PassengerKey` / `PassengerLabel` | attributes Gender (`GenderLabel`), Age Band (key `AgeBandOrder`, name `AgeBand`), FFP Tier, Workplace (`WorkplaceLabel`); no hierarchy; do not add `PassengerName` |
| `Airport` | `DimAirport` | `AirportKey` / `AirportName` | attributes Province, Airport Code (`AirportCodeLabel`); hierarchy `Geography` = Province > Airport |
| `Flight` | `DimTicket` + `DimAirline` | `TicketKey` / `TicketLabel` | add `DimAirline` as a second table of the dimension (snowflake): attributes Flight No, Airline (key `AirlineKey`, name `AirlineName`), Airline Code, Is Supplemented (key `SupplementedKey`); hierarchy `Airline Flight` = Airline > Flight No > Ticket |
| `Plane` | `DimPlane` | `PlaneKey` / `PlaneModel` | attributes Size Class (key `SizeClassOrder`, name `SizeClass`), Seat Count; hierarchy `Plane Class` = Size Class > Plane Model |
| `Cabin` | `DimSeat` | `CabinKey` / `SeatLabel` | attributes Cabin Class (`CabinClass`); no hierarchy |
| `Price Range` | `DimPriceRange` | `PriceRangeKey` / `PriceGrade` | attributes Min Price, Max Price; no hierarchy |

For every hierarchy open the **Attribute Relationships** tab and create the relationships from the spec (for example Day to Month to Quarter to Year, Ticket to Flight No to Airline, Airport to Province, Plane Model to Size Class); a hierarchy with a green "no relationship" warning is wrong. Set **OrderBy** exactly as the "Order by" column of the spec. Screenshot **C3** shows the `Calendar` and `Geography` hierarchies.

### 5. Cube, measures and role-playing dimensions (spec sections 2.1 and 3)

1. **Cubes > New Cube > Use existing tables**. Measure group table: `Fact_FlightSegment`. Tick the measures `SegmentCount`, `Price`, `Mileage`, `HasStopover`, `Rate`; untick the key columns. Pick the seven dimensions above. Name the cube `FlightCube`.
2. In the cube's **Cube Structure** tab rename the measures: `Segment Count`, `Total Price`, `Total Mileage`, `Stopover Segments`, `Rate Sum`; the measure group `Flight Segments`. Set each measure's **DataType** as in the spec (BigInt for the four sums, Double for `Rate Sum`), **FormatString** as in the spec, and **Visible = False** for `Rate Sum`.
3. **Distinct count:** right-click the cube > **New Measure** > Usage **Distinct count**, source table `Fact_FlightSegment`, column `PassengerKey`, tick the option to create a new measure group named `Segment Passengers`; name the measure `Distinct Passengers` (DataType Integer).
4. **Role-playing:** open the **Dimension Usage** tab. Add the cube dimensions `Departure Date` and `Arrival Date` (both based on the database dimension `Date`), and `Departure Airport`, `Transit Airport`, `Landing Airport` (all based on `Airport`), then delete the plain `Date` and `Airport` rows. For each role select the relationship type **Regular** and the fact column from the spec table 2.1 (`DepartureDateKey`, `ArrivalDateKey`, `DepartureAirportKey`, `TransitAirportKey`, `LandingAirportKey`). Check that **both** measure groups have a Regular relationship to all ten cube dimensions (the distinct-count group needs `Flight` and `Passenger`). Screenshot **C2**: the Dimension Usage grid.
5. Set the cube's **DefaultMeasure** to `Segment Count`.

### 6. Calculated members

Open the **Calculations** tab, switch to **Script View**, and paste these three definitions (they are the three rows of spec section 3):

```
CREATE MEMBER CURRENTCUBE.[Measures].[Average Price] AS
  IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Total Price] / [Measures].[Segment Count]),
  FORMAT_STRING = "#,##0.00", VISIBLE = 1;
CREATE MEMBER CURRENTCUBE.[Measures].[Average Rate] AS
  IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Rate Sum] / [Measures].[Segment Count]),
  FORMAT_STRING = "0.000", VISIBLE = 1;
CREATE MEMBER CURRENTCUBE.[Measures].[Stopover Share] AS
  IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Stopover Segments] / [Measures].[Segment Count]),
  FORMAT_STRING = "0.0%", VISIBLE = 1;
```

### 7. Deploy and process

1. **Project > FlightCube Properties > Deployment**: Server `localhost:<port>` (the Analysis Services instance `DEV` from `docs\environment-setup.md`; `localhost\DEV` only while SQL Server Browser runs), Database `FlightCube`, Processing Option **Full**. Close the dialog.
2. **Build > Deploy Solution**. If processing fails with a login or "cannot connect to data source" error, re-check the data-source impersonation (step 2.2) and re-run `sql\05_grant_ssas_read.sql` (a rebuild of `FlightDW` removes the grant). A duplicate or missing key error on `Workplace` should not occur: the named calculation `WorkplaceLabel` (`ISNULL(RTRIM(Workplace, NCHAR(12288)), 'Unknown')`, cube spec section 1) strips the trailing ideographic spaces that caused it, so if it appears, check that expression rather than ignoring key errors.
3. After the green "Deployment completed successfully" message, screenshot **C2/C3** as needed.

### 8. Smoke test (must pass before anything else)

In SSMS connect to **Analysis Services** `localhost:<port>` (port as in step (b)1 above; `localhost\DEV` only works while SQL Server Browser runs), open a new **MDX query** on database `FlightCube`, cube `FlightCube`:

```
SELECT { [Measures].[Segment Count], [Measures].[Stopover Segments], [Measures].[Total Price], [Measures].[Distinct Passengers] } ON 0
FROM [FlightCube]
```

Expected (verified totals in the spec): `600`, `95`, `1,400,460`, `599`. Screenshot **C4**. Then run `[Measures].[Average Price]` (expect `2,334.10`). If any number differs, the cube or its relationships are wrong: stop and send me the screenshot before running the statements.

### 9. Save and commit

Close Visual Studio, then commit `ssas\FlightCube\` (the `.sln`, `.dwproj`, `.ds`, `.dsv`, `.dim`, `.cube`, `.database` files). Do not commit `bin\`, `obj\` or `.asdatabase` files (they are in `.gitignore`).
