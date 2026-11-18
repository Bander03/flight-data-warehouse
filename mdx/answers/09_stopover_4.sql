-- Operation: Stopover analysis (Departure x Landing Airport, all segments via a stopover)
-- Question: On which routes (departure airport to landing airport) does every segment make a stopover?
-- Measure: Segment Count
SELECT dep.AirportName + N' | ' + land.AirportName AS Member, SUM(f.SegmentCount) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS dep ON dep.AirportKey = f.DepartureAirportKey
JOIN dw.DimAirport AS land ON land.AirportKey = f.LandingAirportKey
GROUP BY dep.AirportKey, dep.AirportName, land.AirportKey, land.AirportName
HAVING MIN(CASE WHEN f.TransitAirportKey <> 0 THEN 1 ELSE 0 END) = 1   -- no direct segment on the route
ORDER BY Member;
