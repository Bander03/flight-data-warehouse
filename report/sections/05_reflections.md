# 5. Lessons and experience from the course and the project

## Bander Sidiq Mahmood

**What I learned.** Before this project a data warehouse was for me only a set of tables. Building one showed me that the most important decision is the grain of the fact table: once we fixed it as one passenger on one flight segment, the dimensions, the measures and even the questions we could ask followed from it. I also understood why role-playing dimensions exist: departure date and arrival date, or departure, transit and landing airport, are the same dimension used in different roles, and modelling them once keeps the data consistent and the cube small. Writing MDX taught me a different way of thinking than SQL: instead of joining tables, one navigates hierarchies and works with sets and tuples, and operations like drill down, roll up, ranking and moving averages become natural there but awkward in SQL.

**What I think is special in our work.** Our preprocessing is not a random fill of missing values. The rule is that a flight number defines its route, its aircraft and its stopover, and every other value has to stay consistent with that; every rule of the course guide, and more, is checked automatically before and after preprocessing, and the whole pipeline is reproducible with a fixed random seed. The cube is built by a generated script and not by clicking, so it can be rebuilt in minutes. Every one of the 28 MDX statements is verified against an independent SQL query, so the numbers in the report are not just output that looks right.

**What I would do differently.** I would install and test the whole environment (Developer edition, Analysis Services, Visual Studio extensions) in the first days, because that is where we lost the most time. With more time I would add aggregations and partitions to the cube, security roles for different user groups, and an incremental load so that new flights could be added without rebuilding the warehouse. Finally, working through a shared repository with one file per section showed me that organising a team is part of the engineering, not something outside it.

## Yohannes Abate Ejita

**What the preprocessing part shows about data quality.** A warehouse is only as good as its data. The delivered table looked complete, but measured against the rules of the guide it failed eight of 17 checks. Writing the rules down as automatic checks first, and running them before and after the repair, made the problems visible and the repair provable.

**Consistency matters more than volume.** The easy way to reach "20 airports" is to fill random values. The approach that works is to find one rule from which everything else follows: here, a flight number fixes the route, the aircraft and the stopover, and the dates, prices and passengers must agree with it. Rules like the 900 km minimum for a stopover keep the result realistic as well as valid.

**What is special in this part.** All 17 rules of the teacher are checked automatically before and after preprocessing, the pipeline is deterministic (fixed seed), supplemental data is flagged so that the original data can always be told apart.

**What could be done differently.** With more time the stopover model could include the time spent on the ground, which the source data does not contain, and the route table could be taken from real timetable data instead of rules derived from the airline hubs.

## Hina Shamshad

**What I learned about OLAP.** Before this project, "analysing data" meant SQL to me: join, group by, filter. MDX showed me a different model, where a hierarchy (geography, calendar) is the main thing being navigated and a query is really a choice of a set of members on each axis, plus whatever calculated members the question needs. Operations I thought of as "just a different way to look at the same table" turned out to need different MDX tools: drill down and roll up walk a hierarchy level by level, slice fixes one dimension, dice fixes two at once, and rank, top N, moving average and running total all lean on calculated measures rather than on filtering alone.

**What I think is special in this part.** None of the 28 statements is accepted on trust: each has an independent T-SQL answer key, and the comparison script checks every one of them numerically, including how ties in the ranked lists are broken. The stopover analysis does not just say "stopovers exist", it isolates them with a calculated member and compares the real, aggregated average price against direct flights, so the comparison is between two correctly aggregated numbers and not between two averages of averages.

**What could be done differently.** I would start writing the MDX side by side with the cube design instead of after it, since a few statements only became easy once a calculated member existed that I had to ask Bander to add. I also noticed only late that SSMS rounds displayed values, which cost time redoing screenshots; next time I would check the display format against the exact value from the start. With more time, I would also look at the time actually spent at a stopover airport, which the data does not currently contain.
