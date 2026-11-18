-- Operation: Dice (Passenger FFP Tier x Cabin Class)
-- Question: How many different passengers of the top frequent-flyer tiers 5 and 6 flew in business class (C) and in economy class (Y)?
-- Measure: Distinct Passengers
SELECT CAST(p.FFPTier AS NVARCHAR(10)) + N' | ' + s.CabinClass AS Member,
       COUNT(DISTINCT f.PassengerKey) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimPassenger AS p ON p.PassengerKey = f.PassengerKey
JOIN dw.DimSeat AS s ON s.CabinKey = f.CabinKey
WHERE p.FFPTier IN (5, 6)
  AND s.CabinClass IN ('C', 'Y')
GROUP BY p.FFPTier, s.CabinClass
ORDER BY Member;
