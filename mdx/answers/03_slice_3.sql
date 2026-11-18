-- Operation: Slice (Departure Date: Is Spring Festival = Yes)
-- Question: What was the average ticket price per cabin class for segments that departed during the Spring Festival period (2021-02-11 to 2021-02-17)?
-- Measure: Average Price
SELECT s.CabinClass AS Member,
       CAST(SUM(f.Price) * 1.0 / SUM(f.SegmentCount) AS DECIMAL(12, 2)) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimDate AS d ON d.DateKey = f.DepartureDateKey
JOIN dw.DimSeat AS s ON s.CabinKey = f.CabinKey
WHERE d.IsSpringFestival = 1
GROUP BY s.CabinClass
ORDER BY Member;
