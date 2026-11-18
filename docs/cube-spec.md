# Cube specification: FlightCube

Single source of truth for the SSAS Multidimensional design. Answer keys (`mdx/answers/`), MDX statements (`mdx/`), the build guide and the report use these names verbatim. Counts marked "verified" were read from `FlightDW` on 2026-11-12 (read-only SELECTs).

## 1. Summary

| Item | Value |
|---|---|
| Analysis Services database | `FlightCube` |
| Cube | `FlightCube` |
| Data source | `FlightDW` (SQL Server database `FlightDW`, schema `dw`, Windows authentication) |
| Data source view | `FlightDW`, over exactly the 9 `dw` tables: `DimDate`, `DimPassenger`, `DimAirline`, `DimTicket`, `DimAirport`, `DimPlane`, `DimSeat`, `DimPriceRange`, `Fact_FlightSegment` |
| Storage mode | MOLAP (the warehouse itself is the ROLAP-style relational star schema) |
| Grain | one passenger on one flight segment (600 fact rows, verified; 95 with stopover, 505 direct) |
| Measure groups | `Flight Segments` (all additive measures), `Segment Passengers` (the distinct-count measure; SSAS requires a separate group) |
| Default measure | `Segment Count` |
| All member name | `All` on every attribute and hierarchy |
| Language | English captions; only airport and airline names are Chinese, taken unchanged from the data |

DSV relationships (all from `Fact_FlightSegment` unless noted): `DepartureDateKey` and `ArrivalDateKey` to `DimDate.DateKey`; `PassengerKey` to `DimPassenger.PassengerKey`; `TicketKey` to `DimTicket.TicketKey`; `DimTicket.AirlineKey` to `DimAirline.AirlineKey`; `DepartureAirportKey`, `TransitAirportKey`, `LandingAirportKey` to `DimAirport.AirportKey`; `PlaneKey` to `DimPlane.PlaneKey`; `CabinKey` to `DimSeat.CabinKey`; `PriceRangeKey` to `DimPriceRange.PriceRangeKey` (11 foreign keys, matching `sys.foreign_keys`).

### DSV named calculations

Added in the DSV so captions are English, sortable and never use personal names. Answer keys must produce the same labels.

| Table | Named calculation | Expression |
|---|---|---|
| `DimDate` | `DayLabel` | `CONVERT(CHAR(10), FullDate, 120)` (ISO text, e.g. `2021-02-11`) |
| `DimDate` | `SpringFestivalKey` | `CAST(IsSpringFestival AS TINYINT)` (TINYINT key, so SSAS never needs a BIT key) |
| `DimDate` | `SpringFestivalLabel` | `CASE WHEN IsSpringFestival = 1 THEN 'Yes' ELSE 'No' END` |
| `DimPassenger` | `PassengerLabel` | `CAST(PassengerKey AS NVARCHAR(10))` (never `PassengerName`) |
| `DimPassenger` | `GenderLabel` | `CASE Gender WHEN N'男' THEN 'Male' WHEN N'女' THEN 'Female' ELSE 'Unknown' END` |
| `DimPassenger` | `WorkplaceLabel` | `ISNULL(RTRIM(Workplace, NCHAR(12288)), 'Unknown')` (trailing ideographic spaces U+3000 stripped: 70 passenger rows (30 distinct texts) end in one, SQL Server compares them equal to the value without it but SSAS does not, so processing would fail with a missing attribute key; needs SQL Server 2022 or later) |
| `DimAirport` | `AirportCodeLabel` | `ISNULL(AirportCode, '')` |
| `DimTicket` | `TicketLabel` | `FlightNo + ' ' + CONVERT(CHAR(16), DepartureTime, 120) + ' (#' + CAST(TicketKey AS NVARCHAR(10)) + ')'` (unique for all 569,157 tickets, verified) |
| `DimTicket` | `SupplementedKey` | `CAST(IsSupplemented AS TINYINT)` (TINYINT key, so SSAS never needs a BIT key) |
| `DimTicket` | `SupplementedLabel` | `CASE WHEN IsSupplemented = 1 THEN 'Yes' ELSE 'No' END` |
| `DimPlane` | `SizeClassOrder` | `CASE SizeClass WHEN 'Small' THEN 1 WHEN 'Narrow' THEN 2 ELSE 3 END` |
| `DimSeat` | `SeatLabel` | `CabinClass + CAST(SeatRow AS NVARCHAR(5)) + SeatLine` (e.g. `F2A`; unique for all 1,353 seats, verified) |

## 2. Dimensions

Cube dimensions are `Departure Date`, `Arrival Date`, `Passenger`, `Departure Airport`, `Transit Airport`, `Landing Airport`, `Flight`, `Plane`, `Cabin`, `Price Range` (10). They come from 7 database dimensions: `Date`, `Passenger`, `Airport`, `Flight`, `Plane`, `Cabin`, `Price Range`.

### 2.1 Role-playing mapping

| Cube dimension | Database dimension | Source table | Fact foreign key |
|---|---|---|---|
| `Departure Date` | `Date` | `dw.DimDate` | `DepartureDateKey` |
| `Arrival Date` | `Date` | `dw.DimDate` | `ArrivalDateKey` |
| `Departure Airport` | `Airport` | `dw.DimAirport` | `DepartureAirportKey` |
| `Transit Airport` | `Airport` | `dw.DimAirport` | `TransitAirportKey` |
| `Landing Airport` | `Airport` | `dw.DimAirport` | `LandingAirportKey` |
| `Passenger` | `Passenger` | `dw.DimPassenger` | `PassengerKey` |
| `Flight` | `Flight` | `dw.DimTicket` joined (snowflake) to `dw.DimAirline` via `AirlineKey` | `TicketKey` |
| `Plane` | `Plane` | `dw.DimPlane` | `PlaneKey` |
| `Cabin` | `Cabin` | `dw.DimSeat` | `CabinKey` |
| `Price Range` | `Price Range` | `dw.DimPriceRange` | `PriceRangeKey` |

### 2.2 Date dimension (`Departure Date`, `Arrival Date`; identical structure)

Source `dw.DimDate`, key `DateKey` (a day-of-year surrogate: 2021-01-01 = 1, 2021-02-11 = 42, 2021-12-31 = 365). The table holds all of 2021 (365 rows, 4 quarters, 12 months); the fact uses only Q1 to Q3.

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Year` | `Year` | `Year` | Key | 1 member (2021) |
| `Quarter` | `QuarterName` | `QuarterName` | Key | members `2021 Q1`..`2021 Q4`; fact: Q1, Q2, Q3 |
| `Month` | `YearMonth` | `MonthName` (caption) | Key (`YearMonth` sorts naturally) | key e.g. `2021-02`, caption `February`; fact: Jan to Aug (8) |
| `Day` (dimension key) | `DateKey` (source `FullDate`) | `DayLabel` | Key | fact: 111 distinct departure days, 112 arrival days, 2021-01-05 to 2021-08-22 |
| `Day Name` | `DayOfWeek` | `DayName` | Key (1 = Monday ... 7 = Sunday) | English names |
| `Is Spring Festival` | `SpringFestivalKey` (from `IsSpringFestival`) | `SpringFestivalLabel` | Key | `Yes` = 2021-02-11 to 2021-02-17 (7 days, verified) |

Hierarchy `Calendar`: `Year` > `Quarter` > `Month` > `Day`. Attribute relationships: `Day` -> `Month` -> `Quarter` -> `Year`; `Day` -> `Day Name`; `Day` -> `Is Spring Festival`.

### 2.3 Passenger

Source `dw.DimPassenger` (62,044 rows; 599 distinct in the fact), key `PassengerKey`. Hierarchies: none (attribute hierarchies only).

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Passenger` (dimension key) | `PassengerKey` | `PassengerLabel` | Key | caption is the key as text; never `PassengerName` |
| `Gender` | `GenderLabel` | `GenderLabel` | Key | `Male`, `Female`, `Unknown` (3 NULL in source) |
| `Age Band` | `AgeBandOrder` | `AgeBand` | Key (= `AgeBandOrder`) | `<25`(1) `25-34`(2) `35-44`(3) `45-54`(4) `55-64`(5) `65+`(6) `Unknown`(7) |
| `FFP Tier` | `FFPTier` | `FFPTier` | Key | values 4, 5, 6 only (verified: 57,124 / 3,409 / 1,511 passengers) |
| `Workplace` | `WorkplaceLabel` | `WorkplaceLabel` | Name | ~3,850 distinct values, 3,704 NULL shown as `Unknown`; free text, not used in a hierarchy |

`PassengerName` is not exposed (9,632 names occur more than once and 610 are NULL). Group and count passengers by the `Passenger` key only.

### 2.4 Airport (`Departure Airport`, `Transit Airport`, `Landing Airport`; identical structure)

Source `dw.DimAirport` (185 rows: 184 real airports plus the `No stopover` row; 31 real provinces plus `N/A`), key `AirportKey`.

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Airport` (dimension key) | `AirportKey` | `AirportName` | Name | Chinese names from the data (unique, verified); `AirportKey 0` = `No stopover` |
| `Province` | `Province` | `Province` | Name | Chinese province names from the data; `N/A` holds only `No stopover` |
| `Airport Code` | `AirportCodeLabel` | `AirportCodeLabel` | Name | blank for 48 rows (47 real airports plus `No stopover`) |

Hierarchy `Geography`: `Province` > `Airport`. Attribute relationship: `Airport` -> `Province`. Longitude and latitude are not exposed.

Fact usage (verified): departure 43 airports in 22 provinces; landing 46 airports in 24 provinces; transit 13 real airports in 10 provinces (plus `No stopover` on 505 rows); 28 real provinces occur in any role.

Unknown-member rules:
- `No stopover` (`AirportKey` 0, `Province` `N/A`) is a real member. It carries all 505 direct segments on `Transit Airport`; it also exists, empty, on `Departure Airport` and `Landing Airport`.
- Every transit-hub statement must exclude it, for example `Except([Transit Airport].[Geography].[Airport].Members, [Transit Airport].[Geography].[Airport].&[0])` (or exclude province `&[N/A]`).
- Statements on `Departure Airport` and `Landing Airport` need no exclusion, but must not show empty `No stopover` rows (use `NON EMPTY`).

### 2.5 Flight

Source `dw.DimTicket` (569,157 rows, 112 flight numbers; 193 tickets and 77 flight numbers used in the fact) snowflaked to `dw.DimAirline` through `DimTicket.AirlineKey` (18 rows in `DimAirline`; 11 have tickets and appear in the fact, 7 have none). Key `TicketKey`.

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Ticket` (dimension key) | `TicketKey` (`DimTicket`) | `TicketLabel` | Key | e.g. `MU5160 2021-01-04 21:45 (#83)` (ticket 83); captions are unique |
| `Flight No` | `FlightNo` (`DimTicket`) | `FlightNo` | Name | each flight number belongs to exactly one airline (verified) |
| `Airline` | `AirlineKey` (`DimAirline`) | `AirlineName` (`DimAirline`) | Name | Chinese names from the data, for example `中国东方航空` (MU) |
| `Airline Code` | `AirlineCode` (`DimAirline`) | `AirlineCode` | Name | two-letter code, e.g. `MU` |
| `Is Supplemented` | `SupplementedKey` (from `IsSupplemented`, `DimTicket`) | `SupplementedLabel` | Key | `Yes` for the 240 supplemental tickets (12 flight numbers) |

Hierarchy `Airline Flight`: `Airline` > `Flight No` > `Ticket`. Attribute relationships: `Ticket` -> `Flight No` -> `Airline` -> `Airline Code`; `Ticket` -> `Is Supplemented`. `Airline` has 18 members (members are read from `DimAirline`); the 7 airlines without tickets are childless top-level members of `Airline Flight` and empty in every measure, so every statement over `Airline` or `Airline Flight` must use `NON EMPTY` (11 airlines remain).

### 2.6 Plane

Source `dw.DimPlane` (18 rows, 18 distinct models, all 18 used in the fact), key `PlaneKey`.

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Plane Model` (dimension key) | `PlaneKey` | `PlaneModel` | Name | Chinese model names from the data, e.g. `波音737(中)` |
| `Size Class` | `SizeClassOrder` | `SizeClass` | Key | `Small`(1, 4 models) `Narrow`(2, 9) `Wide`(3, 5); rule: Wide >= 250 seats, Narrow 100-249, Small < 100 |
| `Seat Count` | `SeatCount` | `SeatCount` | Key | |

Hierarchy `Plane Class`: `Size Class` > `Plane Model`. Attribute relationship: `Plane Model` -> `Size Class`.

### 2.7 Cabin

Source `dw.DimSeat` (1,353 rows: F 110, C 330, Y 913; 467 seats and all 3 classes used in the fact), key `CabinKey`.

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Seat` (dimension key) | `CabinKey` | `SeatLabel` | Name | e.g. `F2A` |
| `Cabin Class` | `CabinClass` | `CabinClass` | Key | captions are the codes `F`, `C`, `Y` (identical to the answer keys) |

No user hierarchy; the drill path Cabin Class > Seat is the attribute relationship `Seat` -> `Cabin Class`, used through attribute hierarchies `[Cabin].[Cabin Class]` and `[Cabin].[Seat]`. `SeatRow` and `SeatLine` are not exposed.

### 2.8 Price Range

Source `dw.DimPriceRange` (30 rows; 28 used in the fact), key `PriceRangeKey` (= `PriceGrade` + 1).

| Attribute | Key column | Name column | Order by | Notes |
|---|---|---|---|---|
| `Price Grade` (dimension key) | `PriceRangeKey` | `PriceGrade` | Key | members named `0`..`29`; grade g covers `MinPrice` = 300g to `MaxPrice` = 300(g+1) |
| `Min Price` | `MinPrice` | `MinPrice` | Key | non-hierarchy attribute |
| `Max Price` | `MaxPrice` | `MaxPrice` | Key | non-hierarchy attribute |

No user hierarchy.

## 3. Measures

All measures are on `Fact_FlightSegment`.

| Measure | Aggregate | Source column | Data Type | Visible | Format string | Measure group |
|---|---|---|---|---|---|---|
| `Segment Count` | Sum | `SegmentCount` | BigInt | yes | `#,##0` | `Flight Segments` |
| `Total Price` | Sum | `Price` | BigInt | yes | `#,##0` | `Flight Segments` |
| `Total Mileage` | Sum | `Mileage` | BigInt | yes | `#,##0` | `Flight Segments` |
| `Stopover Segments` | Sum | `HasStopover` | BigInt | yes | `#,##0` | `Flight Segments` |
| `Rate Sum` | Sum | `Rate` | Double | hidden | `#,##0.00` | `Flight Segments` |
| `Distinct Passengers` | DistinctCount | `PassengerKey` | Integer | yes | `#,##0` | `Segment Passengers` |

Data types are set explicitly on every measure (`Data Type` column above): `SegmentCount` and `HasStopover` are TINYINT in the warehouse, and SSAS would default them to an unsigned tinyint whose Sum overflows past 255, so `Segment Count` and `Stopover Segments` must be BigInt, as must the INT sums `Total Price` and `Total Mileage`; `Rate Sum` is Double (source DECIMAL(4,2)).

Verified totals over all 600 rows: `Segment Count` 600, `Total Price` 1,400,460, `Total Mileage` 1,001,283, `Stopover Segments` 95, `Rate Sum` 470.68, `Distinct Passengers` 599.

### Calculated members (in the `FlightCube` MDX script, parent `[Measures]`)

| Member | Format string | Definition |
|---|---|---|
| `[Measures].[Average Price]` | `#,##0.00` | `IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Total Price] / [Measures].[Segment Count])` |
| `[Measures].[Average Rate]` | `0.000` | `IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Rate Sum] / [Measures].[Segment Count])` |
| `[Measures].[Stopover Share]` | `0.0%` | `IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Stopover Segments] / [Measures].[Segment Count])` |

Overall values: average price 2,334.10, average rate 0.784, stopover share 15.8% (95 / 600). `Distinct Passengers` is not additive; never sum it across members.

## 4. Worked example member paths (one per hierarchy)

Keys: `&[...]` is the member key; name paths also work where the name is unique.

| Hierarchy | Level | Example |
|---|---|---|
| `[Departure Date].[Calendar]` | Year | `[Departure Date].[Calendar].[Year].&[2021]` |
| | Quarter | `[Departure Date].[Calendar].[Quarter].&[2021 Q1]` |
| | Month | `[Departure Date].[Calendar].[Month].&[2021-02]` (caption `February`) |
| | Day | `[Departure Date].[Calendar].[Day].&[42]` (2021-02-11) |
| `[Arrival Date].[Calendar]` | Month | `[Arrival Date].[Calendar].[Month].&[2021-03]` |
| `[Departure Airport].[Geography]` | Province | `[Departure Airport].[Geography].[Province].&[山东]` |
| | Airport | `[Departure Airport].[Geography].[Airport].&[3]` (流亭机场) |
| `[Transit Airport].[Geography]` | Province | `[Transit Airport].[Geography].[Province].&[山东]`; no stopover: `[Transit Airport].[Geography].[Province].&[N/A]` |
| | Airport | `[Transit Airport].[Geography].[Airport].&[3]`; no stopover: `[Transit Airport].[Geography].[Airport].&[0]` |
| `[Landing Airport].[Geography]` | Airport | `[Landing Airport].[Geography].[Airport].&[3]` |
| `[Flight].[Airline Flight]` | Airline | `[Flight].[Airline Flight].[Airline].&[3]` (中国东方航空, MU) |
| | Flight No | `[Flight].[Airline Flight].[Flight No].&[MU5160]` |
| | Ticket | `[Flight].[Airline Flight].[Ticket].&[83]` (a ticket of MU5160) |
| `[Plane].[Plane Class]` | Size Class | `[Plane].[Plane Class].[Size Class].&[2]` (Narrow) |
| | Plane Model | `[Plane].[Plane Class].[Plane Model].&[1]` (波音737(中)) |

Attribute hierarchies without a user hierarchy: `[Passenger].[Age Band].&[7]` (`Unknown`, a real member; `[Passenger].[Age Band].&[1]` = `<25`), `[Passenger].[FFP Tier].&[4]`, `[Passenger].[Gender].&[Female]`, `[Departure Date].[Is Spring Festival].&[1]` (Yes; `&[0]` = No; also on `[Arrival Date]`), `[Flight].[Is Supplemented].&[1]` (Yes; `&[0]` = No), `[Cabin].[Cabin Class].&[F]`, `[Cabin].[Seat].&[1]`, `[Price Range].[Price Grade].&[3]` (grade 2, 600 to 900).

## 5. Modelling rules

1. Group, count and rank passengers by `PassengerKey` (`[Passenger].[Passenger]`), never by `PassengerName` (NULLs and duplicates in the source). The name is not in the cube.
2. Captions are English. Exceptions, taken unchanged from the data: airport names, province names, airline names, plane model names.
3. `No stopover` (`AirportKey 0`, province `N/A`) must be excluded from every transit-hub statement. `Age Band` `Unknown` is a real member and is kept.
4. Every member shown as a caption must equal the label the T-SQL answer key produces (same named calculations as section 1).
5. Dates in the fact run 2021-01-05 to 2021-08-22 (the `Date` dimension covers all of 2021, so Q4 and Sep to Dec exist but are empty; use `NON EMPTY`). Spring Festival = 2021-02-11 to 2021-02-17.
6. `Rate Sum` is hidden; users see only `Average Rate`. Divide only through the guarded calculated members.
7. Role-playing dimensions are separate cube dimensions over one database dimension; MDX must name the role (`[Departure Date]`, not `[Date]`).

## 6. Names registry

Machine-greppable: one name per line, format `<kind>: <name>`. Every identifier in an MDX file must appear here.

```
cube: FlightCube
database: FlightCube
data source: FlightDW
data source view: FlightDW
measure group: Flight Segments
measure group: Segment Passengers
measure: Segment Count
measure: Total Price
measure: Total Mileage
measure: Stopover Segments
measure: Rate Sum
measure: Distinct Passengers
calculated member: Average Price
calculated member: Average Rate
calculated member: Stopover Share
dimension: Departure Date
dimension: Arrival Date
dimension: Passenger
dimension: Departure Airport
dimension: Transit Airport
dimension: Landing Airport
dimension: Flight
dimension: Plane
dimension: Cabin
dimension: Price Range
database dimension: Date
database dimension: Airport
hierarchy: Calendar
hierarchy: Geography
hierarchy: Airline Flight
hierarchy: Plane Class
level: Year
level: Quarter
level: Month
level: Day
level: Province
level: Airport
level: Airline
level: Flight No
level: Ticket
level: Size Class
level: Plane Model
attribute: Passenger
attribute: Plane Model
attribute: Day Name
attribute: Is Spring Festival
attribute: Gender
attribute: Age Band
attribute: FFP Tier
attribute: Workplace
attribute: Airport Code
attribute: Airline Code
attribute: Is Supplemented
attribute: Seat Count
attribute: Seat
attribute: Cabin Class
attribute: Price Grade
attribute: Min Price
attribute: Max Price
member: No stopover
member: N/A
member: Unknown
```
