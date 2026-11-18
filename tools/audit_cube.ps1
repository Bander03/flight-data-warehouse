# audit_cube.ps1: independent, read-only audit of the deployed cube FlightCube against the warehouse FlightDW.
# Windows PowerShell 5.1. Every expected value comes from a T-SQL query on FlightDW (sqlcmd), every actual value from an
# MDX query on FlightCube (Invoke-ASCmd, raw cell values). Checks:
#   D1  every measure, summed over the members of every one of the 10 cube dimensions, equals the grand total
#   D2  role-playing: each date and airport role, member by member, equals the SQL group-by of its own foreign key
#   D3  calculated members (Average Price, Average Rate, Stopover Share) and Distinct Passengers per airline equal SQL,
#       and the airlines without segments return an empty cell (no error cell)
#   D4  Distinct Passengers is not additive: the sum over airlines is larger than the cube total, which stays 599
#   D5  the 'No stopover' member carries the 505 direct segments on Transit Airport and none on the other airport roles
#   C6  Chinese captions: airport, airline and plane captions in the cube equal the warehouse names, character by character
# Usage (repo root):  powershell -File tools\audit_cube.ps1        Exit code 0 = all checks pass, 1 = at least one failed.
param([string]$Instance = 'DEV', [string]$SqlInstance = 'localhost\SQLEXPRESS')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Inv = [System.Globalization.CultureInfo]::InvariantCulture
try { Import-Module SqlServer -DisableNameChecking -ErrorAction Stop } catch {
    $cand = @(Get-ChildItem (Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Modules\SqlServer') -Filter SqlServer.psd1 -Recurse |
              Sort-Object { [version]$_.Directory.Name } -Descending)
    Import-Module $cand[0].FullName -DisableNameChecking
}
$svc = Get-CimInstance Win32_Service -Filter ("Name='MSOLAP`${0}'" -f $Instance)
$port = (Get-NetTCPConnection -State Listen -OwningProcess $svc.ProcessId | Select-Object -ExpandProperty LocalPort -Unique)[0]
$Server = "localhost:$port"
$script:fail = 0
$script:pass = 0
function Say([string]$m) { [Console]::Out.WriteLine($m) }
function Check([string]$id, [bool]$ok, [string]$detail) {
    if ($ok) { $script:pass++; Say "PASS $id $detail" } else { $script:fail++; Say "FAIL $id $detail" }
}

function Invoke-Sql([string]$q) {
    # rows as arrays of strings; columns separated by TAB
    $out = & sqlcmd -S $SqlInstance -E -d FlightDW -f 65001 -h -1 -W -s "`t" -Q "SET NOCOUNT ON; $q" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "sqlcmd failed: $out" }
    $rows = @()
    foreach ($l in $out) { $s = [string]$l; if ($s.Trim() -ne '') { $rows += , @($s -split "`t") } }
    return , $rows
}

function Invoke-Mdx([string]$q) {
    # returns @{ Rows = list of @{ Captions = string[]; Cells = double?[] (null for empty) ; Errors = int } }
    $resp = [string](Invoke-ASCmd -Server $Server -Database FlightCube -Query $q)
    if ($resp -match '<Error\b|<Exception\b') { throw "MDX rejected: $q" }
    $xml = [xml]$resp
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace('md', 'urn:schemas-microsoft-com:xml-analysis:mddataset')
    $ncol = @($xml.SelectNodes("//md:Axes/md:Axis[@name='Axis0']/md:Tuples/md:Tuple", $ns)).Count
    $cells = @{}
    $errCells = @{}
    foreach ($c in $xml.SelectNodes('//md:CellData/md:Cell', $ns)) {
        $o = [int]$c.CellOrdinal
        $v = $c.SelectSingleNode('md:Value', $ns)
        if ($v -and $v.InnerText -ne '' -and $v.GetAttribute('xsi:type') -ne $null -and $v.InnerXml -match '<Error') { $errCells[$o] = 1 }
        elseif ($v -and $v.InnerText -ne '') { $cells[$o] = $v.InnerText }
    }
    $rows = New-Object System.Collections.Generic.List[object]
    $i = 0
    foreach ($t in $xml.SelectNodes("//md:Axes/md:Axis[@name='Axis1']/md:Tuples/md:Tuple", $ns)) {
        $caps = @($t.SelectNodes('md:Member', $ns) | ForEach-Object { $_.SelectSingleNode('md:Caption', $ns).InnerText })
        $vals = @()
        for ($k = 0; $k -lt $ncol; $k++) {
            $o = $i * $ncol + $k
            if ($cells.ContainsKey($o)) { $vals += [double]::Parse($cells[$o], [System.Globalization.NumberStyles]::Float, $Inv) } else { $vals += $null }
        }
        $rows.Add(@{ Captions = $caps; Cells = $vals })
        $i++
    }
    return ,$rows
}

# ---- grand totals from SQL
$tot = (Invoke-Sql "SELECT COUNT(*), SUM(CAST(Price AS BIGINT)), SUM(CAST(Mileage AS BIGINT)), SUM(CAST(HasStopover AS INT)), COUNT(DISTINCT PassengerKey) FROM dw.Fact_FlightSegment")[0]
$T = @([double]$tot[0], [double]$tot[1], [double]$tot[2], [double]$tot[3])
$TP = [double]$tot[4]
Check 'D0' (($T -join ',') -eq '600,1400460,1001283,95' -and $TP -eq 599) "SQL totals $($T -join ' / '), $TP distinct passengers"

# ---- D1 every dimension adds up
$meas = '{[Measures].[Segment Count],[Measures].[Total Price],[Measures].[Total Mileage],[Measures].[Stopover Segments]}'
$dims = @(
    @('Departure Date', 'Day'), @('Arrival Date', 'Day'), @('Passenger', 'Passenger'), @('Departure Airport', 'Airport'),
    @('Transit Airport', 'Airport'), @('Landing Airport', 'Airport'), @('Flight', 'Ticket'), @('Plane', 'Plane Model'),
    @('Cabin', 'Seat'), @('Price Range', 'Price Grade'))
foreach ($d in $dims) {
    $rows = Invoke-Mdx "SELECT $meas ON 0, NON EMPTY [$($d[0])].[$($d[1])].[$($d[1])].Members ON 1 FROM [FlightCube]"
    $sum = @(0.0, 0.0, 0.0, 0.0)
    foreach ($r in $rows) { for ($k = 0; $k -lt 4; $k++) { if ($null -ne $r.Cells[$k]) { $sum[$k] += $r.Cells[$k] } } }
    Check "D1 $($d[0])" (($sum -join ',') -eq ($T -join ',')) "$($rows.Count) members add up to $($sum -join ' / ')"
}

# ---- D2 role-playing, member by member against SQL
function Compare-Role([string]$id, [string]$dim, [string]$attr, [string]$sqlSelect) {
    $m = @{}
    foreach ($r in (Invoke-Mdx "SELECT {[Measures].[Segment Count]} ON 0, NON EMPTY [$dim].[$attr].[$attr].Members ON 1 FROM [FlightCube]")) { $m[$r.Captions[0]] = [double]$r.Cells[0] }
    $s = @{}
    foreach ($r in (Invoke-Sql $sqlSelect)) { $s[$r[0]] = [double]$r[1] }
    $bad = @($s.Keys | Where-Object { -not $m.ContainsKey($_) -or $m[$_] -ne $s[$_] }) + @($m.Keys | Where-Object { -not $s.ContainsKey($_) })
    Check $id ($bad.Count -eq 0) "$dim by $attr : $($m.Count) members (cube) vs $($s.Count) groups (SQL), $($bad.Count) differences"
}
Compare-Role 'D2 departure date' 'Departure Date' 'Day' "SELECT CONVERT(CHAR(10), d.FullDate, 120), COUNT(*) FROM dw.Fact_FlightSegment f JOIN dw.DimDate d ON d.DateKey = f.DepartureDateKey GROUP BY d.FullDate"
Compare-Role 'D2 arrival date' 'Arrival Date' 'Day' "SELECT CONVERT(CHAR(10), d.FullDate, 120), COUNT(*) FROM dw.Fact_FlightSegment f JOIN dw.DimDate d ON d.DateKey = f.ArrivalDateKey GROUP BY d.FullDate"
Compare-Role 'D2 departure airport' 'Departure Airport' 'Airport' "SELECT a.AirportName, COUNT(*) FROM dw.Fact_FlightSegment f JOIN dw.DimAirport a ON a.AirportKey = f.DepartureAirportKey GROUP BY a.AirportName"
Compare-Role 'D2 landing airport' 'Landing Airport' 'Airport' "SELECT a.AirportName, COUNT(*) FROM dw.Fact_FlightSegment f JOIN dw.DimAirport a ON a.AirportKey = f.LandingAirportKey GROUP BY a.AirportName"
Compare-Role 'D2 transit airport' 'Transit Airport' 'Airport' "SELECT a.AirportName, COUNT(*) FROM dw.Fact_FlightSegment f JOIN dw.DimAirport a ON a.AirportKey = f.TransitAirportKey GROUP BY a.AirportName"
$dd = (Invoke-Sql "SELECT COUNT(*) FROM dw.Fact_FlightSegment f WHERE f.DepartureDateKey <> f.ArrivalDateKey")[0][0]
Check 'D2 date roles differ' ([int]$dd -gt 0) "$dd segments arrive on another day than they depart, so the two date roles are not interchangeable"

# ---- D3 calculated members and distinct passengers per airline, empty cells for airlines without segments
$rows = Invoke-Mdx "SELECT {[Measures].[Segment Count],[Measures].[Average Price],[Measures].[Average Rate],[Measures].[Stopover Share],[Measures].[Distinct Passengers]} ON 0, [Flight].[Airline].[Airline].Members ON 1 FROM [FlightCube]"
$sql = @{}
foreach ($r in (Invoke-Sql "SELECT a.AirlineName, COUNT(*), CAST(AVG(CAST(f.Price AS FLOAT)) AS DECIMAL(18,6)), CAST(AVG(CAST(f.Rate AS FLOAT)) AS DECIMAL(18,6)), CAST(SUM(CAST(f.HasStopover AS FLOAT))/COUNT(*) AS DECIMAL(18,6)), COUNT(DISTINCT f.PassengerKey) FROM dw.Fact_FlightSegment f JOIN dw.DimTicket t ON t.TicketKey = f.TicketKey JOIN dw.DimAirline a ON a.AirlineKey = t.AirlineKey GROUP BY a.AirlineName")) { $sql[$r[0]] = @($r[1..5] | ForEach-Object { [double]::Parse($_, $Inv) }) }
$bad = 0; $empty = 0; $distSum = 0.0
foreach ($r in $rows) {
    $name = $r.Captions[0]
    if ($sql.ContainsKey($name)) {
        for ($k = 0; $k -lt 5; $k++) { if ($null -eq $r.Cells[$k] -or [math]::Abs($r.Cells[$k] - $sql[$name][$k]) -gt 1e-4) { $bad++; Say "   mismatch $name col $k : cube $($r.Cells[$k]) sql $($sql[$name][$k])" } }
        $distSum += $r.Cells[4]
    } else {
        if ($null -ne $r.Cells[0] -and $r.Cells[0] -ne 0) { $bad++; Say "   $name has segments in the cube but not in SQL" }
        if ($null -eq $r.Cells[1] -and $null -eq $r.Cells[2] -and $null -eq $r.Cells[3]) { $empty++ } else { $bad++; Say "   $name (no segments) shows a value for a ratio measure" }
    }
}
Check 'D3 calculated members' ($bad -eq 0) "$($sql.Count) airlines with data equal SQL (segments, average price, average rate, stopover share, distinct passengers); $empty airlines without segments return empty ratio cells"
Check 'D3 airline count' ($rows.Count -eq 18 -and $empty -eq 7) "$($rows.Count) airline members, $empty without segments (11 have data)"

# ---- D4 Distinct Passengers is a distinct count: the cube total counts each passenger once, and every grouping equals SQL
$cell = [string](Invoke-ASCmd -Server $Server -Database FlightCube -Query "SELECT {[Measures].[Distinct Passengers]} ON 0 FROM [FlightCube]")
$m = [regex]::Match($cell, '<Value[^>]*>([0-9.]+)</Value>')
Check 'D4 cube total' ($m.Success -and [double]$m.Groups[1].Value -eq $TP) "cube Distinct Passengers = $($m.Groups[1].Value), SQL COUNT(DISTINCT PassengerKey) = $TP"
foreach ($g in @(@('Flight', 'Ticket', 'TicketKey'), @('Cabin', 'Cabin Class', $null), @('Departure Date', 'Month', $null))) {
    if ($g[1] -eq 'Ticket') { $q = "SELECT SUM(n) FROM (SELECT COUNT(DISTINCT PassengerKey) AS n FROM dw.Fact_FlightSegment GROUP BY TicketKey) x" }
    elseif ($g[1] -eq 'Cabin Class') { $q = "SELECT SUM(n) FROM (SELECT COUNT(DISTINCT f.PassengerKey) AS n FROM dw.Fact_FlightSegment f JOIN dw.DimSeat s ON s.CabinKey = f.CabinKey GROUP BY s.CabinClass) x" }
    else { $q = "SELECT SUM(n) FROM (SELECT COUNT(DISTINCT f.PassengerKey) AS n FROM dw.Fact_FlightSegment f JOIN dw.DimDate d ON d.DateKey = f.DepartureDateKey GROUP BY d.YearMonth) x" }
    $exp = [double](Invoke-Sql $q)[0][0]
    $act = 0.0
    foreach ($r in (Invoke-Mdx "SELECT {[Measures].[Distinct Passengers]} ON 0, NON EMPTY [$($g[0])].[$($g[1])].[$($g[1])].Members ON 1 FROM [FlightCube]")) { if ($null -ne $r.Cells[0]) { $act += $r.Cells[0] } }
    Check "D4 distinct by $($g[1])" ($act -eq $exp) "sum of the group counts: cube $act, SQL $exp (grand total $TP; the difference to the total shows the double count)"
}

# ---- D5 No stopover member
$rows = Invoke-Mdx "SELECT {[Measures].[Segment Count]} ON 0, {[Transit Airport].[Airport].&[0]} ON 1 FROM [FlightCube]"
Check 'D5 transit No stopover' ($rows.Count -eq 1 -and $rows[0].Captions[0] -eq 'No stopover' -and $rows[0].Cells[0] -eq 505) "member '$($rows[0].Captions[0])' carries $($rows[0].Cells[0]) direct segments"
foreach ($role in 'Departure Airport', 'Landing Airport') {
    $rows = Invoke-Mdx "SELECT {[Measures].[Segment Count]} ON 0, {[$role].[Airport].&[0]} ON 1 FROM [FlightCube]"
    Check "D5 $role" ($rows.Count -eq 1 -and $null -eq $rows[0].Cells[0]) "'No stopover' is empty as a $role"
}

# ---- C6 captions equal the warehouse names, code point by code point
function Compare-Captions([string]$id, [string]$dim, [string]$attr, [string]$sqlSelect) {
    $c = @((Invoke-Mdx "SELECT {[Measures].[Segment Count]} ON 0, [$dim].[$attr].[$attr].Members ON 1 FROM [FlightCube]") | ForEach-Object { $_.Captions[0] } | Where-Object { $_ -ne 'All' })
    $s = @((Invoke-Sql $sqlSelect) | ForEach-Object { $_[0] })
    $diff = @(Compare-Object ($c | Sort-Object { [string]$_ } ) ($s | Sort-Object { [string]$_ }) -CaseSensitive)
    $nonAscii = @($c | Where-Object { $_ -match '[^\u0000-\u007F]' }).Count
    $q = @($c | Where-Object { $_ -match '\?|�' }).Count
    Check $id ($diff.Count -eq 0 -and $q -eq 0) "$($c.Count) cube captions equal $($s.Count) warehouse names ($nonAscii non-ASCII, $q with ? or U+FFFD)"
}
Compare-Captions 'C6 airports' 'Landing Airport' 'Airport' "SELECT AirportName FROM dw.DimAirport"
Compare-Captions 'C6 airlines' 'Flight' 'Airline' "SELECT AirlineName FROM dw.DimAirline"
Compare-Captions 'C6 planes' 'Plane' 'Plane Model' "SELECT PlaneModel FROM dw.DimPlane"

Say ''
Say "$($script:pass) passed, $($script:fail) failed"
if ($script:fail -gt 0) { exit 1 }
exit 0
