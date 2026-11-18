-- Operation: Running total (Departure Date: Month)
-- Question: What is the year-to-date ticket revenue at the end of each departure month of 2021?
-- Measure: Total Price
WITH m AS (
    SELECT d.YearMonth, d.MonthName, SUM(f.Price) AS v
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimDate AS d ON d.DateKey = f.DepartureDateKey
    GROUP BY d.YearMonth, d.MonthName
)
SELECT MonthName AS Member,
       SUM(v) OVER (ORDER BY YearMonth ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS Value
FROM m
ORDER BY YearMonth;
