-- Operation: Slice (Cabin: Cabin Class = Y)
-- Question: How much ticket revenue did each airline earn from economy-class (cabin Y) segments only?
-- Measure: Total Price
SELECT al.AirlineName AS Member, SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimTicket AS t ON t.TicketKey = f.TicketKey
JOIN dw.DimAirline AS al ON al.AirlineKey = t.AirlineKey
JOIN dw.DimSeat AS s ON s.CabinKey = f.CabinKey
WHERE s.CabinClass = 'Y'
GROUP BY al.AirlineKey, al.AirlineName
ORDER BY Member;
