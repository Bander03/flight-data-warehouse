-- Operation: Rank (Airline)
-- Question: How do the airlines rank by total ticket revenue?
-- Measure: Total Price
-- Ties: tied members share a rank (SQL RANK)
SELECT RANK() OVER (ORDER BY SUM(f.Price) DESC) AS [Rank],
       al.AirlineName AS Member,
       SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimTicket AS t ON t.TicketKey = f.TicketKey
JOIN dw.DimAirline AS al ON al.AirlineKey = t.AirlineKey
GROUP BY al.AirlineKey, al.AirlineName
ORDER BY [Rank], Member;
