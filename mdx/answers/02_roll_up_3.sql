-- Operation: Roll up (Flight: Flight No to Airline)
-- Question: How many different passengers flew with each airline when the flight-number figures are rolled up to airlines?
-- Measure: Distinct Passengers
SELECT al.AirlineName AS Member, COUNT(DISTINCT f.PassengerKey) AS Value
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimTicket AS t ON t.TicketKey = f.TicketKey
JOIN dw.DimAirline AS al ON al.AirlineKey = t.AirlineKey
GROUP BY al.AirlineKey, al.AirlineName
ORDER BY Member;
