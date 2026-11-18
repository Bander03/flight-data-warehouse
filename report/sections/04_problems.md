# 4. Main problems encountered and solutions

## Bander Sidiq Mahmood

My part was the design of the star schema, the warehouse scripts, the Analysis Services cube, the SSIS package and putting the pieces of the group together. Most of the problems I met came from the tools and from the data, and I solved them in the following way.

**The software for MDX was missing.** SQL Server Express, which we already had, cannot run Analysis Services, so MDX was impossible on it. I installed SQL Server Developer edition with Analysis Services in Multidimensional mode as a second, named instance, so that the Express database stayed untouched. The first installer I tried (from the Windows package manager) was an old one that stops with the message that it is no longer supported; the current SQL Server 2025 installer worked. A second blocker was that the Visual Studio extensions for Analysis Services would not install on the first try because the Visual Studio installation was incomplete; after it was repaired I decided not to depend on the graphical designer at all and wrote a Python script that generates the whole cube definition (data source, views, dimensions, measures, calculated members) as one XMLA file. The result is repeatable: the cube can be deleted and rebuilt with one command.

**The cube could not read the warehouse.** Analysis Services reads the database with its own service account, which had no permission on the Express instance, so processing failed with a login error. I added a small read-only permission script (`db_datareader` on FlightDW and nothing else). I also learned that it must be run again after every rebuild of the warehouse, because the rebuild drops the database user; this is now written into the README and into the SSIS package as its last task.

**Processing failed because of an invisible character.** Processing the cube stopped with the error that an attribute key cannot be found. The cause was the workplace column: 70 passenger records (30 different texts) ended with an ideographic space (a Chinese full-width blank). SQL Server treats a value with and without trailing blanks as equal, Analysis Services does not, so the same workplace appeared as two members. I traced the error back to these values and fixed it with a named calculation that removes this character, and I changed the matching SQL answer query to group the same way.

**Proving that the MDX results are right.** An MDX result that merely looks plausible is not enough. For each of the 28 statements I wrote an independent T-SQL query on the warehouse and a script that runs the MDX, saves the result and compares both numerically; at the end all 28 match. The comparison also exposed how ties in ranked lists are handled; I corrected the answer queries so that both sides break ties in the same way, instead of loosening the comparison.

**The SSIS package.** An Execute SQL Task cannot run our scripts, because they use `GO` and sqlcmd variables, so each task of the package calls `sqlcmd` instead. Visual Studio would not open the package project that I had written by hand, so I ran the package with the `dtexec` tool, which completed with all seven tasks successful, and drew the control-flow figure from the package file.

**Coordinating the group.** The three of us could not all edit one Word file without overwriting each other, so I put the project in a private GitHub repository, kept the report as one text file per section, and made a script that builds the Word report; each member writes in their own section and I merge it.

## Yohannes Abate Ejita

This part covers the preprocessing and the validation of the fact table, the area I was assigned in the group. The source table could not be used as delivered, so my work consisted of finding out exactly what was wrong and repairing it in a way that stays consistent.

**The data broke the course rules in several ways.** The transit airport column was completely empty, only two airports and ten dates occurred, the plane column was blank in 536 of 600 rows, there were only seven airlines, and nine rows pointed to passengers that do not exist. The first step was therefore to turn the rules of the teacher's guide into 17 automatic checks and to run them before and after every change, so that each repair could be measured: nine rules passed on the source data and all 17 pass after preprocessing.

**The ticket table has no airports.** Departure and landing airports could not be copied from anywhere. The solution was one rule that keeps everything consistent: a flight number defines its route, its aircraft and its optional stopover, and all tickets and passengers of that flight inherit them. Only airports that exist in the airport table and have an airport code are used.

**Stopovers had to be believable.** A transit airport chosen at random would be a different city on the other side of the country. The final rule gives a stopover only to routes of at least 900 km, requires the transit airport to differ from both ends and to be at least 150 km from each, and limits the detour to 25 percent over the direct distance. Without a stopover the transit key stays empty and the warehouse maps it to a special "No stopover" row.

**Dates, airlines and prices had to stay linked.** Whole ticket groups were moved to other tickets of the same flight number, so that the departure and arrival dates keep matching the ticket and overnight arrivals remain correct. Four more airlines received 240 flagged supplemental tickets (the original tickets stay untouched). Prices are computed from the cabin class and the distance and then checked against the price ranges: 531 rows were outside their range before, none after.

**Repeatable and tested.** The whole pipeline uses a fixed random seed, so it gives the same result every time, and its rules are covered by automated tests that were written together with the code.

## Hina Shamshad

My part was the OLAP analysis: writing the 28 MDX statements, working out the stopover findings, and taking the screenshots that prove every result. The main difficulty was not the data but learning to think in MDX instead of SQL, and then making sure every number shown in the report is actually correct.

**MDX is a different way to ask a question.** In SQL I would join the fact table to a dimension and group by a column; in MDX there is no join, only a hierarchy to walk down (drill down), up (roll up), or cut at one level (slice). I had to get used to writing a question in plain words first ("which five transit airports carry the most revenue on stopover segments?") and only then translating it into sets and tuples on ROWS and COLUMNS. Each of the eight operations we implemented — the seven the guide names (drill down, roll up, slice, dice, rank, top N, moving average) plus running total, our own addition — turned out to need its own MDX construct, not just a different filter on the same query.

**Three statements per operation had to be genuinely different, not three copies with a different number.** For the dice operation in particular, a real dice means filtering two dimensions at once; my first attempts filtered one dimension and just changed the measure, which is closer to a slice. The version that stayed is `04_dice_1`, which crosses two departure provinces with two calendar quarters, so both dimensions are actually cut at the same time.

**The stopover comparison needed two kinds of "stopover".** To compare segments with a stopover against direct segments, the cube already has a real member for "no stopover", but there is no single real member for "has a stopover" — every transit airport is its own member. The fix was a calculated member that aggregates every transit airport except "no stopover", and a second calculated member for the average price with its own `SOLVE_ORDER`, so that the ratio is taken of the total price and total segments, not an average of per-airport ratios (which would have given a misleading number).

**SSMS rounds what it shows.** When I took the screenshots, I noticed that some results looked different from the numbers I had checked, for example 69.5 showing as 70. SSMS applies the cube's own number format to the display, which rounds it. I kept the exact values in the result tables of the report and noted in the screenshot checklist that the screenshots show the rounded, formatted value on purpose.

**Keeping 28 screenshots consistent.** With this many screenshots, it is easy for one of them to be taken before a fix, or for the query and the result pane to not both be visible. I re-ran every statement after the cube was corrected and compared each result against its T-SQL answer key before taking the final screenshot, so that all 28 results match; to stay within the report's page limit, only nine of the screenshots (one per operation) are printed, and the rest are kept as evidence alongside the committed results.
