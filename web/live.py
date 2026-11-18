"""Live run of ONE stored MDX statement on the cube, for the website's "Run live on the cube" button.

The statement is run by tools/run_mdx.ps1 into a temporary folder (-OutDir), so the committed results in
mdx/results are never written or deleted. The browser can only choose a stem; it is checked against the 28
existing files and passed as an argument-list item, never as a shell string.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from . import data

SCRIPT = data.REPO / "tools" / "run_mdx.ps1"


def _run_powershell(stem: str, out_dir: str, timeout: int) -> tuple[int, str]:
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
           "-Stem", stem, "-OutDir", str(out_dir)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, cwd=str(data.REPO))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def run_live(stem: str, runner=_run_powershell, timeout: int = 60) -> dict:
    """Run `stem` on the cube and compare with the saved result.

    Returns {"ok": True, "rows", "columns", "matches_saved", "differences", "seconds"} or {"ok": False, "error"}.
    Raises ValueError for a name that is not one of the stored statements.
    """
    if not data.is_stem(stem):
        raise ValueError(f"unknown statement: {stem!r}")
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="fdw_live_") as tmp:
        try:
            code, output = runner(stem, tmp, timeout)
        except FileNotFoundError:
            return {"ok": False, "error": "PowerShell was not found on this computer, so the cube cannot be queried. "
                                          "The saved result is still shown."}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"The cube query timed out after {timeout} seconds. "
                                          "The saved result is still shown."}
        out_csv = Path(tmp) / f"{stem}.csv"
        if code != 0 or not out_csv.exists():
            last = [ln.strip() for ln in output.splitlines() if ln.strip()][-1:] or ["no details"]
            return {"ok": False, "error": "The cube could not be reached or rejected the statement "
                                          f"(is Analysis Services running?). Details: {last[0][:200]}"}
        columns, rows = data.read_result_csv(out_csv)
    differences = data.rows_equal(data.load_statement(stem)["rows"], rows)
    return {"ok": True, "columns": columns, "rows": rows, "matches_saved": not differences,
            "differences": differences, "seconds": round(time.time() - started, 2)}
