-- Operation: Roll up (Departure Date: Day to Month)
-- Question: What was the total ticket revenue per departure month when the daily figures are rolled up to months?
-- Measure: Total Price
SELECT d.MonthName AS Member, SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimDate AS d ON d.DateKey = f.DepartureDateKey
GROUP BY d.YearMonth, d.MonthName
ORDER BY d.YearMonth;      -- calendar order (month key), same as the MDX axis order
