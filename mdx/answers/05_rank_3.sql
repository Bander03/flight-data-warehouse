-- Operation: Rank (Price Range: Price Grade)
-- Question: How do the price grades (300-yuan price bands, grade g = 300g to 300(g+1)) rank by total ticket revenue?
-- Measure: Total Price
-- Ties: tied members share a rank (SQL RANK)
SELECT RANK() OVER (ORDER BY SUM(f.Price) DESC) AS [Rank],
       CAST(r.PriceGrade AS NVARCHAR(10)) AS Member,     -- cube caption of [Price Range].[Price Grade]: '0' .. '29'
       SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimPriceRange AS r ON r.PriceRangeKey = f.PriceRangeKey
GROUP BY r.PriceGrade
ORDER BY [Rank], Member;
