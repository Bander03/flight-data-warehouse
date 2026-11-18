-- Operation: Rank (Departure Airport)
-- Question: Among the departure airports with at least 10 segments, how do they rank by total ticket revenue?
-- Measure: Total Price
-- Ties: tied members share a rank (SQL RANK)
SELECT RANK() OVER (ORDER BY SUM(f.Price) DESC) AS [Rank],
       dep.AirportName AS Member,
       SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS dep ON dep.AirportKey = f.DepartureAirportKey
GROUP BY dep.AirportKey, dep.AirportName
HAVING SUM(f.SegmentCount) >= 10
ORDER BY [Rank], Member;
