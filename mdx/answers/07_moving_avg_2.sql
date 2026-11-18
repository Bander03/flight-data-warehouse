-- Operation: Moving average, 3 months (Arrival Date: Month)
-- Question: What is the 3-month moving average of the number of segments arriving per month (current and two previous months; the first two months use the months available)?
-- Measure: Segment Count
WITH m AS (
    SELECT d.YearMonth, d.MonthName, SUM(f.SegmentCount) AS v
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimDate AS d ON d.DateKey = f.ArrivalDateKey
    GROUP BY d.YearMonth, d.MonthName
)
SELECT MonthName AS Member,
       CAST(AVG(v * 1.0) OVER (ORDER BY YearMonth ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS DECIMAL(14, 2)) AS Value
FROM m
ORDER BY YearMonth;
