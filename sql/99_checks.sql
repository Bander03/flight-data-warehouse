-- 99_checks.sql: assertions on the loaded warehouse. Any failure raises severity 16, so
-- `sqlcmd -b` exits non-zero. Each assertion is its own batch (GO) so the first failure stops the run.
-- Run after 04_load.sql:  sqlcmd -S localhost\SQLEXPRESS -E -b -i 99_checks.sql   (it only reads FlightDW, so no DataDir is needed)
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
USE FlightDW;
GO

-- 1. Fact has all 600 segments, and SegmentCount adds up.
DECLARE @n INT = (SELECT COUNT(*) FROM dw.Fact_FlightSegment);
IF @n <> 600 RAISERROR(N'CHECK FAILED: fact rows = %d, expected 600', 16, 1, @n);
ELSE PRINT 'PASS: fact has 600 rows';
DECLARE @s INT = (SELECT SUM(SegmentCount) FROM dw.Fact_FlightSegment);
IF @s <> 600 RAISERROR(N'CHECK FAILED: SUM(SegmentCount) = %d, expected 600', 16, 1, @s);
ELSE PRINT 'PASS: SegmentCount sums to 600';
GO

-- 2. Ticket count = original 568,917 + supplemental tickets (flagged IsSupplemented = 1) = CSV rows.
DECLARE @orig INT = (SELECT COUNT(*) FROM dw.DimTicket WHERE IsSupplemented = 0);
DECLARE @supp INT = (SELECT COUNT(*) FROM dw.DimTicket WHERE IsSupplemented = 1);
DECLARE @csv  INT = (SELECT COUNT(*) FROM stg.dim_ticket);
IF @orig <> 568917 RAISERROR(N'CHECK FAILED: original tickets = %d, expected 568917', 16, 1, @orig);
ELSE IF @orig + @supp <> @csv RAISERROR(N'CHECK FAILED: DimTicket rows %d <> CSV rows %d', 16, 1, @orig, @csv);
ELSE PRINT 'PASS: DimTicket = 568917 original + supplemental = CSV rows';
GO

-- 3. Every dw table row count equals its stg table. This compares dw with staging, not with the CSV files:
--    staging holds what BULK INSERT read (MAXERRORS = 0 fails the load on any rejected row), and the opt-in
--    pytest test_row_counts_match_csv compares with the files themselves. DimAirport has one extra row (key 0).
DECLARE @bad NVARCHAR(400) = N'';
SELECT @bad = @bad + t + N' dw=' + CAST(d AS NVARCHAR(20)) + N' csv=' + CAST(s AS NVARCHAR(20)) + N'; '
FROM (
    SELECT N'DimDate' t, (SELECT COUNT(*) FROM dw.DimDate) d, (SELECT COUNT(*) FROM stg.dim_date) s
    UNION ALL SELECT N'DimPassenger', (SELECT COUNT(*) FROM dw.DimPassenger), (SELECT COUNT(*) FROM stg.dim_passenger)
    UNION ALL SELECT N'DimAirline', (SELECT COUNT(*) FROM dw.DimAirline), (SELECT COUNT(*) FROM stg.dim_airline)
    UNION ALL SELECT N'DimTicket', (SELECT COUNT(*) FROM dw.DimTicket), (SELECT COUNT(*) FROM stg.dim_ticket)
    UNION ALL SELECT N'DimAirport(+1 No stopover)', (SELECT COUNT(*) FROM dw.DimAirport), (SELECT COUNT(*) + 1 FROM stg.dim_airport)
    UNION ALL SELECT N'DimPlane', (SELECT COUNT(*) FROM dw.DimPlane), (SELECT COUNT(*) FROM stg.dim_plane)
    UNION ALL SELECT N'DimSeat', (SELECT COUNT(*) FROM dw.DimSeat), (SELECT COUNT(*) FROM stg.dim_seat)
    UNION ALL SELECT N'DimPriceRange', (SELECT COUNT(*) FROM dw.DimPriceRange), (SELECT COUNT(*) FROM stg.dim_price_range)
    UNION ALL SELECT N'Fact_FlightSegment', (SELECT COUNT(*) FROM dw.Fact_FlightSegment), (SELECT COUNT(*) FROM stg.fact_flight_segment)
) x WHERE d <> s;
IF @bad <> N'' RAISERROR(N'CHECK FAILED: dw row counts differ from stg: %s', 16, 1, @bad);
ELSE PRINT 'PASS: every dw table row count equals its stg table';
GO

-- 4. No orphan foreign keys (checked by join, independent of the declared constraints) ...
DECLARE @bad NVARCHAR(400) = N'';
SELECT @bad = @bad + fk + N'=' + CAST(n AS NVARCHAR(20)) + N' '
FROM (
    SELECT N'DepartureDateKey' fk, COUNT(*) n FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimDate d WHERE d.DateKey = f.DepartureDateKey)
    UNION ALL SELECT N'ArrivalDateKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimDate d WHERE d.DateKey = f.ArrivalDateKey)
    UNION ALL SELECT N'PassengerKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimPassenger d WHERE d.PassengerKey = f.PassengerKey)
    UNION ALL SELECT N'TicketKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimTicket d WHERE d.TicketKey = f.TicketKey)
    UNION ALL SELECT N'DepartureAirportKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimAirport d WHERE d.AirportKey = f.DepartureAirportKey)
    UNION ALL SELECT N'TransitAirportKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimAirport d WHERE d.AirportKey = f.TransitAirportKey)
    UNION ALL SELECT N'LandingAirportKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimAirport d WHERE d.AirportKey = f.LandingAirportKey)
    UNION ALL SELECT N'PlaneKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimPlane d WHERE d.PlaneKey = f.PlaneKey)
    UNION ALL SELECT N'CabinKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimSeat d WHERE d.CabinKey = f.CabinKey)
    UNION ALL SELECT N'PriceRangeKey', COUNT(*) FROM dw.Fact_FlightSegment f WHERE NOT EXISTS (SELECT 1 FROM dw.DimPriceRange d WHERE d.PriceRangeKey = f.PriceRangeKey)
    UNION ALL SELECT N'DimTicket.AirlineKey', COUNT(*) FROM dw.DimTicket t WHERE t.AirlineKey IS NULL OR NOT EXISTS (SELECT 1 FROM dw.DimAirline d WHERE d.AirlineKey = t.AirlineKey)
) x WHERE n > 0;
IF @bad <> N'' RAISERROR(N'CHECK FAILED: orphan keys: %s', 16, 1, @bad);
ELSE PRINT 'PASS: no orphan foreign keys';

-- ... and the declared foreign keys exist (11) and are trusted (they stay enabled during the reload, so they are never disabled or untrusted).
DECLARE @fks INT = (SELECT COUNT(*) FROM sys.foreign_keys WHERE schema_id = SCHEMA_ID(N'dw'));
DECLARE @untrusted INT = (SELECT COUNT(*) FROM sys.foreign_keys WHERE schema_id = SCHEMA_ID(N'dw') AND (is_not_trusted = 1 OR is_disabled = 1));
IF @fks <> 11 RAISERROR(N'CHECK FAILED: %d foreign keys in dw, expected 11', 16, 1, @fks);
ELSE IF @untrusted <> 0 RAISERROR(N'CHECK FAILED: %d untrusted/disabled foreign keys', 16, 1, @untrusted);
ELSE PRINT 'PASS: 11 trusted foreign keys';
GO

-- 5. Stopover modelling: transit 0 = no stopover; HasStopover agrees; at least 20 stopover rows.
DECLARE @inconsistent INT = (SELECT COUNT(*) FROM dw.Fact_FlightSegment
    WHERE HasStopover <> CASE WHEN TransitAirportKey = 0 THEN 0 ELSE 1 END);
IF @inconsistent <> 0 RAISERROR(N'CHECK FAILED: %d rows where HasStopover disagrees with TransitAirportKey', 16, 1, @inconsistent);
DECLARE @stop INT = (SELECT COUNT(*) FROM dw.Fact_FlightSegment WHERE HasStopover = 1);
IF @stop < 20 RAISERROR(N'CHECK FAILED: only %d rows with HasStopover = 1, need >= 20', 16, 1, @stop);
ELSE PRINT 'PASS: HasStopover = 1 on at least 20 rows';
GO

-- 6. At least 11 distinct airlines referenced by the fact (fact -> ticket -> airline).
DECLARE @air INT = (SELECT COUNT(DISTINCT t.AirlineKey)
    FROM dw.Fact_FlightSegment f JOIN dw.DimTicket t ON t.TicketKey = f.TicketKey);
IF @air < 11 RAISERROR(N'CHECK FAILED: only %d airlines referenced by the fact, need >= 11', 16, 1, @air);
ELSE PRINT 'PASS: at least 11 airlines referenced by the fact';
GO

-- 7. Chinese round trip: airline CA is the Chinese name for Air China (compared via code points so this script is encoding-proof).
DECLARE @expected NVARCHAR(20) = NCHAR(0x4E2D) + NCHAR(0x56FD) + NCHAR(0x56FD) + NCHAR(0x9645) + NCHAR(0x822A) + NCHAR(0x7A7A);
DECLARE @actual NVARCHAR(100) = (SELECT AirlineName FROM dw.DimAirline WHERE AirlineCode = N'CA');
IF @actual IS NULL OR @actual <> @expected COLLATE Latin1_General_BIN2
    RAISERROR(N'CHECK FAILED: Chinese round-trip, airline CA name does not match', 16, 1);
ELSE PRINT 'PASS: Chinese text round-trips (airline CA)';
GO

-- 8. Dimension rules: 'No stopover' row, spring festival flag (7 days), price inside its price range.
DECLARE @nostop INT = (SELECT COUNT(*) FROM dw.DimAirport WHERE AirportKey = 0 AND AirportName = N'No stopover');
IF @nostop <> 1 RAISERROR(N'CHECK FAILED: DimAirport row 0 ''No stopover'' missing', 16, 1);
DECLARE @sf INT = (SELECT COUNT(*) FROM dw.DimDate WHERE IsSpringFestival = 1
    AND FullDate BETWEEN '2021-02-11' AND '2021-02-17');
DECLARE @sfall INT = (SELECT COUNT(*) FROM dw.DimDate WHERE IsSpringFestival = 1);
IF @sf <> 7 OR @sfall <> 7 RAISERROR(N'CHECK FAILED: spring festival flag on %d dates (in range %d), expected 7', 16, 1, @sfall, @sf);
DECLARE @pr INT = (SELECT COUNT(*) FROM dw.Fact_FlightSegment f
    JOIN dw.DimPriceRange r ON r.PriceRangeKey = f.PriceRangeKey
    WHERE f.Price < r.MinPrice OR f.Price > r.MaxPrice);
IF @pr <> 0 RAISERROR(N'CHECK FAILED: %d fact rows with Price outside their price range', 16, 1, @pr);
ELSE PRINT 'PASS: No stopover row, spring festival flag, price ranges';
GO

-- 9. Derived date attributes (English names, sortable labels) agree with the date parts; spot check 2021-02-11.
DECLARE @bad INT = (SELECT COUNT(*) FROM dw.DimDate
    WHERE [Year] <> YEAR(FullDate) OR [Month] <> MONTH(FullDate) OR [Quarter] <> DATEPART(QUARTER, FullDate)
       OR YearMonth <> CONCAT([Year], N'-', RIGHT(N'0' + CAST([Month] AS NVARCHAR(2)), 2))
       OR QuarterName <> CONCAT([Year], N' Q', [Quarter])
       OR MonthName <> CHOOSE([Month], N'January', N'February', N'March', N'April', N'May', N'June', N'July',
                              N'August', N'September', N'October', N'November', N'December')
       OR DayName <> CHOOSE([DayOfWeek], N'Monday', N'Tuesday', N'Wednesday', N'Thursday', N'Friday',
                            N'Saturday', N'Sunday'));
DECLARE @spot INT = (SELECT COUNT(*) FROM dw.DimDate WHERE FullDate = '2021-02-11'
    AND MonthName = N'February' AND YearMonth = '2021-02' AND QuarterName = N'2021 Q1' AND DayName = N'Thursday');
IF @bad <> 0 RAISERROR(N'CHECK FAILED: %d DimDate rows with inconsistent name columns', 16, 1, @bad);
ELSE IF @spot <> 1 RAISERROR(N'CHECK FAILED: DimDate 2021-02-11 is not February / 2021-02 / 2021 Q1 / Thursday', 16, 1);
ELSE PRINT 'PASS: DimDate MonthName, YearMonth, QuarterName, DayName';
GO

-- 10. AgeBandOrder: one order per band, bands agree with Age, Unknown sorts last.
DECLARE @expected TABLE (AgeBand NVARCHAR(10), AgeBandOrder TINYINT, lo SMALLINT, hi SMALLINT);
INSERT @expected VALUES (N'<25', 1, -32768, 24), (N'25-34', 2, 25, 34), (N'35-44', 3, 35, 44),
                        (N'45-54', 4, 45, 54), (N'55-64', 5, 55, 64), (N'65+', 6, 65, 32767), (N'Unknown', 7, NULL, NULL);
DECLARE @wrong INT = (SELECT COUNT(*) FROM dw.DimPassenger p
    WHERE NOT EXISTS (SELECT 1 FROM @expected e
                      WHERE e.AgeBand = p.AgeBand COLLATE DATABASE_DEFAULT AND e.AgeBandOrder = p.AgeBandOrder
                        AND ((p.Age IS NULL AND e.lo IS NULL) OR p.Age BETWEEN e.lo AND e.hi)));
DECLARE @unknown_last INT = (SELECT COUNT(*) FROM dw.DimPassenger
    WHERE AgeBandOrder > (SELECT MIN(AgeBandOrder) FROM dw.DimPassenger WHERE AgeBand = N'Unknown')
       AND AgeBand <> N'Unknown');
IF @wrong <> 0 RAISERROR(N'CHECK FAILED: %d passengers whose (AgeBand, AgeBandOrder) disagrees with Age', 16, 1, @wrong);
ELSE IF @unknown_last <> 0 RAISERROR(N'CHECK FAILED: AgeBand Unknown does not sort last', 16, 1);
ELSE PRINT 'PASS: AgeBand / AgeBandOrder agree with Age (Unknown last)';
GO

PRINT 'ALL CHECKS PASSED';
GO
