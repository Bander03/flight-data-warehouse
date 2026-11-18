# mdx

The MDX statement library for the cube `FlightCube` (8 OLAP operations x 3 statements, plus 4 stopover statements).

## Files

- `NN_<operation>_<k>.mdx`: one MDX query per file, with header comments `-- Operation:`, `-- Question:`, `-- Measure:`, `-- Answer key:`. Result shape: measure `Value` (and `Rank` first for `05_rank_*` and `06_top_n_*`) on COLUMNS, members on ROWS.
- `answers/NN_<operation>_<k>.sql`: the T-SQL answer key of each statement (read-only SELECT on `FlightDW`), columns `Member`, `Value` (`Rank` first for ranked statements).
- `results/<stem>.csv`: the cube's result of each statement (UTF-8, `Member,Value` or `Rank,Member,Value`; Member = row captions joined with ` | `; raw cell values), written by `tools/run_mdx.ps1`.
- `results/SUMMARY.md`: per statement the operation, question, measure, row count and first 5 rows, written by `tools/make_results_summary.py`.

## Run and compare (repo root)

```
powershell -File tools\run_mdx.ps1                 # run every statement on FlightCube, write results\*.csv
python tools\compare_results.py                    # compare with the answer keys; exit 1 on any mismatch
python tools\make_results_summary.py --compare     # rewrite results\SUMMARY.md (with the cross-check outcome)
```

`run_mdx.ps1 -Stem 05_rank_1` and `compare_results.py 05_rank_1` run selected statements; `run_mdx.ps1 -OutDir <folder>` writes the CSVs elsewhere and leaves `results\` untouched (the website uses it for its live runs). Needs the processed cube on the Analysis Services instance `DEV` and `sqlcmd` access to `localhost\SQLEXPRESS`.
