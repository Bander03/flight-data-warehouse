# Appendix A. Warehouse creation statements

The star schema of `FlightDW` (dw.Fact_FlightSegment and its eight dimension tables, with 0 = 'No stopover'
and role-playing foreign keys); the database/schema creation, staging tables, load and checks scripts are
complete in the repository folder `sql/` (`01_create_db.sql`, `02_stg_tables.sql`, `04_load.sql`,
`99_checks.sql`), to keep this appendix within the space the course guide allows.

{{include: sql/03_dw_tables.sql}}

# Appendix B. Complete MDX statements

The complete MDX of all 28 statements, exactly as run on the cube (the question, operation and measure of
each are given in section 3.3; the header comments of the `.mdx` files themselves are omitted here to save
space).

## B.1 Drill down

**01_drill_down_1**

{{include-code: mdx/01_drill_down_1.mdx}}

**01_drill_down_2**

{{include-code: mdx/01_drill_down_2.mdx}}

**01_drill_down_3**

{{include-code: mdx/01_drill_down_3.mdx}}

## B.2 Roll up

**02_roll_up_1**

{{include-code: mdx/02_roll_up_1.mdx}}

**02_roll_up_2**

{{include-code: mdx/02_roll_up_2.mdx}}

**02_roll_up_3**

{{include-code: mdx/02_roll_up_3.mdx}}

## B.3 Slice

**03_slice_1**

{{include-code: mdx/03_slice_1.mdx}}

**03_slice_2**

{{include-code: mdx/03_slice_2.mdx}}

**03_slice_3**

{{include-code: mdx/03_slice_3.mdx}}

## B.4 Dice

**04_dice_1**

{{include-code: mdx/04_dice_1.mdx}}

**04_dice_2**

{{include-code: mdx/04_dice_2.mdx}}

**04_dice_3**

{{include-code: mdx/04_dice_3.mdx}}

## B.5 Rank

**05_rank_1**

{{include-code: mdx/05_rank_1.mdx}}

**05_rank_2**

{{include-code: mdx/05_rank_2.mdx}}

**05_rank_3**

{{include-code: mdx/05_rank_3.mdx}}

## B.6 Top N

**06_top_n_1**

{{include-code: mdx/06_top_n_1.mdx}}

**06_top_n_2**

{{include-code: mdx/06_top_n_2.mdx}}

**06_top_n_3**

{{include-code: mdx/06_top_n_3.mdx}}

## B.7 Moving average

**07_moving_avg_1**

{{include-code: mdx/07_moving_avg_1.mdx}}

**07_moving_avg_2**

{{include-code: mdx/07_moving_avg_2.mdx}}

**07_moving_avg_3**

{{include-code: mdx/07_moving_avg_3.mdx}}

## B.8 Running total

**08_running_total_1**

{{include-code: mdx/08_running_total_1.mdx}}

**08_running_total_2**

{{include-code: mdx/08_running_total_2.mdx}}

**08_running_total_3**

{{include-code: mdx/08_running_total_3.mdx}}

## B.9 Stopover analysis

**09_stopover_1**

{{include-code: mdx/09_stopover_1.mdx}}

**09_stopover_2**

{{include-code: mdx/09_stopover_2.mdx}}

**09_stopover_3**

{{include-code: mdx/09_stopover_3.mdx}}

**09_stopover_4**

{{include-code: mdx/09_stopover_4.mdx}}
