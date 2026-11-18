-- Operation: Stopover analysis (Transit Airport, top 5 hubs)
-- Question: Which five transit airports (hubs, 'No stopover' excluded) carry the most ticket revenue on segments with a stopover?
-- Measure: Total Price
SELECT TOP (5) tr.AirportName AS Member, SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS tr ON tr.AirportKey = f.TransitAirportKey
WHERE f.TransitAirportKey <> 0            -- exclude the 'No stopover' member
GROUP BY tr.AirportKey, tr.AirportName
ORDER BY Value DESC, Member;
