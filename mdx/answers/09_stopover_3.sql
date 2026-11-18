-- Operation: Stopover analysis (Airline)
-- Question: What share of each airline's segments includes a stopover?
-- Measure: Stopover Share
SELECT al.AirlineName AS Member,
       CAST(SUM(CASE WHEN f.TransitAirportKey <> 0 THEN f.SegmentCount ELSE 0 END) * 1.0
            / SUM(f.SegmentCount) AS DECIMAL(8, 4)) AS Value     -- a stopover segment has a real transit airport (= HasStopover)
FROM dw.Fact_FlightSegment AS f
JOIN dw.DimTicket AS t ON t.TicketKey = f.TicketKey
JOIN dw.DimAirline AS al ON al.AirlineKey = t.AirlineKey
GROUP BY al.AirlineKey, al.AirlineName
ORDER BY Member;
