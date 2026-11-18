# Flight Data Warehouse: Group 2

**Website:** https://bander03.github.io/flight-data-warehouse/ · **Report (PDF):** [report/FlightDW_Course_Project_Report.pdf](report/FlightDW_Course_Project_Report.pdf)

Course project, Big Data Intelligent Management and Analysis (Prof Yan Zhu).
**Deadline: Monday 2026-12-21** (paper report + e-version).

Topic: design and build a data warehouse for flight journeys. The fact table is the
flight segment fact table (`Fact_Airticket`, our file: `fact table group_2`) with 8 dimension tables.

## Team

| Member | Role |
|---|---|
| Bander Sidiq Mahmood (leader) | Schema design, warehouse build, cube, repo and merging |
| Yohannes Abate Ejita | Preprocessing, stopover generation, data validation |
| Hina Shamshad | OLAP / MDX queries, stopover analysis, screenshots |

## What is graded

| Part | Weight |
|---|---|
| Star schema + preprocessing + showing both in report | 25% |
| Build the data warehouse (creation statements <= 1/3 of report space) | 15% |
| 7+ OLAP operations x 3 different MDX statements (21+), plus stopover analysis | 40% |
| Project report | 20% |

## Repository layout

| Folder | Content | Owner |
|---|---|---|
| `docs/` | Plan, data findings, design notes, task list | Bander |
| `preprocessing/` | Scripts that fix the fact table + validation checks | Yohannes |
| `sql/` | Warehouse DDL, ETL / load scripts | Bander |
| `mdx/` | The 28 MDX statements (`*.mdx`), their T-SQL answer keys (`answers/`) and saved results (`results/`) | Hina (then split) |
| `ssas/` | Generated cube definition `FlightCube.xmla` (from `docs/cube-spec.md`, by `tools/build_cube_xmla.py`) | Bander |
| `ssis/` | Generated SSIS package `LoadFlightDW.dtsx` (by `tools/build_ssis_package.py`) | Bander |
| `tools/` | Build, deploy, run and verify scripts (cube, MDX, SSIS, report, audits) | Bander |
| `report/` | Report sections in Markdown; final `.docx` assembled by one person | all |
| `web/` | Local website (Python standard library) to browse the 28 MDX analyses | Bander |
| `data/raw`, `data/processed` | Local only, not in git. Get files from the shared drive | n/a |

## How to run

Run everything from the repo root. Needs Python 3.10 to 3.12 (tested on 3.10.5) and, for the warehouse, SQL Server 2017+ (tested on 2022 Express,
instance `localhost\SQLEXPRESS`, Windows authentication). The raw data folder (`0 2026_DW project_data set_1 Fact+ 8 Dim for 1 Group`)
must sit at the repo root; it is not in git.

1. Install the Python requirements:

   ```
   pip install -r preprocessing/requirements.txt
   ```

2. Run the preprocessing pipeline. It reads the raw Excel files (the first run caches them as CSV in `data/raw`), repairs the
   fact table, checks all 17 guide #2 rules, and writes the nine CSVs plus `profile_before_after.md` to `data/processed`:

   ```
   set PYTHONPATH=preprocessing/src
   python -m fdw.cli
   ```

   (Git Bash: `PYTHONPATH=preprocessing/src python -m fdw.cli`.) Output is deterministic (seed 20261112). The last line reads
   `17/17 rules passed`.

3. Build the warehouse. `BULK INSERT` runs as the SQL Server service account, which cannot read your Desktop, so copy the CSVs
   to `C:\fdw_data` first, then run the five scripts (cmd.exe). Quote the `DataDir` value, or sqlcmd fails with `Invalid argument`:

   ```
   mkdir C:\fdw_data
   copy data\processed\*.csv C:\fdw_data\
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\01_create_db.sql
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\02_stg_tables.sql
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\03_dw_tables.sql
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -v DataDir="C:\fdw_data" -i sql\04_load.sql
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\99_checks.sql
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\05_grant_ssas_read.sql
   ```

   This drops and recreates only the database named `FlightDW`. The last line gives the cube's service account read access
   (step 5); **re-run `sql\05_grant_ssas_read.sql` after every rebuild of `FlightDW`** (these scripts, the SSIS package or the
   warehouse tests), because dropping the database also drops that user and the next cube processing then fails with a
   login error. It is idempotent. See [sql/README.md](sql/README.md) for details.

4. Run the tests (869 tests, about 100 s: 861 run offline, 8 are skipped by default: the 6 warehouse tests below and 2 live cube
   tests of step 5; the audit tests of step 4b skip themselves when the warehouse is not built):

   ```
   pytest preprocessing/tests -v
   ```

   The 6 warehouse tests in `test_warehouse.py` are **skipped by default**, because they drop and rebuild the database `FlightDW`
   (and would destroy any cube or SSIS objects added to it later). To run them, run step 2 first (they skip when
   `data/processed` lacks a CSV), then opt in (cmd.exe, two separate lines):

   ```
   set FDW_WAREHOUSE_TESTS=1
   pytest preprocessing/tests/test_warehouse.py -v
   ```

   (Git Bash: `FDW_WAREHOUSE_TESTS=1 pytest preprocessing/tests/test_warehouse.py -v`.) They copy the CSVs to `C:\fdw_data`
   themselves and skip if `sqlcmd` or the instance is unavailable.

4b. Independent audits (read-only; the warehouse audit needs step 3, the cube audit step 5; they do not reuse the project's code):

   ```
   sqlcmd -S localhost\SQLEXPRESS -E -b -f 65001 -i sql\98_independent_audit.sql   # 22 checks on the warehouse
   powershell -File tools\audit_cube.ps1                                        # 29 checks: cube against warehouse
   ```

   The first recomputes distances, stopover rules, dates, prices and totals from the `dw` tables; the second compares every
   cube dimension, role and calculated member with SQL. Both exit non-zero on the first violation. The plan and the results
   of the whole test campaign are in [docs/test-plan.md](docs/test-plan.md) and [docs/test-report.md](docs/test-report.md).

5. Build the cube and run the 28 MDX statements. Extra requirements: SQL Server 2025 Developer with Analysis Services in
   **Multidimensional** mode as the named instance `DEV` ([docs/environment-setup.md](docs/environment-setup.md); check with
   `powershell -File tools\check_env.ps1`). Analysis Services needs read access to `FlightDW`: the database owner runs
   `sqlcmd -S localhost\SQLEXPRESS -E -b -i sql\05_grant_ssas_read.sql` (read-only, one service account) after every rebuild
   of `FlightDW` (step 3). Then, in Windows PowerShell from the repo root:

   ```
   # regenerate ssas\FlightCube.xmla from docs\cube-spec.md (the file is already committed)
   python tools\build_cube_xmla.py
   # create and process the database FlightCube; prints 600 / 95 / 1400460 / 599
   powershell -File tools\deploy_cube.ps1 -Smoke
   # run mdx\*.mdx on the cube, write mdx\results\*.csv
   powershell -File tools\run_mdx.ps1
   # compare every result with its T-SQL answer key (mdx\answers): 28 of 28 must match
   python tools\compare_results.py
   ```

   `powershell -File tools\deploy_cube.ps1 -SmokeOnly` repeats only the smoke query, and `powershell -File tools\run_mdx.ps1 -Stem 05_rank_1`
   runs one statement. Details: [mdx/README.md](mdx/README.md), design: [docs/cube-spec.md](docs/cube-spec.md). Opt-in live
   tests (read-only queries on the deployed cube), in the same Windows PowerShell window:

   ```
   $env:FDW_CUBE_TESTS = '1'
   python -m pytest preprocessing/tests/test_cube_xmla.py preprocessing/tests/test_cube_xmla_spec.py -v
   Remove-Item Env:FDW_CUBE_TESTS
   ```

6. Build the Word report from the Markdown sections (formatting from guide #4; tables and figures are numbered by the builder;
   `--check` lists the placeholders, author instructions and uncaptioned tables that remain):

   ```
   python tools\build_report.py
   python tools\build_report.py --check
   ```

   The star schema figure is regenerated with `python tools\make_star_diagram.py`; the section on the 28 OLAP functions with
   `python tools\make_functions_section.py` (only for a first draft: it refuses to overwrite hand edits without `--force`).
   See [report/README.md](report/README.md) and [docs/screenshot-checklist.md](docs/screenshot-checklist.md).

7. Optional: the local website, a dashboard for browsing the project: an overview (totals, monthly revenue, how the project was
   built, star schema, team), the guide #2 preprocessing checks before and after, the 28 MDX analyses (question, result chart,
   SSMS screenshot, MDX, match with the T-SQL answer key; filter by operation), the stopover analysis, and the report with every
   teacher requirement and where it is met (`web/requirements.json`, kept by hand). It reads the committed files, so it needs
   neither the warehouse nor the cube. The button "Run live on the cube" re-runs one stored
   statement on Analysis Services (needs step 5) and compares it with the saved result without changing any file. It listens on
   this computer only (`127.0.0.1`) and needs no extra package:

   ```
   python web\server.py --open
   ```

   Open `http://127.0.0.1:8000` if the browser does not start; stop with Ctrl+C. The overview numbers are counted from
   `data/processed`, or read from `web/overview_snapshot.json` and `web/profile_snapshot.json` when that folder is missing
   (refresh both with `python -m web.data --write-snapshot`). The Report page opens `report/build/FlightDW_Course_Project_Report.pdf`
   when it has been exported. `python tools/build_static_site.py` writes a static copy into `site/` that needs no
   server (for GitHub Pages); there the live button is replaced by a note.

Why the pipeline output is not just the source data: see the decisions in [docs/DATA_FINDINGS.md](docs/DATA_FINDINGS.md).

## Working rules

1. Each person works in their own folders. Ask before editing someone else's files.
2. Commit text only (SQL, Python, MDX, Markdown). Never commit Excel, `.rar`, `.bak` or PDF files.
3. Work on a branch (`yohannes/preprocessing`, `hina/mdx-rollup`), open a pull request, and Bander reviews it.
4. Post progress at least twice a week. If you are stuck more than a day, say so.
5. Every task is a GitHub Issue with an owner and a date. See `docs/ISSUES.md` for the starter list.

See [docs/PLAN.md](docs/PLAN.md) for the timeline and [docs/DATA_FINDINGS.md](docs/DATA_FINDINGS.md) for the preprocessing work.
