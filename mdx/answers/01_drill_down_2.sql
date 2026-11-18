-- Operation: Drill down (Departure Airport: Province to Airport)
-- Question: Which departure airports does Shanghai (province 上海) have, and what is the average ticket price of the segments leaving each of them?
-- Measure: Average Price
SELECT dep.AirportName AS Member,
       CAST(SUM(f.Price) * 1.0 / SUM(f.SegmentCount) AS DECIMAL(12, 2)) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS dep ON dep.AirportKey = f.DepartureAirportKey
WHERE dep.Province = N'上海'
GROUP BY dep.AirportKey, dep.AirportName
ORDER BY Member;
