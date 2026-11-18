# SSIS package `LoadFlightDW` (report figure D4)

The package is **generated and tested**, no clicking in Visual Studio needed:

```powershell
python tools\build_ssis_package.py      # writes ssis\FlightDWLoad\LoadFlightDW.dtsx
python tools\make_ssis_diagram.py       # redraws the report figure docs\figures\ssis-control-flow.png
& "C:\Program Files\Microsoft SQL Server\170\DTS\Binn\DTExec.exe" /File ssis\FlightDWLoad\LoadFlightDW.dtsx
powershell -File tools\deploy_cube.ps1 -Smoke    # re-process the cube: the package rebuilt FlightDW
```

`dtexec` must end with `DTSER_SUCCESS (0)` (verified 2026-11-13: seven tasks, 600 fact rows afterwards, cube smoke test 600 / 95 / 1,400,460 / 599). The structure is pinned by `preprocessing/tests/test_ssis_package.py`. The package variables `RepoDir`, `DataDir` and `SqlInstance` feed property expressions, so it runs from any clone: `RepoDir` is `.` (the folder `dtexec` is started in), so **start `dtexec` in the repository root**; change `RepoDir` only if you run it from elsewhere. Warning: task 2 drops and recreates the database `FlightDW`; never run it against another server.

Report figure D4 is the control-flow diagram drawn from the package file (`tools/make_ssis_diagram.py`). If you want a Visual Studio screenshot instead (optional): create an *Integration Services Project* in Visual Studio 2019, use **Add > Existing Item** to add `ssis\FlightDWLoad\LoadFlightDW.dtsx`, run it with F5 and screenshot the green control flow.

---

# Manual build in Visual Studio (alternative, kept for reference)


The warehouse is already built and verified by the SQL scripts. This package shows the same load as a diagram, the way the teacher's experiment guide shows ETL. It is **optional for the grade**; do it when the cube and the MDX are finished.

**Design decision:** the five scripts use `GO` batches and sqlcmd variables (`$(DataDir)`), and an SSIS *Execute SQL Task* supports neither. So each script (01 to 04, the checks 99 and the Analysis Services grant 05) is run by an **Execute Process Task** that calls `sqlcmd.exe`, the same command the README uses. The package is therefore a faithful picture of the real load, not a second implementation.

## 1. Create the project

Visual Studio 2019 > **File > New > Project** > **Integration Services Project**. Name `FlightDWLoad`, location `ssis\` in the repo. The package `Package.dtsx` opens; rename it `LoadFlightDW.dtsx`.

## 2. Variables (View > Other Windows > Variables)

| Name | Type | Value |
|---|---|---|
| `RepoDir` | String | your repo folder, for example `%USERPROFILE%\Desktop\BigDataFinalProject` (adjust to where you cloned it) |
| `DataDir` | String | `C:\fdw_data` |
| `SqlInstance` | String | `localhost\SQLEXPRESS` |

## 3. Control flow (drag from the SSIS Toolbox; connect with green success arrows, in this order)

In the arguments below, `<repo>` stands for your repo folder (the value of `RepoDir`, for example `C:\Users\<you>\Desktop\BigDataFinalProject`): type the full path, because Execute Process Task arguments do not expand `%USERPROFILE%`.

| # | Task type | Name | Settings |
|---|---|---|---|
| 1 | Execute Process Task | `Copy CSVs to DataDir` | Executable `C:\Windows\System32\cmd.exe`; Arguments `/c if not exist C:\fdw_data mkdir C:\fdw_data & copy /Y "<repo>\data\processed\*.csv" C:\fdw_data\` |
| 2 | Execute Process Task | `01 create database` | Executable `sqlcmd.exe`; Arguments `-S localhost\SQLEXPRESS -E -b -f 65001 -i "<repo>\sql\01_create_db.sql"` |
| 3 | Execute Process Task | `02 staging tables` | same, `02_stg_tables.sql` |
| 4 | Execute Process Task | `03 star schema` | same, `03_dw_tables.sql` |
| 5 | Execute Process Task | `04 load` | same plus `-v DataDir="C:\fdw_data"` and `04_load.sql` (the quotes around the value are required) |
| 6 | Execute Process Task | `99 checks` | same, `99_checks.sql` |
| 7 | Execute Process Task | `05 grant cube read` | same, `05_grant_ssas_read.sql` |

Task 7 is required, not optional: task 2 drops `FlightDW`, and with it the database user `NT Service\MSOLAP$DEV`, so after every run of this package the Analysis Services grant must be re-created (the script is idempotent and gives read-only access to `FlightDW` only) before the cube is processed again (`powershell -File tools\deploy_cube.ps1 -Smoke`, README step 5). Without it the next Process Full of `FlightCube` fails with a login error.

For every Execute Process Task set **FailTaskIfReturnCodeIsNotSuccessValue = True** and **SuccessValue = 0**, so a failed check turns the task red and stops the package. Better: replace the fixed paths by property expressions using the variables (Expressions > Arguments), once the first run works.

Task 2 drops and recreates only the database `FlightDW`; the package must not be run against any other server.

## 4. Run and capture

1. Right-click the package > **Execute Package** (or press F5). All seven tasks must turn **green**. Then re-process the cube (`powershell -File tools\deploy_cube.ps1 -Smoke`), because the package rebuilt the database it reads.
2. Screenshot **D4**: the control flow with all tasks green (and, if you like, the Progress tab).
3. Verify: `sqlcmd -S localhost\SQLEXPRESS -E -d FlightDW -Q "SELECT COUNT(*) FROM dw.Fact_FlightSegment"` returns `600`.

## 5. Save and commit

Close Visual Studio, then commit `ssis\FlightDWLoad\` (`.sln`, `.dtproj`, `.dtsx`, `.conmgr` files); do not commit `bin\` or `obj\`.

If the package cannot run for any reason, the report does not lose points: the load is demonstrated by the SQL scripts and `sql\99_checks.sql` (screenshot D3).
