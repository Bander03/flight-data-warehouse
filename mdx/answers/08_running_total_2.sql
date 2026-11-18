-- Operation: Running total (Arrival Date: Month)
-- Question: How many segments have arrived cumulatively by the end of each month of 2021?
-- Measure: Segment Count
WITH m AS (
    SELECT d.YearMonth, d.MonthName, SUM(f.SegmentCount) AS v
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimDate AS d ON d.DateKey = f.ArrivalDateKey
    GROUP BY d.YearMonth, d.MonthName
)
SELECT MonthName AS Member,
       SUM(v) OVER (ORDER BY YearMonth ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS Value
FROM m
ORDER BY YearMonth;
