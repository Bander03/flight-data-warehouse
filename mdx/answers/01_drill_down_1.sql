-- Operation: Drill down (Departure Date: Quarter to Month)
-- Question: Which months make up 2021 Q1, and how many flight segments departed in each of them?
-- Measure: Segment Count
SELECT d.MonthName AS Member, SUM(f.SegmentCount) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimDate AS d ON d.DateKey = f.DepartureDateKey
WHERE d.QuarterName = '2021 Q1'
GROUP BY d.YearMonth, d.MonthName
ORDER BY d.YearMonth;      -- calendar order (month key), same as the MDX axis order
