-- Operation: Top N (Passenger: Workplace, N = 5)
-- Question: Which five passenger workplaces account for the most segments (workplace 'Unknown' excluded)?
-- Measure: Segment Count
-- Label: the cube's WorkplaceLabel, ISNULL(RTRIM(Workplace, NCHAR(12288)), 'Unknown') (trailing ideographic spaces stripped)
WITH r AS (
    SELECT ISNULL(RTRIM(p.Workplace, NCHAR(12288)), 'Unknown') AS Member, SUM(f.SegmentCount) AS Value
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimPassenger AS p ON p.PassengerKey = f.PassengerKey
    GROUP BY ISNULL(RTRIM(p.Workplace, NCHAR(12288)), 'Unknown')
)
SELECT TOP (5) ROW_NUMBER() OVER (ORDER BY Value DESC, Member) AS [Rank], Member, Value
FROM r
WHERE Member <> 'Unknown'                                   -- NULL workplaces are the 'Unknown' member in the cube
ORDER BY [Rank];
