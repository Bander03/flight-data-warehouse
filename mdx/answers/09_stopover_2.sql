-- Operation: Stopover analysis (Transit Airport: stopover vs direct)
-- Question: Is the average ticket price of segments with a stopover higher than that of direct segments?
-- Measure: Average Price
-- Members: 'No stopover' = [Transit Airport].[Geography].[Airport].&[0] (cube caption); 'With stopover' = all other transit airports together (a calculated member in MDX)
SELECT N'No stopover' AS Member,
       CAST(SUM(f.Price) * 1.0 / SUM(f.SegmentCount) AS DECIMAL(12, 2)) AS Value
FROM dw.Fact_FlightSegment AS f
WHERE f.TransitAirportKey = 0
UNION ALL
SELECT N'With stopover',
       CAST(SUM(f.Price) * 1.0 / SUM(f.SegmentCount) AS DECIMAL(12, 2))
FROM dw.Fact_FlightSegment AS f
WHERE f.TransitAirportKey <> 0            -- real transit airports only
ORDER BY Member;
