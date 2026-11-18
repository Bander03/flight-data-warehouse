-- Operation: Top N (Departure Airport x Landing Airport = route, N = 5)
-- Question: Which five routes (departure airport to landing airport) bring in the most ticket revenue?
-- Measure: Total Price
WITH r AS (
    SELECT dep.AirportName + N' | ' + land.AirportName AS Member, SUM(f.Price) AS Value
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimAirport AS dep ON dep.AirportKey = f.DepartureAirportKey
    JOIN dw.DimAirport AS land ON land.AirportKey = f.LandingAirportKey
    GROUP BY dep.AirportKey, dep.AirportName, land.AirportKey, land.AirportName
)
SELECT TOP (5) ROW_NUMBER() OVER (ORDER BY Value DESC, Member) AS [Rank], Member, Value
FROM r
ORDER BY [Rank];
