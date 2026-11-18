-- 04_load.sql: load the CSVs into stg (BULK INSERT), then rebuild the dw tables from stg. Idempotent:
-- running it again leaves the same row counts.
--   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -v DataDir="C:\fdw_data" -i 04_load.sql
-- (the value must be quoted: an unquoted -v DataDir=C:\fdw_data fails with "Invalid argument")
-- DataDir must be readable by the SQL Server service account (not under a user's Desktop).
-- CSVs are UTF-8 with BOM, quoted where a text field contains a comma (FORMAT = 'CSV', SQL Server 2017+),
-- no embedded newlines, LF line endings (as written by fdw.cli). ROWTERMINATOR = '0x0a' is required:
-- FORMAT = 'CSV' without it expects CRLF and fails on LF files with the obscure error
-- 'Cannot obtain the required interface (IID_IColumnsInfo) from OLE DB provider BULK'. Empty cell = NULL.
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
USE FlightDW;
GO

-- 1. Staging: empty, then BULK INSERT every CSV (stg columns are all NVARCHAR, so nothing can fail on typing).
--    MAXERRORS = 0: a single malformed row fails the load instead of being skipped.
TRUNCATE TABLE stg.fact_flight_segment;
TRUNCATE TABLE stg.dim_ticket;
TRUNCATE TABLE stg.dim_passenger;
TRUNCATE TABLE stg.dim_airport;
TRUNCATE TABLE stg.dim_airline;
TRUNCATE TABLE stg.dim_plane;
TRUNCATE TABLE stg.dim_seat;
TRUNCATE TABLE stg.dim_price_range;
TRUNCATE TABLE stg.dim_date;
GO

DECLARE @files TABLE (id INT IDENTITY(1,1), tbl SYSNAME, csv NVARCHAR(100));
INSERT @files (tbl, csv) VALUES
    (N'stg.fact_flight_segment', N'fact_flight_segment.csv'),
    (N'stg.dim_ticket',          N'dim_ticket.csv'),
    (N'stg.dim_passenger',       N'dim_passenger.csv'),
    (N'stg.dim_airport',         N'dim_airport.csv'),
    (N'stg.dim_airline',         N'dim_airline.csv'),
    (N'stg.dim_plane',           N'dim_plane.csv'),
    (N'stg.dim_seat',            N'dim_seat.csv'),
    (N'stg.dim_price_range',     N'dim_price_range.csv'),
    (N'stg.dim_date',            N'dim_date.csv');
DECLARE @i INT = 1, @tbl SYSNAME, @csv NVARCHAR(100), @sql NVARCHAR(MAX);
WHILE @i <= (SELECT MAX(id) FROM @files)
BEGIN
    SELECT @tbl = tbl, @csv = csv FROM @files WHERE id = @i;
    -- BULK INSERT needs a literal path, so build the statement dynamically ($(DataDir) is a sqlcmd variable)
    SET @sql = N'BULK INSERT ' + @tbl + N' FROM ''$(DataDir)\' + @csv + N''' WITH ('
             + N'FORMAT = ''CSV'', FIELDQUOTE = ''"'', CODEPAGE = ''65001'', ROWTERMINATOR = ''0x0a'', '
             + N'FIRSTROW = 2, MAXERRORS = 0, KEEPNULLS, TABLOCK)';
    EXEC (@sql);
    SET @i += 1;
END
GO

-- 2. Warehouse: empty the dw tables. TRUNCATE is not allowed on a table referenced by a foreign key,
--    so the fact (referencing) is truncated and the referenced dimensions are emptied with DELETE.
TRUNCATE TABLE dw.Fact_FlightSegment;
DELETE FROM dw.DimTicket;
DELETE FROM dw.DimAirline;
DELETE FROM dw.DimDate;
DELETE FROM dw.DimPassenger;
DELETE FROM dw.DimAirport;
DELETE FROM dw.DimPlane;
DELETE FROM dw.DimSeat;
DELETE FROM dw.DimPriceRange;
GO

-- 3. Dimensions (empty string -> NULL; strict conversions, so bad data fails the load).
-- Names are built with CHOOSE (not DATENAME), so they are English whatever the server language is.
INSERT dw.DimDate (DateKey, FullDate, [Year], [Quarter], [Month], [Day], [DayOfWeek],
                   MonthName, YearMonth, QuarterName, DayName, IsSpringFestival)
SELECT CAST(DateRangeID AS INT),
       d.dt,
       CAST([Year] AS SMALLINT),
       DATEPART(QUARTER, d.dt),
       CAST([Month] AS TINYINT),
       DAY(d.dt),
       w.dow,
       CHOOSE(MONTH(d.dt), N'January', N'February', N'March', N'April', N'May', N'June', N'July',
              N'August', N'September', N'October', N'November', N'December'),
       CONVERT(CHAR(7), d.dt, 126),                          -- 'yyyy-mm'
       CONCAT(YEAR(d.dt), N' Q', DATEPART(QUARTER, d.dt)),
       CHOOSE(w.dow, N'Monday', N'Tuesday', N'Wednesday', N'Thursday', N'Friday', N'Saturday', N'Sunday'),
       CASE WHEN d.dt BETWEEN '2021-02-11' AND '2021-02-17' THEN 1 ELSE 0 END
FROM stg.dim_date s
CROSS APPLY (SELECT CAST(s.[Date] AS DATE) AS dt) d
CROSS APPLY (SELECT (DATEDIFF(DAY, '19000101', d.dt) % 7) + 1 AS dow) w;   -- 1900-01-01 was a Monday: 1 = Mon .. 7 = Sun

INSERT dw.DimPassenger (PassengerKey, Gender, Age, AgeBand, AgeBandOrder, Workplace, FFPTier, FlightCount,
                        PassengerName)
SELECT CAST(PassengerID AS INT),
       NULLIF(PassengerGender, N''),
       a.age,
       CHOOSE(b.band, N'<25', N'25-34', N'35-44', N'45-54', N'55-64', N'65+', N'Unknown'),
       b.band,
       NULLIF(PassengerWorkplace, N''),
       CAST(FFP_TIER AS TINYINT),
       CAST(FLIGHT_COUNT AS INT),
       NULLIF(PassengerName, N'')
FROM stg.dim_passenger s
CROSS APPLY (SELECT CAST(NULLIF(s.PassengerAge, N'') AS SMALLINT) AS age) a
CROSS APPLY (SELECT CASE WHEN a.age IS NULL THEN 7                  -- Unknown sorts last
                         WHEN a.age < 25 THEN 1
                         WHEN a.age < 35 THEN 2
                         WHEN a.age < 45 THEN 3
                         WHEN a.age < 55 THEN 4
                         WHEN a.age < 65 THEN 5
                         ELSE 6 END AS band) b;

INSERT dw.DimAirline (AirlineKey, AirlineName, AirlineCode, PlaneNumber)
SELECT CAST(AirlinesID AS INT), airlines, airlinesCode, CAST(NULLIF(planeNumber, N'') AS INT)
FROM stg.dim_airline;

INSERT dw.DimAirport (AirportKey, AirportName, AirportCode, Province, Longitude, Latitude)
VALUES (0, N'No stopover', NULL, N'N/A', NULL, NULL);       -- target of Transit = NULL in the fact
INSERT dw.DimAirport (AirportKey, AirportName, AirportCode, Province, Longitude, Latitude)
SELECT CAST(AirportID AS INT), ariport, NULLIF(airportCode, N''), NULLIF(city, N''),
       CAST(NULLIF(Ariport_X, N'') AS DECIMAL(12,8)),      -- longitude
       CAST(NULLIF(Ariport_y, N'') AS DECIMAL(12,8))       -- latitude
FROM stg.dim_airport;

-- SizeClass is derived from the seat count, not from the size label in the source's planeModel
-- (the 767, labelled large, has 220 seats and is 'Narrow').
INSERT dw.DimPlane (PlaneKey, PlaneModel, SeatCount, SizeClass)
SELECT CAST(PlaneID AS INT), planeModel, CAST(SeatNum AS INT),
       CASE WHEN CAST(SeatNum AS INT) >= 250 THEN N'Wide'
            WHEN CAST(SeatNum AS INT) >= 100 THEN N'Narrow'
            ELSE N'Small' END
FROM stg.dim_plane;

INSERT dw.DimSeat (CabinKey, CabinClass, SeatRow, SeatLine)
SELECT CAST(CabinID AS INT), CabinClass, CAST(SeatRow AS SMALLINT), SeatLine
FROM stg.dim_seat;

INSERT dw.DimPriceRange (PriceRangeKey, MinPrice, MaxPrice, PriceGrade)
SELECT CAST(PriceRangeID AS INT), CAST(MinNum AS INT), CAST(MaxNum AS INT), CAST(PriceGrade AS INT)
FROM stg.dim_price_range;

-- LEFT JOIN so a FlightNo prefix without an airline fails the NOT NULL on AirlineKey instead of dropping the ticket.
INSERT dw.DimTicket (TicketKey, FlightNo, DepartureTime, DelayMinutes, ArrivalTime, AirlineKey, IsSupplemented)
SELECT CAST(t.TicketID AS INT), t.FlightNo, CAST(t.departureTime AS DATETIME2(0)), CAST(t.delayTime AS INT),
       CAST(t.arrivalTime AS DATETIME2(0)), a.AirlineKey, CAST(t.IsSupplemented AS BIT)
FROM stg.dim_ticket t
LEFT JOIN dw.DimAirline a ON a.AirlineCode = LEFT(t.FlightNo, 2);
GO

-- 4. Fact: transit NULL -> AirportKey 0 ('No stopover'), HasStopover derived from it, SegmentCount = 1.
INSERT dw.Fact_FlightSegment (SegmentID, DepartureDateKey, ArrivalDateKey, PassengerKey, TicketKey,
       DepartureAirportKey, TransitAirportKey, LandingAirportKey, PlaneKey, CabinKey, PriceRangeKey,
       Price, Rate, Mileage, HasStopover, SegmentCount)
SELECT CAST(ian AS INT), CAST(DepartureDateID AS INT), CAST(ArrivalDateID AS INT), CAST(PassengerID AS INT),
       CAST(TicketID AS INT), CAST(Departure_ariportID AS INT),
       COALESCE(CAST(NULLIF(Transit_ariportID, N'') AS INT), 0),
       CAST(Landing_ariportID AS INT), CAST(PlaneID AS INT), CAST(CabinID AS INT), CAST(PriceRangeID AS INT),
       CAST(Price AS INT), CAST(Rate AS DECIMAL(4,2)), CAST(mileage AS INT),
       CASE WHEN NULLIF(Transit_ariportID, N'') IS NULL THEN 0 ELSE 1 END, 1
FROM stg.fact_flight_segment;
GO

PRINT 'load complete';
SELECT N'dw.Fact_FlightSegment' AS tbl, COUNT(*) AS n FROM dw.Fact_FlightSegment
UNION ALL SELECT N'dw.DimTicket', COUNT(*) FROM dw.DimTicket
UNION ALL SELECT N'dw.DimPassenger', COUNT(*) FROM dw.DimPassenger
UNION ALL SELECT N'dw.DimAirport', COUNT(*) FROM dw.DimAirport
UNION ALL SELECT N'dw.DimAirline', COUNT(*) FROM dw.DimAirline
UNION ALL SELECT N'dw.DimPlane', COUNT(*) FROM dw.DimPlane
UNION ALL SELECT N'dw.DimSeat', COUNT(*) FROM dw.DimSeat
UNION ALL SELECT N'dw.DimPriceRange', COUNT(*) FROM dw.DimPriceRange
UNION ALL SELECT N'dw.DimDate', COUNT(*) FROM dw.DimDate;
GO
