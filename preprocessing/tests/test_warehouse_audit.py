"""Runs sql/98_independent_audit.sql on the built warehouse (read-only) and proves that the audit can fail.

Skipped when sqlcmd, the instance or a loaded FlightDW (600 fact rows) is missing, so it never builds anything.
The mutation tests change one value inside a transaction that is always rolled back.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SQLCMD = shutil.which("sqlcmd")
INSTANCE = os.environ.get("FDW_SQL_INSTANCE", r"localhost\SQLEXPRESS")


def _sqlcmd(*args, timeout=120):
    return subprocess.run([SQLCMD, "-S", INSTANCE, "-E", "-b", "-f", "65001", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=REPO)


@pytest.fixture(scope="module")
def warehouse():
    if SQLCMD is None:
        pytest.skip("sqlcmd not on PATH")
    try:
        r = _sqlcmd("-h", "-1", "-W", "-Q", "SET NOCOUNT ON; SELECT COUNT(*) FROM FlightDW.dw.Fact_FlightSegment", timeout=30)
    except subprocess.TimeoutExpired:
        pytest.skip("SQL Server instance not reachable")
    if r.returncode != 0 or r.stdout.strip() != "600":
        pytest.skip("FlightDW is not loaded (600 fact rows expected)")


def test_audit_passes_on_the_loaded_warehouse(warehouse):
    r = _sqlcmd("-i", str(REPO / "sql" / "98_independent_audit.sql"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL AUDIT CHECKS PASSED" in r.stdout
    assert r.stdout.count("PASS:") == 22


MUTATIONS = {
    "1": "UPDATE dw.Fact_FlightSegment SET Mileage = Mileage + 50 WHERE SegmentID = (SELECT MIN(SegmentID) FROM dw.Fact_FlightSegment);",
    "2": "UPDATE dw.Fact_FlightSegment SET HasStopover = 1 - HasStopover WHERE SegmentID = (SELECT MIN(SegmentID) FROM dw.Fact_FlightSegment);",
    "6": "UPDATE dw.Fact_FlightSegment SET ArrivalDateKey = (SELECT MIN(DateKey) FROM dw.DimDate) WHERE SegmentID = (SELECT MAX(SegmentID) FROM dw.Fact_FlightSegment);",
    "7": "UPDATE dw.Fact_FlightSegment SET Price = 999999 WHERE SegmentID = (SELECT MIN(SegmentID) FROM dw.Fact_FlightSegment);",
}


@pytest.mark.parametrize("check", sorted(MUTATIONS))
def test_audit_detects_a_corrupted_row(warehouse, check):
    audit = (REPO / "sql" / "98_independent_audit.sql").read_text(encoding="utf-8")
    script = f"USE FlightDW;\nGO\nBEGIN TRAN;\n{MUTATIONS[check]}\nGO\n{audit}\nGO\nIF @@TRANCOUNT > 0 ROLLBACK;\nGO\n"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "mutation.sql"
        f.write_text(script, encoding="utf-8")
        r = _sqlcmd("-i", str(f))
    assert r.returncode != 0
    assert f"AUDIT FAILED {check}" in r.stdout
    after = _sqlcmd("-h", "-1", "-W", "-Q", "SET NOCOUNT ON; SELECT SUM(Price) FROM FlightDW.dw.Fact_FlightSegment")
    assert after.stdout.strip() == "1400460", "the mutation was not rolled back"
