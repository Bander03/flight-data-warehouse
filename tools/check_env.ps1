# check_env.ps1: verifies the software needed for the cube/MDX/SSIS phase (Plan 2, Task 4).
# Read-only: it only looks at services, files and the registry, and runs one SELECT 1.
# Usage (PowerShell or cmd.exe, from the repo root):  powershell -File tools\check_env.ps1
# Exit code 0 = everything present, 1 = at least one FAIL.

$ErrorActionPreference = 'Continue'
$script:failures = 0

function Report([string]$name, [bool]$ok, [string]$detail) {
    if ($ok) { $tag = 'PASS' } else { $tag = 'FAIL'; $script:failures++ }
    Write-Output ('{0}  {1}  {2}' -f $tag, $name.PadRight(46), $detail)
}

# 1. Database Engine: the existing Express instance that holds FlightDW must answer.
$sqlcmd = Get-Command sqlcmd -ErrorAction SilentlyContinue
if ($sqlcmd) {
    $out = & sqlcmd -S 'localhost\SQLEXPRESS' -E -d FlightDW -h -1 -W -Q 'SET NOCOUNT ON; SELECT COUNT(*) FROM dw.Fact_FlightSegment' 2>&1
    $rows = ($out | Out-String).Trim()
    Report 'FlightDW on localhost\SQLEXPRESS' ($rows -eq '600') ("fact rows = $rows (expected 600)")
} else {
    Report 'FlightDW on localhost\SQLEXPRESS' $false 'sqlcmd not found'
}

# 2. A Developer-edition Database Engine instance (optional but recommended); report editions found.
$engines = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'MSSQLSERVER' -or $_.Name -like 'MSSQL$*' }
$names = ($engines | ForEach-Object { $_.Name + '=' + $_.Status }) -join ', '
Report 'SQL Server Database Engine instances' ($engines.Count -gt 0) $names

# 3. Analysis Services (Multidimensional): service present and running.
$ssas = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'MSSQLServerOLAPService' -or $_.Name -like 'MSOLAP$*' }
$ssasNames = ($ssas | ForEach-Object { $_.Name + '=' + $_.Status }) -join ', '
$ssasOk = ($ssas | Where-Object { $_.Status -eq 'Running' }).Count -gt 0
Report 'Analysis Services service running' $ssasOk $ssasNames

# 3b. Analysis Services server mode must be Multidimensional (registry: DeploymentMode 0 = Multidimensional).
$modeText = 'service not installed'
$modeOk = $false
$msas = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server' -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -like 'MSAS*' }
foreach ($key in $msas) {
    $setup = Get-ItemProperty -Path (Join-Path $key.PSPath 'Setup') -ErrorAction SilentlyContinue
    if ($setup -and $null -ne $setup.DeploymentMode) {
        $modeText = ('{0}: DeploymentMode={1}' -f $key.PSChildName, $setup.DeploymentMode)
        if ($setup.DeploymentMode -eq 0) { $modeOk = $true }
    }
}
if ($modeOk) {
    Report 'Analysis Services mode = Multidimensional' $true $modeText
} elseif ($ssas.Count -gt 0) {
    # SQL Server 2025 does not expose DeploymentMode in the registry and msmdsrv.ini needs administrator
    # rights, so the mode cannot be read from here. Verify it once in SSMS (see docs\environment-setup.md).
    Write-Output ('INFO  {0}  {1}' -f 'Analysis Services mode = Multidimensional'.PadRight(46), 'not verifiable by script: in SSMS connect to Analysis Services > right-click server > Properties > DeploymentMode must be 0 (Multidimensional)')
} else {
    Report 'Analysis Services mode = Multidimensional' $false $modeText
}

# 4. Integration Services service.
$ssis = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'MsDtsServer*' }
$ssisNames = ($ssis | ForEach-Object { $_.Name + '=' + $_.Status }) -join ', '
Report 'Integration Services service present' ($ssis.Count -gt 0) $ssisNames

# 5. Visual Studio extensions: search the VSIX manifests for the two project types.
$roots = @()
foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    $vs = Join-Path $base 'Microsoft Visual Studio'
    if (Test-Path $vs) { $roots += Get-ChildItem $vs -Directory -ErrorAction SilentlyContinue | ForEach-Object { Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue } }
}
$searchDirs = @()
foreach ($r in $roots) {
    foreach ($sub in @('Common7\IDE\CommonExtensions', 'Common7\IDE\Extensions')) {
        $p = Join-Path $r.FullName $sub
        if (Test-Path $p) { $searchDirs += $p }
    }
}
$userExt = Join-Path $env:LOCALAPPDATA 'Microsoft\VisualStudio'
if (Test-Path $userExt) { $searchDirs += $userExt }
$manifests = @()
foreach ($d in $searchDirs) {
    $manifests += Get-ChildItem $d -Recurse -Filter 'extension.vsixmanifest' -Depth 4 -ErrorAction SilentlyContinue
}
$text = ($manifests | ForEach-Object { Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue }) -join "`n"
$hasAs = $text -match 'Analysis Services'
$hasIs = $text -match 'Integration Services'
Report 'VS extension: Analysis Services Projects' $hasAs ("$($manifests.Count) manifests searched")
Report 'VS extension: Integration Services Projects' $hasIs ''

# 6. SSMS.
$ssms = @()
foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
    $ssms += Get-ChildItem $base -Directory -Filter 'Microsoft SQL Server Management Studio*' -ErrorAction SilentlyContinue
}
Report 'SQL Server Management Studio installed' ($ssms.Count -gt 0) (($ssms | ForEach-Object { $_.Name }) -join ', ')

# 7. PowerShell SqlServer module (provides Invoke-ASCmd, used by tools\run_mdx.ps1).
$mod = Get-Module -ListAvailable SqlServer -ErrorAction SilentlyContinue | Select-Object -First 1
$modText = 'not installed'
$modOk = $false
if ($mod) { $modText = 'SqlServer ' + $mod.Version; $modOk = $true }
else {
    # Some hosts do not list the per-user module folder; look there directly.
    $userMod = Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Modules\SqlServer'
    if (Test-Path $userMod) { $modText = 'SqlServer in ' + $userMod; $modOk = $true }
}
Report 'PowerShell module SqlServer (Invoke-ASCmd)' $modOk $modText

Write-Output ''
if ($script:failures -eq 0) { Write-Output 'All checks passed.'; exit 0 }
Write-Output ("$($script:failures) check(s) failed. See docs\environment-setup.md.")
exit 1
