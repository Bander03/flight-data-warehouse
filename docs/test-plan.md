# Test plan: Flight Data Warehouse (Group 2)

Goal: find bugs, mistakes and limitations in every layer of the project, in more than one way, fix what is wrong and write down what cannot be fixed. Results go to [test-report.md](test-report.md). Date of the run: 2026-11-15.

Principle: every layer is tested by (1) the project's own automated tests, (2) an independent re-computation that does not reuse the project's code, and (3) a run from a clean state, so that "works on my machine" is excluded. A test passes only if its expected value was fixed before the run.

## Layers and tests

| ID | Layer | Test | Method | Expected |
|---|---|---|---|---|
| A1 | All code | Full pytest suite, offline | `pytest preprocessing/tests` | 0 failures |
| A2 | Warehouse | Opt-in warehouse tests (drop and rebuild FlightDW) | `FDW_WAREHOUSE_TESTS=1` | all pass |
| A3 | Cube | Opt-in live cube tests | `FDW_CUBE_TESTS=1` | all pass |
| B1 | Reproducibility | Pipeline run twice | SHA-256 of the 9 output CSVs, run 1 against run 2 | identical |
| B2 | Reproducibility | Fresh clone of GitHub `main`, README steps 1 to 6 as written | temp folder, raw data copied in | every command succeeds, numbers equal |
| B3 | Idempotency | `04_load.sql` and the full SQL chain run twice | row counts and `99_checks` after each run | identical, no error |
| B4 | Idempotency | Cube deployed twice | `deploy_cube.ps1 -Smoke` twice | same totals |
| C1 | Data | Guide #2 rules re-implemented from the guide text, independent of `validate.py` | SQL on the warehouse | all hold |
| C2 | Data | Referential integrity and key uniqueness of all 9 tables | SQL | 0 orphans, 0 duplicates |
| C3 | Data | Stopover plausibility: transit differs from both ends, route >= 900 km, detour <= 25 %, >= 150 km from each end, recomputed with SQL haversine | SQL | 0 violations |
| C4 | Data | Dates: arrival >= departure; date keys exist; 6+ calendar months | SQL | 0 violations |
| C5 | Data | Price inside its price range; price = f(cabin, distance) sanity; mileage > 0 | SQL | 0 violations |
| C6 | Data | Chinese text survives the whole chain (CSV, staging, dimension, cube caption) | compare code points | no `?` or mojibake |
| C7 | Data | Supplemented rows are flagged; original 568,917 tickets unchanged | SQL | counts as documented |
| D1 | Cube | Every measure by every dimension adds up to the grand total | MDX per dimension | equals 600 / 95 / 1,400,460 |
| D2 | Cube | Role-playing: departure vs arrival date and the three airport roles give different, correct results | MDX against SQL | match |
| D3 | Cube | Calculated members (Average Price, Average Rate, Stopover Share) against SQL, also on empty cells (no division by zero) | MDX against SQL | match |
| D4 | Cube | Distinct Passengers is not additive: parent value <= sum of children | MDX | holds |
| D5 | Cube | Unknown / "No stopover" member behaves (NULL transit, key 0) | MDX | counted, not dropped |
| E1 | MDX | All 28 statements run and equal their T-SQL answer key | `run_mdx.ps1` + `compare_results.py` | 28 of 28 |
| E2 | MDX | Every statement uses the operation it claims (WHERE for slice, CROSSJOIN for dice, RANK/TOPCOUNT, moving window, YTD) | text check against the header comments | consistent |
| E3 | MDX | Result files are in sync with the cube (results rewritten, `git diff` empty) | rerun and diff | no diff |
| F1 | Report | Build from Markdown; `--check`; every figure has a file; captions above/below; numbering | `build_report.py` | 0 problems |
| F2 | Report | Numbers in the text against the data (every 3+ digit number in prose) | existing test + manual spot check of 15 sentences | all correct |
| F3 | Report | Guide #4 format: Times New Roman 11, cover fonts, page numbers, code snippets <= 1/3 A4 page, creation statements <= 1/3 of report | python-docx and the PDF | within limits |
| F4 | Report | Visual check of every page of the PDF (clipping, blank pages, unreadable figures) | page images | none |
| F5 | Report | References: each cited, in order of first citation, links respond | script + curl | consistent |
| F6 | Report | Spelling and wording | script over the text | no typos |
| G1 | Docs | README commands run as written in Windows PowerShell and cmd | fresh clone (B2) | work |
| G2 | Docs | Every file path named in the docs exists | script | none missing |
| H1 | Robustness | Preprocessing refuses bad input: missing raw file, wrong column, empty file | run with broken input | clear error, no partial output |
| H2 | Robustness | SQL scripts abort on error (`-b`) and the checks fail on a corrupted table | tamper in a scratch DB copy | non-zero exit |
| J1 | Website | Data layer, live runner, server and static pages: all 28 analyses load, Chinese and `|` in members, unknown or traversal stems give 404, saved results are never changed, offline-safe pages | `pytest preprocessing/tests/test_web_*.py` | 0 failures |
| J2 | Website | Browser check of Overview, Analyses, one analysis, Stopover at desktop and 375 px width, light and dark; no horizontal scroll | browser pane | readable, no overflow |
| J3 | Website | "Run live on the cube" against the real cube (ranked statement); `git status` afterwards | real click | same rows as saved, no file changed |
| J4 | Website | Cube or PowerShell unavailable | fake runner in tests | friendly message, saved result stays |
| I1 | Security / hygiene | No secrets, no personal paths or e-mail in tracked files; `.gitignore` covers data | `git grep` | none |

## Limitations to record (known by design, to be listed in the report of the test)

- The source data are synthetic in places: supplemented airline tickets (`IsSupplemented`), re-assigned dates and generated stopovers; analysis results describe the prepared data, not real traffic.
- Stopovers exist only on routes >= 900 km, so stopover versus direct comparisons are not like-for-like.
- Stopover duration (ground time) is not modelled.
- Distinct passengers is not additive over groups.
- The cube needs SQL Server Developer with Analysis Services in Multidimensional mode; SSMS shows rounded numbers (number format of the cube).

## Bug policy

A found bug is written in the test report with ID, layer, symptom, root cause and fix. A regression test is added whenever a fix is code. Anything that cannot be fixed is moved to the limitations list.
