-- Operation: Dice (Plane Size Class x Cabin Class)
-- Question: How much ticket revenue did wide-body and narrow-body aircraft earn in business class (C) and in first class (F)?
-- Measure: Total Price
SELECT pl.SizeClass + N' | ' + s.CabinClass AS Member, SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimPlane AS pl ON pl.PlaneKey = f.PlaneKey
JOIN dw.DimSeat AS s ON s.CabinKey = f.CabinKey
WHERE pl.SizeClass IN ('Wide', 'Narrow')
  AND s.CabinClass IN ('C', 'F')
GROUP BY pl.SizeClass, s.CabinClass
ORDER BY Member;
