## 3.3 Functions: OLAP analysis with MDX

All statements are written in MDX [5] and run on the cube `FlightCube` (Analysis Services, Multidimensional); every result was checked against an independent T-SQL query on the warehouse (28 of 28 match, `tools/compare_results.py`). To keep this section within the length the course guide describes, one statement per OLAP operation is shown here in full (business meaning, MDX, result table next to its screenshot, short analysis); the other statements of the same operation follow with their question, their screenshots and one analysis that gives the exact values. The complete text of all 28 MDX statements is given in Appendix B. SSMS shows the values with the number format of the cube (for example 69.5 is displayed as 70), while the result tables and the analysis text give the exact values.

{{keep}}
### 3.3.1 Drill down

Drill down moves from a coarse level of a hierarchy to its finer level, for example from a province to its airports.

**01_drill_down_1.** Which months make up 2021 Q1, and how many flight segments departed in each of them?

*Meaning.* The first quarter of 2021 is split into its three months to see how traffic builds up during the quarter.

```
WITH MEMBER [Measures].[Value] AS [Measures].[Segment Count]
SELECT {[Measures].[Value]} ON COLUMNS,
  NON EMPTY [Departure Date].[Calendar].[Quarter].&[2021 Q1].Children ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `01_drill_down_1` (3 rows).
| Member | Value |
|---|---|
| January | 61 |
| February | 78 |
| March | 91 |
{{col}}
![Figure N SSMS: `01_drill_down_1`.](../figures/M01.1.jpg)
{{end-row}}

*Result.* January had 61 segments, February 78 and March 91, so traffic grew from month to month during the quarter.
{{end-keep}}

{{keep}}
**01_drill_down_2.** Which departure airports does Shanghai (province 上海) have, and what is the average ticket price of the segments leaving each of them? **01_drill_down_3.** Which flight numbers does Air China (CA) operate in the data, and how much ticket revenue did each of them bring in?

{{row 8 8}}
![Figure N SSMS: `01_drill_down_2`.](../figures/M01.2.jpg)
{{col}}
![Figure N SSMS: `01_drill_down_3`.](../figures/M01.3.jpg)
{{end-row}}

*Result.* Shanghai has two departure airports: Hongqiao (虹桥机场) averages 2,519.87 and Pudong (浦东机场) 2,133.93. Air China operates 21 flight numbers; CA1517 earns the most with 42,740 and the smallest, CA1886, earns 4,940.
{{end-keep}}

{{keep}}
### 3.3.2 Roll up

Roll up is the opposite: figures of a fine level are aggregated to the coarser level above it.

**02_roll_up_1.** What was the total ticket revenue per departure month when the daily figures are rolled up to months?

*Meaning.* Daily figures are aggregated to months to see the seasonal profile of revenue.

```
WITH MEMBER [Measures].[Value] AS [Measures].[Total Price]
SELECT {[Measures].[Value]} ON COLUMNS,
  GENERATE(NONEMPTY([Departure Date].[Calendar].[Day].Members, [Measures].[Segment Count]),
           {[Departure Date].[Calendar].CurrentMember.Parent}) ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `02_roll_up_1` (first 6 of 8 rows).
| Member | Value |
|---|---|
| January | 149,130 |
| February | 213,460 |
| March | 197,430 |
| April | 187,620 |
| May | 170,870 |
| June | 154,470 |
{{col}}
![Figure N SSMS: `02_roll_up_1`.](../figures/M02.1.jpg)
{{end-row}}

*Result.* Monthly revenue peaks in February with 213,460 and is lowest in August with 145,970; the eight months add up to the total revenue of 1,400,460.
{{end-keep}}

{{keep}}
**02_roll_up_2.** How many kilometres were flown into each landing province when the airport figures are rolled up to provinces? **02_roll_up_3.** How many different passengers flew with each airline when the flight-number figures are rolled up to airlines?

{{row 8 8}}
![Figure N SSMS: `02_roll_up_2`.](../figures/M02.2.jpg)
{{col}}
![Figure N SSMS: `02_roll_up_3`.](../figures/M02.3.jpg)
{{end-row}}

*Result.* Shanghai (上海) receives the most kilometres of the 24 provinces, 344,106. China Eastern Airlines (中国东方航空) carried the most distinct passengers of the 11 airlines, 300, against 2 each for the two smallest.
{{end-keep}}

{{keep}}
### 3.3.3 Slice

A slice fixes one member of one dimension and shows the rest of the cube for that member only.

**03_slice_1.** How much ticket revenue did each airline earn from economy-class (cabin Y) segments only?

*Meaning.* Only economy-class segments are kept (slice on the cabin class Y) and the revenue is shown per airline.

```
WITH MEMBER [Measures].[Value] AS [Measures].[Total Price]
SELECT {[Measures].[Value]} ON COLUMNS,
  NON EMPTY [Flight].[Airline Flight].[Airline].Members ON ROWS
FROM [FlightCube]
WHERE ([Cabin].[Cabin Class].&[Y])
```

{{row 6.6 9.4}}
**Table N** Result of `03_slice_1` (first 6 of 11 rows).
| Member | Value |
|---|---|
| 上海航空 | 22,490 |
| 中国东方航空 | 273,130 |
| 中国南方航空 | 11,220 |
| 中国国际航空 | 142,620 |
| 厦门航空 | 3,490 |
| 吉祥航空 | 7,090 |
{{col}}
![Figure N SSMS: `03_slice_1`.](../figures/M03.1.jpg)
{{end-row}}

*Result.* In economy class China Eastern Airlines earns 273,130, Air China 142,620 and Hainan Airlines 48,690; each of the remaining eight airlines earns less than 23,000.
{{end-keep}}

{{keep}}
**03_slice_2.** Which landing airports are reached from Beijing Capital Airport (首都机场), and how many segments fly to each? **03_slice_3.** What was the average ticket price per cabin class for segments that departed during the Spring Festival period (2021-02-11 to 2021-02-17)?

{{row 8 8}}
![Figure N SSMS: `03_slice_2`.](../figures/M03.2.jpg)
{{col}}
![Figure N SSMS: `03_slice_3`.](../figures/M03.3.jpg)
{{end-row}}

*Result.* Beijing Capital has six destinations; Qingyang (庆阳机场) receives the most, 15. During the Spring Festival week the average ticket price is 1,306.84 in economy (Y), 5,777.50 in business (C) and 7,045.00 in first class (F).
{{end-keep}}

{{keep}}
### 3.3.4 Dice

A dice selects a sub-cube by restricting several dimensions at the same time.

**04_dice_1.** How many segments departed from Shanghai (上海) and Beijing (北京) in 2021 Q1 and 2021 Q2?

*Meaning.* The dice selects two provinces and two quarters at once to compare departures from Shanghai and Beijing.

```
WITH MEMBER [Measures].[Value] AS [Measures].[Segment Count]
SELECT {[Measures].[Value]} ON COLUMNS,
  NON EMPTY {[Departure Airport].[Geography].[Province].&[上海],
             [Departure Airport].[Geography].[Province].&[北京]}
          * {[Departure Date].[Calendar].[Quarter].&[2021 Q1],
             [Departure Date].[Calendar].[Quarter].&[2021 Q2]} ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `04_dice_1` (4 rows).
| Member | Value |
|---|---|
| 上海 \| 2021 Q1 | 73 |
| 上海 \| 2021 Q2 | 63 |
| 北京 \| 2021 Q1 | 14 |
| 北京 \| 2021 Q2 | 11 |
{{col}}
![Figure N SSMS: `04_dice_1`.](../figures/M04.1.jpg)
{{end-row}}

*Result.* Shanghai had 73 departures in the first quarter and 63 in the second, Beijing only 14 and 11.
{{end-keep}}

{{keep}}
**04_dice_2.** How much ticket revenue did wide-body and narrow-body aircraft earn in business class (C) and in first class (F)? **04_dice_3.** How many different passengers of the top frequent-flyer tiers 5 and 6 flew in business class (C) and in economy class (Y)?

{{row 8 8}}
![Figure N SSMS: `04_dice_2`.](../figures/M04.2.jpg)
{{col}}
![Figure N SSMS: `04_dice_3`.](../figures/M04.3.jpg)
{{end-row}}

*Result.* Wide-body aircraft earn more than narrow-body in both business (402,670 vs 206,710) and first class (196,570 vs 73,670). Top-tier frequent flyers mostly fly economy: 21 of tier 5 and 9 of tier 6, against 4 and 3 in business.
{{end-keep}}

{{keep}}
### 3.3.5 Rank

Rank orders the members of a level by a measure and shows their position.

**05_rank_1.** How do the airlines rank by total ticket revenue?

*Meaning.* Airlines are ranked by total ticket revenue.

```
WITH SET [Ranked Airlines] AS
  ORDER(NONEMPTY([Flight].[Airline Flight].[Airline].Members, [Measures].[Total Price]), [Measures].[Total Price], BDESC)
MEMBER [Measures].[Value] AS [Measures].[Total Price]
MEMBER [Measures].[Rank] AS RANK([Flight].[Airline Flight].CurrentMember, [Ranked Airlines], [Measures].[Total Price])
SELECT {[Measures].[Rank], [Measures].[Value]} ON COLUMNS,
  [Ranked Airlines] ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `05_rank_1` (first 6 of 11 rows).
| Rank | Member | Value |
|---|---|---|
| 1 | 中国东方航空 | 699,600 |
| 2 | 中国国际航空 | 409,590 |
| 3 | 海南航空 | 151,680 |
| 4 | 上海航空 | 56,430 |
| 5 | 吉祥航空 | 38,720 |
| 6 | 中国南方航空 | 11,220 |
{{col}}
![Figure N SSMS: `05_rank_1`.](../figures/M05.1.jpg)
{{end-row}}

*Result.* China Eastern Airlines ranks first with 699,600, Air China second with 409,590 and Hainan Airlines third with 151,680; Spring Airlines (春秋航空) is last, 11th, with 2,390.
{{end-keep}}

{{keep}}
**05_rank_2.** Among the departure airports with at least 10 segments, how do they rank by total ticket revenue? **05_rank_3.** How do the price grades (300-yuan price bands, grade g = 300g to 300(g+1)) rank by total ticket revenue?

{{row 8 8}}
![Figure N SSMS: `05_rank_2`.](../figures/M05.2.jpg)
{{col}}
![Figure N SSMS: `05_rank_3`.](../figures/M05.3.jpg)
{{end-row}}

*Result.* Of the 16 busy airports, Hongqiao ranks first with 199,070. Of the 28 price grades used, grade 5 (1,500 to 1,800 yuan) brings the most revenue, 188,920.
{{end-keep}}

{{keep}}
### 3.3.6 Top N

Top N keeps only the N members with the highest value of a measure.

**06_top_n_1.** Which five routes (departure airport to landing airport) bring in the most ticket revenue?

*Meaning.* A route is a departure and a landing airport; the five most valuable routes are listed.

```
WITH SET [Top Routes] AS
  TOPCOUNT(NONEMPTY([Departure Airport].[Geography].[Airport].Members
                    * [Landing Airport].[Geography].[Airport].Members, [Measures].[Total Price]),
           5, [Measures].[Total Price])
MEMBER [Measures].[Value] AS [Measures].[Total Price]
MEMBER [Measures].[Rank] AS
  RANK(([Departure Airport].[Geography].CurrentMember, [Landing Airport].[Geography].CurrentMember), [Top Routes])
SELECT {[Measures].[Rank], [Measures].[Value]} ON COLUMNS,
  [Top Routes] ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `06_top_n_1` (5 rows).
| Rank | Member | Value |
|---|---|---|
| 1 | 三家子机场 \| 双流机场 | 42,740 |
| 2 | 富蕴机场 \| 虹桥机场 | 41,160 |
| 3 | 塔城机场 \| 虹桥机场 | 33,390 |
| 4 | 首都机场 \| 嘉峪关机场 | 32,790 |
| 5 | 浦东机场 \| 玉树巴塘机场 | 32,710 |
{{col}}
![Figure N SSMS: `06_top_n_1`.](../figures/M06.1.jpg)
{{end-row}}

*Result.* Sanjiazi (三家子机场) to Shuangliu leads with 42,740, then Fuyun (富蕴机场) to Hongqiao with 41,160; fifth is Pudong to Yushu Batang with 32,710.
{{end-keep}}

{{keep}}
**06_top_n_2.** Which ten flight numbers have flown the most kilometres in total? **06_top_n_3.** Which five passenger workplaces account for the most segments (workplace 'Unknown' excluded)?

{{row 8 8}}
![Figure N SSMS: `06_top_n_2`.](../figures/M06.2.jpg)
{{col}}
![Figure N SSMS: `06_top_n_3`.](../figures/M06.3.jpg)
{{end-row}}

*Result.* MU5112 flew the most kilometres, 47,606. Guangzhou (中国广东广州) is the leading workplace with 74 segments.
{{end-keep}}

{{keep}}
### 3.3.7 Moving average

A moving average smooths a series: each value is the mean of the current period and the periods just before it. The first two statements use a 3-month window on monthly figures (the first two months use the months available); the third uses a 7-day window on daily figures.

**07_moving_avg_1.** What is the 3-month moving average of monthly ticket revenue by departure month (current and two previous months; the first two months use the months available)?

*Meaning.* The 3-month moving average of the monthly revenue smooths the month-to-month variation.

```
WITH MEMBER [Measures].[Value] AS
  AVG(LASTPERIODS(3, [Departure Date].[Calendar].CurrentMember), [Measures].[Total Price])
SELECT {[Measures].[Value]} ON COLUMNS,
  NONEMPTY([Departure Date].[Calendar].[Month].Members, [Measures].[Segment Count]) ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `07_moving_avg_1` (first 6 of 8 rows).
| Member | Value |
|---|---|
| January | 149,130 |
| February | 181,295 |
| March | 186,673.3333 |
| April | 199,503.3333 |
| May | 185,306.6667 |
| June | 170,986.6667 |
{{col}}
![Figure N SSMS: `07_moving_avg_1`.](../figures/M07.1.jpg)
{{end-row}}

*Result.* The smoothed revenue rises from 149,130 in January to 199,503.33 in April and then declines to 160,650 in August.
{{end-keep}}

{{keep}}
**07_moving_avg_2.** What is the 3-month moving average of the number of segments arriving per month (arrival-date role; current and two previous months)? **07_moving_avg_3.** What is the 7-day moving average of the daily number of departing segments on each February 2021 day with departures?

{{row 8 8}}
![Figure N SSMS: `07_moving_avg_2`.](../figures/M07.2.jpg)
{{col}}
![Figure N SSMS: `07_moving_avg_3`.](../figures/M07.3.jpg)
{{end-row}}

*Result.* The arrival-count average peaks in April at 83.67. The daily departures average starts at 2 in early February, rises to 6 by 18 February (inside the Spring Festival week, 2021-02-11 to 2021-02-17), dips back to 3 by 22 February, then rises again to its highest value, 7, on 28 February.
{{end-keep}}

{{keep}}
### 3.3.8 Running total

A running total (year to date) accumulates a monthly measure from January to the current month.

**08_running_total_1.** What is the year-to-date ticket revenue at the end of each departure month of 2021?

*Meaning.* The running total accumulates the monthly revenue from January (year to date).

```
WITH MEMBER [Measures].[Value] AS
  SUM(PERIODSTODATE([Departure Date].[Calendar].[Year], [Departure Date].[Calendar].CurrentMember),
      [Measures].[Total Price])
SELECT {[Measures].[Value]} ON COLUMNS,
  NONEMPTY([Departure Date].[Calendar].[Month].Members, [Measures].[Segment Count]) ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `08_running_total_1` (first 6 of 8 rows).
| Member | Value |
|---|---|
| January | 149,130 |
| February | 362,590 |
| March | 560,020 |
| April | 747,640 |
| May | 918,510 |
| June | 1,072,980 |
{{col}}
![Figure N SSMS: `08_running_total_1`.](../figures/M08.1.jpg)
{{end-row}}

*Result.* Cumulative revenue reaches 362,590 at the end of February, 918,510 in May and 1,400,460 in August, the total revenue of all 600 segments.
{{end-keep}}

{{keep}}
**08_running_total_2.** How many segments have arrived cumulatively by the end of each month of 2021? **08_running_total_3.** How many segments with a stopover have departed cumulatively by the end of each month of 2021?

{{row 8 8}}
![Figure N SSMS: `08_running_total_2`.](../figures/M08.2.jpg)
{{col}}
![Figure N SSMS: `08_running_total_3`.](../figures/M08.3.jpg)
{{end-row}}

*Result.* Arrived segments accumulate from 61 in January to 600 in August, equal to all fact rows. Cumulative stopover segments rise from 9 in January to 95 in August, with the largest monthly jump in March.
{{end-keep}}

{{keep}}
### 3.3.9 Stopover analysis

These statements analyse flights with a stopover, using the transit-airport role of the airport dimension; the member 'No stopover' is excluded wherever hubs are ranked.

**09_stopover_2.** Is the average ticket price of segments with a stopover higher than that of direct segments?

*Meaning.* Comparing segments with and without a stopover shows whether indirect travel costs more on average. 'No stopover' is a real member of the Transit Airport dimension; 'With stopover' is a calculated member aggregating all other transit airports, so the ratio uses the aggregated sums.

```
WITH MEMBER [Transit Airport].[Geography].[With stopover] AS
  AGGREGATE(EXCEPT([Transit Airport].[Geography].[Airport].Members,
                   {[Transit Airport].[Geography].[Airport].&[0]})), SOLVE_ORDER = 1
MEMBER [Measures].[Value] AS
  IIF([Measures].[Segment Count] = 0, NULL, [Measures].[Total Price] / [Measures].[Segment Count]), SOLVE_ORDER = 10
SELECT {[Measures].[Value]} ON COLUMNS,
  {[Transit Airport].[Geography].[Airport].&[0], [Transit Airport].[Geography].[With stopover]} ON ROWS
FROM [FlightCube]
```

{{row 6.6 9.4}}
**Table N** Result of `09_stopover_2` (2 rows).
| Member | Value |
|---|---|
| No stopover | 2,227.3267 |
| With stopover | 2,901.6842 |
{{col}}
![Figure N SSMS: `09_stopover_2`.](../figures/M09.2.jpg)
{{end-row}}

*Result.* Segments with a stopover cost 2,901.68 on average, direct ones 2,227.33. Stopovers were only assigned to routes of at least 900 km (a preprocessing rule), so the groups differ in distance and the comparison is not like-for-like.
{{end-keep}}

{{keep}}
**09_stopover_1.** Which five transit airports (hubs, 'No stopover' excluded) carry the most ticket revenue on segments with a stopover? **09_stopover_3.** What share of each airline's segments includes a stopover? **09_stopover_4.** On which routes does every segment make a stopover?

{{row 8 8}}
![Figure N SSMS: `09_stopover_1`.](../figures/M09.1.jpg)
![Figure N SSMS: `09_stopover_3`.](../figures/M09.3.jpg)
{{col}}
![Figure N SSMS: `09_stopover_4`.](../figures/M09.4.jpg)
*Result.* Sanxia (三峡机场) is the top hub by stopover revenue, 45,110. Air China has the highest stopover share among the large airlines, 0.3101, followed by China Eastern (0.1067) and Hainan Airlines (0.0923). 14 routes are flown only with a stopover; together they account for all 95 stopover segments, the largest being Pudong to Beijing Capital with 14 segments.
{{end-row}}
{{end-keep}}

### 3.3.10 Highlights and discussion of the results

**Role-playing dimensions.** The arrival-date role is used by the arrival statements (07_moving_avg_2 and 08_running_total_2) and the departure-date role by the others; the transit-airport role carries all stopover statements.

**Spring Festival.** The slice on the festival week (03_slice_3) is the analysis the course guide suggests for holiday traffic; in the data, first class costs more than business class, and business more than economy, during that week.

**Stopover versus direct.** Segments with a stopover cost more on average than direct ones (09_stopover_2), but stopovers were only assigned to routes of at least 900 km, so the two groups are not like-for-like and the statement does not separate a stopover effect from a distance effect. Only 14 routes are flown with a stopover (09_stopover_4), and they carry all 95 stopover segments.

**What the data cannot show.** Flight durations come from the source tickets and do not scale with distance, and passenger names are not unique, so no statement analyses duration or groups by name (see 'Known artefacts' in docs/DATA_FINDINGS.md).

**Verification.** Every statement was checked against an independent T-SQL query on the relational warehouse: all 28 results match (tools/compare_results.py). The complete text of all 28 MDX statements is given in Appendix B.
