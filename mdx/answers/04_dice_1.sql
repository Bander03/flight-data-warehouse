-- Operation: Dice (Departure Airport province x Departure Date quarter)
-- Question: How many segments departed from Shanghai (上海) and Beijing (北京) in 2021 Q1 and 2021 Q2?
-- Measure: Segment Count
SELECT dep.Province + N' | ' + d.QuarterName AS Member, SUM(f.SegmentCount) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimAirport AS dep ON dep.AirportKey = f.DepartureAirportKey
JOIN dw.DimDate AS d ON d.DateKey = f.DepartureDateKey
WHERE dep.Province IN (N'上海', N'北京')
  AND d.QuarterName IN ('2021 Q1', '2021 Q2')
GROUP BY dep.Province, d.QuarterName
ORDER BY Member;
