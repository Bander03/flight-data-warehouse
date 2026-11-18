-- 98_independent_audit.sql: independent, read-only audit of the loaded warehouse (does not reuse any pipeline code).
-- It recomputes the geometry and the business rules of the design spec from the dw tables alone, and fails (severity 16,
-- so `sqlcmd -b` exits non-zero) when any violation count is not zero. Run after 04_load.sql:
--   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\98_independent_audit.sql
SET NOCOUNT ON;
SET QUOTED_IDENTIFIER ON;
USE FlightDW;
GO
-- Great-circle distance in km (haversine, R = 6371) between two airports, as an inline view of all airport pairs used.
IF OBJECT_ID('tempdb..#seg') IS NOT NULL DROP TABLE #seg;
SELECT f.SegmentID, f.Mileage, f.HasStopover, f.Price, f.PlaneKey, f.CabinKey, f.PriceRangeKey, f.PassengerKey, f.TicketKey,
       t.FlightNo, f.DepartureAirportKey AS dep, f.TransitAirportKey AS tra, f.LandingAirportKey AS lan,
       RADIANS(d.Latitude) AS p1, RADIANS(d.Longitude) AS l1,
       RADIANS(l.Latitude) AS p2, RADIANS(l.Longitude) AS l2,
       RADIANS(x.Latitude) AS p3, RADIANS(x.Longitude) AS l3
INTO #seg
FROM dw.Fact_FlightSegment f
JOIN dw.DimTicket  t ON t.TicketKey  = f.TicketKey
JOIN dw.DimAirport d ON d.AirportKey = f.DepartureAirportKey
JOIN dw.DimAirport l ON l.AirportKey = f.LandingAirportKey
LEFT JOIN dw.DimAirport x ON x.AirportKey = f.TransitAirportKey AND f.TransitAirportKey <> 0;
-- direct distance dep-lan, leg1 dep-tra, leg2 tra-lan
IF OBJECT_ID('tempdb..#geo') IS NOT NULL DROP TABLE #geo;
SELECT s.*,
   2*6371.0*ASIN(SQRT(POWER(SIN((p2-p1)/2),2)+COS(p1)*COS(p2)*POWER(SIN((l2-l1)/2),2))) AS direct_km,
   CASE WHEN tra<>0 THEN 2*6371.0*ASIN(SQRT(POWER(SIN((p3-p1)/2),2)+COS(p1)*COS(p3)*POWER(SIN((l3-l1)/2),2))) END AS leg1_km,
   CASE WHEN tra<>0 THEN 2*6371.0*ASIN(SQRT(POWER(SIN((p2-p3)/2),2)+COS(p3)*COS(p2)*POWER(SIN((l2-l3)/2),2))) END AS leg2_km
INTO #geo FROM #seg s;
GO
DECLARE @n INT;

-- 1. Mileage equals the great-circle distance (direct, or via the transit airport), within 2 km of rounding.
SELECT @n = COUNT(*) FROM #geo
 WHERE ABS(Mileage - CASE WHEN tra = 0 THEN direct_km ELSE leg1_km + leg2_km END) > 2;
IF @n <> 0 RAISERROR('AUDIT FAILED 1: %d rows whose Mileage is not the haversine distance', 16, 1, @n);
ELSE PRINT 'PASS: 1 mileage = haversine distance (all 600 rows)';

-- 2. HasStopover agrees with the transit key.
SELECT @n = COUNT(*) FROM #geo WHERE HasStopover <> CASE WHEN tra = 0 THEN 0 ELSE 1 END;
IF @n <> 0 RAISERROR('AUDIT FAILED 2: %d rows where HasStopover disagrees with TransitAirportKey', 16, 1, @n);
ELSE PRINT 'PASS: 2 HasStopover = (transit key <> 0)';

-- 3. Stopover plausibility: differs from both ends, route >= 900 km, >= 150 km from each end, detour <= 25 %.
SELECT @n = COUNT(*) FROM #geo
 WHERE tra <> 0 AND (tra IN (dep, lan) OR direct_km < 900 OR leg1_km < 150 OR leg2_km < 150
                     OR leg1_km + leg2_km > 1.25 * direct_km + 0.001);
IF @n <> 0 RAISERROR('AUDIT FAILED 3: %d stopover rows break the geometric rules', 16, 1, @n);
ELSE PRINT 'PASS: 3 every stopover is geometrically plausible';

-- 4. Departure differs from landing in every row.
SELECT @n = COUNT(*) FROM #geo WHERE dep = lan;
IF @n <> 0 RAISERROR('AUDIT FAILED 4: %d rows with departure = landing', 16, 1, @n);
ELSE PRINT 'PASS: 4 departure <> landing';

-- 5. A flight number has exactly one route and one aircraft.
SELECT @n = COUNT(*) FROM (SELECT FlightNo FROM #geo GROUP BY FlightNo
                            HAVING COUNT(DISTINCT CONCAT(dep, '-', tra, '-', lan)) > 1) x;
IF @n <> 0 RAISERROR('AUDIT FAILED 5a: %d flight numbers with more than one route', 16, 1, @n);
ELSE PRINT 'PASS: 5a one route per flight number';
SELECT @n = COUNT(*) FROM (SELECT FlightNo FROM #geo GROUP BY FlightNo HAVING COUNT(DISTINCT PlaneKey) > 1) x;
IF @n <> 0 RAISERROR('AUDIT FAILED 5b: %d flight numbers with more than one aircraft', 16, 1, @n);
ELSE PRINT 'PASS: 5b one aircraft per flight number';

-- 6. Departure and arrival dates come from the ticket's times.
SELECT @n = COUNT(*) FROM dw.Fact_FlightSegment f
 JOIN dw.DimTicket t ON t.TicketKey = f.TicketKey
 JOIN dw.DimDate dd ON dd.DateKey = f.DepartureDateKey
 JOIN dw.DimDate ad ON ad.DateKey = f.ArrivalDateKey
 WHERE dd.FullDate <> CAST(t.DepartureTime AS DATE) OR ad.FullDate <> CAST(t.ArrivalTime AS DATE)
    OR ad.FullDate < dd.FullDate;
IF @n <> 0 RAISERROR('AUDIT FAILED 6: %d rows whose date keys disagree with the ticket times', 16, 1, @n);
ELSE PRINT 'PASS: 6 date keys = ticket dates, arrival >= departure';

-- 7. Price lies in its price range, is positive, and Rate is in (0, 1].
SELECT @n = COUNT(*) FROM dw.Fact_FlightSegment f JOIN dw.DimPriceRange p ON p.PriceRangeKey = f.PriceRangeKey
 WHERE f.Price < p.MinPrice OR f.Price > p.MaxPrice OR f.Price <= 0 OR f.Rate <= 0 OR f.Rate > 1;
IF @n <> 0 RAISERROR('AUDIT FAILED 7: %d rows with price or rate out of range', 16, 1, @n);
ELSE PRINT 'PASS: 7 price in range, rate in (0, 1]';

-- 8. First and business cabins only on aircraft with at least 100 seats.
SELECT @n = COUNT(*) FROM dw.Fact_FlightSegment f
 JOIN dw.DimPlane p ON p.PlaneKey = f.PlaneKey JOIN dw.DimSeat s ON s.CabinKey = f.CabinKey
 WHERE s.CabinClass IN (N'F', N'C') AND p.SeatCount < 100;
IF @n <> 0 RAISERROR('AUDIT FAILED 8: %d premium-cabin rows on small aircraft', 16, 1, @n);
ELSE PRINT 'PASS: 8 premium cabins only on aircraft with >= 100 seats';

-- 9. Airline of a ticket equals the two-letter prefix of its flight number.
SELECT @n = COUNT(*) FROM dw.DimTicket t JOIN dw.DimAirline a ON a.AirlineKey = t.AirlineKey
 WHERE LEFT(t.FlightNo, 2) <> a.AirlineCode;
IF @n <> 0 RAISERROR('AUDIT FAILED 9: %d tickets whose airline differs from the flight-number prefix', 16, 1, @n);
ELSE PRINT 'PASS: 9 airline = flight-number prefix (all tickets)';

-- 10. Supplemented tickets are flagged and the original tickets are all present: 568,917 + 240.
SELECT @n = COUNT(*) FROM dw.DimTicket WHERE IsSupplemented = 0;
IF @n <> 568917 RAISERROR('AUDIT FAILED 10a: %d original tickets, expected 568917', 16, 1, @n);
ELSE PRINT 'PASS: 10a 568917 original tickets';
SELECT @n = COUNT(*) FROM dw.DimTicket WHERE IsSupplemented = 1;
IF @n <> 240 RAISERROR('AUDIT FAILED 10b: %d supplemented tickets, expected 240', 16, 1, @n);
ELSE PRINT 'PASS: 10b 240 supplemented tickets, all flagged';

-- 11. Date dimension: 365 consecutive days of 2021, Spring Festival = 7 days.
SELECT @n = COUNT(*) FROM dw.DimDate;
IF @n <> 365 RAISERROR('AUDIT FAILED 11a: %d dates, expected 365', 16, 1, @n);
ELSE PRINT 'PASS: 11a 365 dates';
SELECT @n = COUNT(*) FROM dw.DimDate WHERE FullDate < '2021-01-01' OR FullDate > '2021-12-31';
IF @n <> 0 RAISERROR('AUDIT FAILED 11b: %d dates outside 2021', 16, 1, @n);
ELSE PRINT 'PASS: 11b all dates inside 2021';
SELECT @n = COUNT(*) FROM dw.DimDate WHERE IsSpringFestival = 1;
IF @n <> 7 RAISERROR('AUDIT FAILED 11c: %d spring-festival days, expected 7', 16, 1, @n);
ELSE PRINT 'PASS: 11c 7 spring-festival days';

-- 12. The airport 0 is the only placeholder; every airport used in the fact has coordinates.
SELECT @n = COUNT(*) FROM dw.DimAirport WHERE AirportKey = 0 AND AirportName = N'No stopover';
IF @n <> 1 RAISERROR('AUDIT FAILED 12a: the No stopover row is missing or duplicated', 16, 1);
ELSE PRINT 'PASS: 12a one No stopover row (key 0)';
SELECT @n = COUNT(*) FROM dw.DimAirport a WHERE a.AirportKey <> 0 AND (a.Latitude IS NULL OR a.Longitude IS NULL)
  AND (a.AirportKey IN (SELECT DepartureAirportKey FROM dw.Fact_FlightSegment)
    OR a.AirportKey IN (SELECT LandingAirportKey FROM dw.Fact_FlightSegment)
    OR a.AirportKey IN (SELECT TransitAirportKey FROM dw.Fact_FlightSegment));
IF @n <> 0 RAISERROR('AUDIT FAILED 12b: %d used airports without coordinates', 16, 1, @n);
ELSE PRINT 'PASS: 12b every used airport has coordinates';

-- 13. Passenger and ticket: nobody is on the same ticket twice; every passenger exists exactly once.
SELECT @n = COUNT(*) FROM (SELECT PassengerKey, TicketKey FROM dw.Fact_FlightSegment
                           GROUP BY PassengerKey, TicketKey HAVING COUNT(*) > 1) x;
IF @n <> 0 RAISERROR('AUDIT FAILED 13: %d passengers on the same ticket twice', 16, 1, @n);
ELSE PRINT 'PASS: 13 no passenger twice on one ticket';

-- 14. Grand totals fixed by the project: 600 segments, 95 with a stopover, total price 1,400,460, 599 passengers.
SELECT @n = COUNT(*) FROM dw.Fact_FlightSegment;
IF @n <> 600 RAISERROR('AUDIT FAILED 14a: %d fact rows', 16, 1, @n); ELSE PRINT 'PASS: 14a 600 fact rows';
SELECT @n = SUM(CAST(HasStopover AS INT)) FROM dw.Fact_FlightSegment;
IF @n <> 95 RAISERROR('AUDIT FAILED 14b: %d stopover rows', 16, 1, @n); ELSE PRINT 'PASS: 14b 95 stopover rows';
SELECT @n = SUM(Price) FROM dw.Fact_FlightSegment;
IF @n <> 1400460 RAISERROR('AUDIT FAILED 14c: total price %d', 16, 1, @n); ELSE PRINT 'PASS: 14c total price 1400460';
SELECT @n = COUNT(DISTINCT PassengerKey) FROM dw.Fact_FlightSegment;
IF @n <> 599 RAISERROR('AUDIT FAILED 14d: %d distinct passengers', 16, 1, @n); ELSE PRINT 'PASS: 14d 599 distinct passengers';
GO
PRINT 'ALL AUDIT CHECKS PASSED';
GO
