-- Operation: Drill down (Flight: Airline to Flight No)
-- Question: Which flight numbers does Air China (CA) operate in the data, and how much ticket revenue did each of them bring in?
-- Measure: Total Price
SELECT t.FlightNo AS Member, SUM(f.Price) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimTicket AS t ON t.TicketKey = f.TicketKey
JOIN dw.DimAirline AS al ON al.AirlineKey = t.AirlineKey
WHERE al.AirlineCode = 'CA'
GROUP BY t.FlightNo
ORDER BY Member;
