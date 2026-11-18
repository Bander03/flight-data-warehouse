-- Operation: Top N (Flight: Flight No, N = 10)
-- Question: Which ten flight numbers have flown the most kilometres in total?
-- Measure: Total Mileage
-- Ties: none in the top 11 (10th = 21,360, 11th = 21,112), so the cut-off is unambiguous
WITH r AS (
    SELECT t.FlightNo AS Member, SUM(f.Mileage) AS Value
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimTicket AS t ON t.TicketKey = f.TicketKey
    GROUP BY t.FlightNo
)
SELECT TOP (10) ROW_NUMBER() OVER (ORDER BY Value DESC, Member) AS [Rank], Member, Value
FROM r
ORDER BY [Rank];
