-- Operation: Moving average, 7 days (Departure Date: Day)
-- Question: What is the 7-day moving average of the daily number of departing segments on each February 2021 day with departures (current and six previous calendar days, averaged over the days that have departures)?
-- Measure: Segment Count
-- Note: window = the current day and the six previous calendar days (2021-02-01 looks back to 2021-01-26);
-- only days with departures enter the average (MDX AVG skips empty cells); rows = February days with departures.
WITH d AS (
    SELECT dd.FullDate, SUM(f.SegmentCount) AS v
    FROM dw.Fact_FlightSegment AS f
    JOIN dw.DimDate AS dd ON dd.DateKey = f.DepartureDateKey
    GROUP BY dd.FullDate
)
SELECT CONVERT(CHAR(10), cur.FullDate, 120) AS Member,
       CAST(AVG(w.v * 1.0) AS DECIMAL(10, 4)) AS Value
FROM d AS cur
JOIN d AS w ON w.FullDate BETWEEN DATEADD(DAY, -6, cur.FullDate) AND cur.FullDate
WHERE cur.FullDate BETWEEN '2021-02-01' AND '2021-02-28'
GROUP BY cur.FullDate
ORDER BY Member;
