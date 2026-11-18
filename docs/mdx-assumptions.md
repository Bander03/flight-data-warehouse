# MDX assumptions verified on the real cube

The 28 statements in `mdx/` were written before `FlightCube` existed. Each line below was an assumption about member keys, captions or engine behaviour; Task 6 ran every statement on the processed cube (`tools/run_mdx.ps1`) and compared it with its T-SQL answer key (`tools/compare_results.py`). Result on 2026-11-13: **28 of 28 statements match**, with no change to any MDX statement. In the final review two statements were rewritten so that each operation has three genuinely different statements (`04_dice_3` now dices two different dimensions, `07_moving_avg_3` now works at day grain with a 7-day window); both were run on the cube and match their rewritten keys (rows marked **rewritten** below). Status column: **confirmed** = the statement ran and its rows and values equal the key; **changed** = something was adjusted (reason given).

## General (all statements)

| Assumption | Status |
|---|---|
| Member paths follow `docs/cube-spec.md` section 4: `&[...]` is the attribute **key** (Quarter key = `QuarterName`, Month key = `YearMonth`, Airport key = `AirportKey`, Province key = province text, Airline key = `AirlineKey`, Size Class key = `SizeClassOrder`, Age Band key = `AgeBandOrder`, Cabin Class key = code, Workplace key = `WorkplaceLabel`, Is Spring Festival key = `SpringFestivalKey`). | confirmed (every key path resolved; no statement returned an unknown-member error or an empty axis) |
| Attribute hierarchies without a user hierarchy are addressed as `[Dimension].[Attribute].[Attribute].Members` (level name = attribute name) to leave out the `All` member. | confirmed (03_slice_3, 05_rank_3, 06_top_n_3) |
| Row order: non-ranked keys order by `Member` text (SQL Server collation), MDX rows come in hierarchy order. For Chinese captions the two orders can differ, so non-ranked statements are matched by `Member`, not by position. Month series are in calendar (key) order in both. | confirmed: 20 of 22 unranked statements come back in the key's order; `03_slice_2` (landing airports) and `09_stopover_4` (routes) differ only in the order of Chinese airport names. The comparison ignores order for unranked statements. |
| `--` line comments in the `.mdx` files are accepted by SSAS. | confirmed (a raw file with its comment header runs unchanged); the runner strips `--` lines anyway. |
| Member captions equal the key's `Member` text, including Chinese airport, province and airline names (UTF-8 end to end). | confirmed (runner writes UTF-8 CSV; all Chinese members compare equal) |

## Per statement

| Statement | Assumption | Status |
|---|---|---|
| 01_drill_down_1 | `[Departure Date].[Calendar].[Quarter].&[2021 Q1]` exists (Quarter key = `QuarterName`); its children are the months January to March. | confirmed |
| 01_drill_down_2 | Province key `&[上海]` (Chinese key text resolves; collation matches). | confirmed (浦东机场, 虹桥机场) |
| 01_drill_down_3 | Air China (CA) is `AirlineKey` 1; `DESCENDANTS(member, 1)` returns the Flight No children. | confirmed (21 flight numbers) |
| 02_roll_up_1 | Day members are ordered by `DateKey`, so `GENERATE(... .Parent)` yields months in calendar order with duplicates removed. | confirmed |
| 02_roll_up_2 | `HIERARCHIZE` puts provinces in the Province attribute's name order. | confirmed (24 provinces; same order as the key) |
| 02_roll_up_3 | Level ordinal of `Airline` in `[Flight].[Airline Flight]` is 1 (All = 0). | confirmed (11 airlines) |
| 03_slice_1 | Cabin Class key `&[Y]`. | confirmed |
| 03_slice_2 | Beijing Capital (首都机场) is `AirportKey` 74. | confirmed (6 landing airports) |
| 03_slice_3 | `[Departure Date].[Is Spring Festival].&[1]` = Yes (TINYINT key `SpringFestivalKey`). | confirmed |
| 04_dice_1 | Province keys `&[上海]`, `&[北京]`; Quarter keys `&[2021 Q1]`, `&[2021 Q2]`; row captions `上海 \| 2021 Q1` etc. | confirmed |
| 04_dice_2 | Size Class keys: Narrow = `&[2]`, Wide = `&[3]`; Cabin keys `&[C]`, `&[F]`. | confirmed |
| 04_dice_3 | FFP Tier keys `&[5]`, `&[6]` with captions `5`, `6` (Passenger dimension); Cabin Class keys `&[C]`, `&[Y]` (Cabin dimension); `Distinct Passengers` is evaluated per cell. | **rewritten** (was FFP Tier x Age Band, two attributes of the one Passenger dimension, so not a multi-dimension dice); confirmed: 4 rows equal the key |
| 05_rank_1 | `RANK(member, set, measure)` gives tied members the same rank (as SQL `RANK`). | confirmed (no ties in the data; ranks 1..11 equal the key) |
| 05_rank_2 | The empty `No stopover` departure member is removed by `FILTER(... >= 10)`. | confirmed (16 airports) |
| 05_rank_3 | Price Grade captions are `0`..`29`; tie order. | confirmed (28 grades; Rank, order and values equal the key, so no tie changed the order) |
| 06_top_n_1 | No tie at the 5th route; `NONEMPTY` reduces the 185 x 185 crossjoin first. | confirmed |
| 06_top_n_2 | `[Flight].[Airline Flight].[Flight No]` key = `FlightNo` (one member per flight number). | confirmed |
| 06_top_n_3 | Workplace key/caption `Unknown` is the NULL-workplace member (`&[Unknown]`); no tie at the 5th. | **changed (answer key)**: the cube's `WorkplaceLabel` is `ISNULL(RTRIM(Workplace, NCHAR(12288)), 'Unknown')` (trailing ideographic spaces stripped, see `docs/cube-spec.md` section 1), so the key now groups and labels by the same expression. The result was already equal before the change (only 1 fact row has such a workplace and it is not in the top 5); the change makes both sides define the member identically. |
| 07_moving_avg_1 | `LASTPERIODS(3, January)` returns only January (no 2020 months in `DimDate`); `AVG` skips empty cells. | confirmed |
| 07_moving_avg_2 | `month.Lag(2)` is NULL for January and February and `{NULL : member}` is an open-ended range from the first month. | confirmed |
| 07_moving_avg_3 | Day key = `DateKey` (2021-02-01 = `&[32]`, 2021-02-28 = `&[59]`), so `{&[32] : &[59]}` is the February day range; `LASTPERIODS(7, day)` crosses the month boundary (for 2021-02-01 it reaches back to 2021-01-26); `AVG` skips empty days. | **rewritten** (was a second `AVG(LASTPERIODS(3, month))` like 07_moving_avg_1); confirmed: 16 rows equal the key (compared to 4 decimals); an ad-hoc query for the empty day 2021-02-01 returned 4 = (6 + 2) / 2 from 2021-01-26 and 2021-01-27, so the window does cross into January |
| 08_running_total_1 | `PERIODSTODATE([Departure Date].[Calendar].[Year], month)` works without Time-type attribute settings. | confirmed |
| 08_running_total_2 | `OPENINGPERIOD(Month level, Year member)` returns January 2021. | confirmed |
| 08_running_total_3 | Month key `&[2021-01]` (`YearMonth`). | confirmed |
| 09_stopover_1 | `[Transit Airport].[Geography].[Airport].&[0]` is the `No stopover` member; no tie at the 5th hub. | confirmed |
| 09_stopover_2 | The real member `&[0]` has caption `No stopover`; the calculated member `With stopover` with `SOLVE_ORDER` 1 vs 10 on `Value` gives the ratio of the aggregated sums. | confirmed (2,227.33 vs 2,901.68) |
| 09_stopover_3 | Share = (Segment Count - Segment Count at transit `&[0]`) / Segment Count; airlines with 0 % stay on the axis with 0. | confirmed (compared to 4 decimals, the key's rounding) |
| 09_stopover_4 | A route qualifies when its tuple with transit `&[0]` is empty (`ISEMPTY`). | confirmed (14 routes) |
