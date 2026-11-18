-- Operation: Roll up (Landing Airport: Airport to Province)
-- Question: How many kilometres were flown into each landing province when the airport figures are rolled up to provinces?
-- Measure: Total Mileage
SELECT land.Province AS Member, SUM(f.Mileage) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS land ON land.AirportKey = f.LandingAirportKey
GROUP BY land.Province
ORDER BY Member;
