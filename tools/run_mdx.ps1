# run_mdx.ps1: runs every MDX statement of the library against the cube FlightCube (Plan 2, Task 6).
# Windows PowerShell 5.1. For each mdx\<stem>.mdx (one MDX query per file) it runs the query with
# Invoke-ASCmd, parses the MDDataset XML and writes mdx\results\<stem>.csv:
#   - UTF-8 without BOM, header Member,Value (Rank,Member,Value for 05_rank_* and 06_top_n_*);
#   - Member = the captions of the row-axis tuple's members joined with ' | ' in axis order;
#   - Value (and Rank) = the RAW cell value (<Value>, never <FmtValue>), invariant culture;
#   - rows whose Value cell is empty are omitted.
# The answer keys (mdx\answers\<stem>.sql) are compared afterwards by tools\compare_results.py.
#
# Usage (repo root):
#   powershell -File tools\run_mdx.ps1                     # all statements
#   powershell -File tools\run_mdx.ps1 -Stem 05_rank_1     # selected stems
#   powershell -File tools\run_mdx.ps1 -Server localhost:38612
# Exit code 0 = every statement ran; 1 = the server rejected at least one statement (named in the output)
# or a -Stem does not exist. The old CSV of a statement is deleted before it runs, so a failed statement
# leaves no result file behind (compare_results.py then reports it instead of matching a stale file).
# Read-only: it only sends MDX SELECT statements to the database FlightCube.
param(
    [string]$Server = '',
    [string]$Database = 'FlightCube',
    [string]$Instance = 'DEV',
    [string[]]$Stem = @(),
    [string]$OutDir = ''
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Repo = Split-Path -Parent $PSScriptRoot
$MdxDir = Join-Path $Repo 'mdx'
if (-not $OutDir) { $OutDir = Join-Path $MdxDir 'results' }   # -OutDir: the website writes live runs to a temp folder
$ModuleRoot = Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Modules\SqlServer'
$Inv = [System.Globalization.CultureInfo]::InvariantCulture
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Say([string]$msg) { [Console]::Out.WriteLine($msg) }
function Fail([string]$msg) { Say "ERROR: $msg"; exit 1 }

function Import-SqlServerModule {
    # By name first (any SqlServer version on PSModulePath); then the newest per-user install under
    # Documents\WindowsPowerShell\Modules (that folder is missing from PSModulePath in some shells).
    try { Import-Module SqlServer -DisableNameChecking -ErrorAction Stop; return } catch { }
    $cand = @(Get-ChildItem -Path $ModuleRoot -Filter 'SqlServer.psd1' -Recurse -ErrorAction SilentlyContinue |
              Sort-Object { [version]$_.Directory.Name } -Descending)
    if ($cand.Count -eq 0) { Fail "SqlServer module not found (Import-Module SqlServer failed, nothing under $ModuleRoot); install it with: Install-Module SqlServer -Scope CurrentUser" }
    Import-Module $cand[0].FullName -DisableNameChecking
}

function Get-AsPort([string]$instance) {
    # The service process of MSOLAP$<instance> is msmdsrv.exe; it listens on a dynamic port.
    $svc = Get-CimInstance Win32_Service -Filter ("Name='MSOLAP`${0}'" -f $instance) -ErrorAction SilentlyContinue
    $procId = $null
    if ($svc -and $svc.ProcessId) { $procId = $svc.ProcessId }
    else {
        $procs = @(Get-Process msmdsrv -ErrorAction SilentlyContinue)
        if ($procs.Count -eq 1) { $procId = $procs[0].Id }
    }
    if (-not $procId) { Fail "Analysis Services instance $instance is not running (no msmdsrv process)." }
    $listen = @(Get-NetTCPConnection -State Listen -OwningProcess $procId -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty LocalPort -Unique)
    if ($listen.Count -eq 0) { Fail "msmdsrv (PID $procId) has no listening TCP port." }
    return $listen[0]
}

function Get-QueryText([string]$path) {
    # Drop the '--' comment lines (header and notes); the rest is the single MDX query.
    $text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
    $lines = $text -split "`r?`n" | Where-Object { -not $_.TrimStart().StartsWith('--') }
    return (($lines -join "`n").Trim())
}

function Get-ServerErrors([string]$response) {
    $errs = @()
    foreach ($m in [regex]::Matches($response, '<Error\b[^>]*?Description="([^"]*)"')) {
        $errs += [System.Net.WebUtility]::HtmlDecode($m.Groups[1].Value)
    }
    if ($errs.Count -eq 0 -and $response -match '<Exception\b') { $errs += 'the server returned an <Exception> element' }
    return $errs
}

function Format-Number([string]$raw) {
    $d = [double]::Parse($raw, [System.Globalization.NumberStyles]::Float, $Inv)
    if ($d -eq [math]::Truncate($d) -and [math]::Abs($d) -lt 1e15) { return ([long]$d).ToString($Inv) }
    return $d.ToString('R', $Inv)
}

function ConvertTo-CsvField([string]$s) {
    if ($s -match '[",\r\n]') { return '"' + $s.Replace('"', '""') + '"' }
    return $s
}

function Convert-Result([string]$response, [string]$stem, [bool]$ranked) {
    $xml = [xml]$response
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace('md', 'urn:schemas-microsoft-com:xml-analysis:mddataset')
    $cols = @($xml.SelectNodes("//md:Axes/md:Axis[@name='Axis0']/md:Tuples/md:Tuple", $ns) |
              ForEach-Object { $_.SelectSingleNode('md:Member/md:Caption', $ns).InnerText })
    $want = if ($ranked) { @('Rank', 'Value') } else { @('Value') }
    if (($cols -join ',') -ne ($want -join ',')) {
        throw "COLUMNS axis is [$($cols -join ', ')], expected [$($want -join ', ')]"
    }
    $cells = @{}
    foreach ($c in $xml.SelectNodes('//md:CellData/md:Cell', $ns)) {
        $v = $c.SelectSingleNode('md:Value', $ns)
        if ($v -and $v.InnerText -ne '') { $cells[[int]$c.CellOrdinal] = $v.InnerText }
    }
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add(($(if ($ranked) { 'Rank,' } else { '' }) + 'Member,Value'))
    $rowTuples = $xml.SelectNodes("//md:Axes/md:Axis[@name='Axis1']/md:Tuples/md:Tuple", $ns)
    $n = $cols.Count
    $i = 0
    foreach ($t in $rowTuples) {
        $captions = @($t.SelectNodes('md:Member', $ns) | ForEach-Object { $_.SelectSingleNode('md:Caption', $ns).InnerText })
        $member = $captions -join ' | '
        $valOrd = $i * $n + ($n - 1)
        if ($cells.ContainsKey($valOrd)) {
            $line = (ConvertTo-CsvField $member) + ',' + (Format-Number $cells[$valOrd])
            if ($ranked) {
                $rank = if ($cells.ContainsKey($i * $n)) { Format-Number $cells[$i * $n] } else { '' }
                $line = $rank + ',' + $line
            }
            $lines.Add($line)
        }
        $i++
    }
    return ,$lines
}

Import-SqlServerModule
if (-not $Server) { $Server = "localhost:$(Get-AsPort $Instance)" }
Say "Analysis Services $Server, database $Database"
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$files = Get-ChildItem -Path $MdxDir -Filter '*.mdx' | Sort-Object Name
$Stem = @($Stem | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })   # -File passes 'a,b' as one string
if ($Stem.Count -gt 0) {
    $unknown = @($Stem | Where-Object { -not (Test-Path (Join-Path $MdxDir "$_.mdx")) })
    if ($unknown.Count -gt 0) { Fail "no such statement(s): $($unknown -join ', ') (expected mdx\<stem>.mdx)" }
    $files = $files | Where-Object { $Stem -contains $_.BaseName }
}
if (-not $files) { Fail 'no MDX files selected' }

$failed = @()
foreach ($f in $files) {
    $name = $f.BaseName
    $ranked = $name.StartsWith('05_rank') -or $name.StartsWith('06_top_n')
    # Remove the previous result first, so a failed run never leaves a stale CSV to compare.
    $out = Join-Path $OutDir "$name.csv"
    if (Test-Path $out) { Remove-Item -LiteralPath $out -Force }
    $query = Get-QueryText $f.FullName
    try {
        $response = [string](Invoke-ASCmd -Server $Server -Database $Database -Query $query)
    } catch {
        Say "FAIL $name : $($_.Exception.Message)"; $failed += $name; continue
    }
    $errs = @(Get-ServerErrors $response)
    if ($errs.Count -gt 0) {
        Say "FAIL $name : server rejected the statement"
        foreach ($e in $errs) { Say "    $e" }
        $failed += $name; continue
    }
    try {
        $lines = Convert-Result $response $name $ranked
    } catch {
        Say "FAIL $name : $($_.Exception.Message)"; $failed += $name; continue
    }
    [System.IO.File]::WriteAllText($out, (($lines -join "`n") + "`n"), $Utf8NoBom)
    Say ('OK   {0} ({1} rows)' -f $name, ($lines.Count - 1))
}

if ($failed.Count -gt 0) {
    Say "$($failed.Count) statement(s) failed: $($failed -join ', ')"
    exit 1
}
Say "$($files.Count) statement(s) written to mdx\results"
exit 0
