-- Operation: Slice (Departure Airport = Beijing Capital)
-- Question: Which landing airports are reached from Beijing Capital Airport (首都机场), and how many segments fly to each?
-- Measure: Segment Count
SELECT land.AirportName AS Member, SUM(f.SegmentCount) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS land ON land.AirportKey = f.LandingAirportKey
WHERE f.DepartureAirportKey = 74          -- 首都机场 (Beijing Capital, PEK)
GROUP BY land.AirportKey, land.AirportName
ORDER BY Member;
