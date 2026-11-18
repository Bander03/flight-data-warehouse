# Environment setup for the cube / MDX / SSIS phase

Goal: add Analysis Services (Multidimensional) and Integration Services next to the SQL Server Express that already holds `FlightDW`. Express stays untouched. Total time about 45 to 90 minutes, disk about 6 GB, administrator rights needed.

Check your progress at any time (read-only):

```
powershell -File tools\check_env.ps1
```

## What is already there

SQL Server 2022 Express (instance `localhost\SQLEXPRESS`, database `FlightDW`), Visual Studio 2019 Community, `sqlcmd`, `winget`.

## Step 1: SQL Server 2025 Developer with Analysis Services and Integration Services

Do **not** use the SQL Server 2022 installer, from `winget` or from <https://aka.ms/sqlserver2022developer>: both serve the same retired November 2022 bootstrapper (`SQL2022-SSEI-Dev.exe`), which stops with "This version of the installer is no longer supported" or crashes at startup (seen on 2026-11-12). Use SQL Server 2025 instead.

Download the current installer from Microsoft (4.6 MB, file `SQL2025-SSEI-EntDev.exe`): open <https://aka.ms/sql2025developer> in your browser, then right-click the downloaded file and choose **Run as administrator**. When it asks for the edition, choose the free **Developer** edition (not Evaluation). In the installer:

1. Choose **Custom**, then let it download the media, then open the **SQL Server Installation Center**.
2. **Installation** > **New SQL Server stand-alone installation or add features**. Edition: **Developer**.
3. **Feature Selection**: tick **Database Engine Services**, **Analysis Services** and, under Shared Features, **Integration Services**. Leave the rest.
4. **Instance Configuration**: **Named instance**, name `DEV`. (This keeps your existing `SQLEXPRESS` untouched.)
5. **Database Engine Configuration**: **Windows authentication mode**, click **Add Current User** as SQL Server administrator.
6. **Analysis Services Configuration**: Server Mode **Multidimensional and Data Mining Mode** (this is the important one: MDX needs it). Click **Add Current User** as Analysis Services administrator.
7. Finish the wizard. If a prerequisite error appears, write down its exact text and send it to me.

## Step 2: SQL Server Management Studio

```
winget install Microsoft.SQLServerManagementStudio
```

(administrator terminal; this is SSMS 20.2, the classic installer.)

## Step 3: Visual Studio extensions

Open **Visual Studio 2019**, then **Extensions > Manage Extensions > Online**. Search and install both:

- **SQL Server Integration Services Projects** (Microsoft)
- **SQL Server Analysis Services Projects** (Microsoft; its listing may say "Microsoft Analysis Services Projects")

Close Visual Studio completely so the extension installer can run, accept its prompts, then reopen Visual Studio once to confirm that **File > New > Project** now lists "Analysis Services Multidimensional and Data Mining Project" and "Integration Services Project".

## Step 4: PowerShell module for running MDX from scripts

In a normal PowerShell window:

```
Install-Module SqlServer -Scope CurrentUser
```

Answer **Y** to the prompts (it downloads from the PowerShell Gallery).

## Step 5: allow the cube service to read FlightDW

Analysis Services reads `FlightDW` from the Express instance as its own service account `NT Service\MSOLAP$DEV` (data-source impersonation `ImpersonateServiceAccount`; no password is stored anywhere). That account needs read access to `FlightDW`, which is one permission change on the Express instance, made by the database owner with a read-only script:

```
sqlcmd -S localhost\SQLEXPRESS -E -b -i sql\05_grant_ssas_read.sql
```

Re-run it after **every** rebuild of `FlightDW` (`sql\01_create_db.sql`, the SSIS package or the warehouse tests drop the database and with it this user); otherwise the next Process Full of the cube fails with a login error. It is idempotent and gives `db_datareader` on `FlightDW` only.

## Step 5b: confirm Multidimensional mode (once, in SSMS)

The check script cannot read the Analysis Services mode on SQL Server 2025. After SSMS is installed: open SSMS, **Connect > Analysis Services**, server name `localhost\DEV`, Windows authentication. Right-click the server name > **Properties**, tick **Show Advanced (All) Properties**, find **DeploymentMode**: it must be **0** (Multidimensional). If it says 2 (Tabular), tell me: the instance must be reinstalled in the right mode.

## Step 6: verify

```
powershell -File tools\check_env.ps1
```

Expected: every line shows PASS. Send me the output; FAIL lines tell us exactly what is missing.
