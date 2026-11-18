-- Operation: Moving average, 3 months (Departure Date: Month)
-- Question: What is the 3-month moving average of monthly ticket revenue by departure month (current and two previous months; the first two months use the months available)?
-- Measure: Total Price
WITH m AS (
    SELECT d.YearMonth, d.MonthName, SUM(f.Price) AS v
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimDate AS d ON d.DateKey = f.DepartureDateKey
    GROUP BY d.YearMonth, d.MonthName
)
SELECT MonthName AS Member,
       CAST(AVG(v * 1.0) OVER (ORDER BY YearMonth ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS DECIMAL(14, 2)) AS Value
FROM m
ORDER BY YearMonth;
