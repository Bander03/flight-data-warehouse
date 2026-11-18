"""Live run of one stored statement (web/live.py): safe, never touches the committed results, friendly errors."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from web import data, live  # noqa: E402

STEM = "05_rank_1"
SAVED = REPO / "mdx" / "results" / f"{STEM}.csv"


def _copy_saved(stem, out_dir, timeout):
    (Path(out_dir) / f"{stem}.csv").write_bytes(SAVED.read_bytes())
    return 0, f"OK   {stem}"


def test_live_equal_to_saved():
    r = live.run_live(STEM, runner=_copy_saved)
    assert r["ok"] is True and r["matches_saved"] is True and r["differences"] == []
    assert r["rows"] == data.load_statement(STEM)["rows"] and r["seconds"] >= 0


def test_live_changed_value_is_reported():
    def changed(stem, out_dir, timeout):
        text = SAVED.read_text(encoding="utf-8").replace("699600", "700000")
        (Path(out_dir) / f"{stem}.csv").write_text(text, encoding="utf-8")
        return 0, "OK"
    r = live.run_live(STEM, runner=changed)
    assert r["ok"] is True and r["matches_saved"] is False
    assert any("中国东方航空" in d for d in r["differences"])


def test_cube_failure_is_friendly():
    r = live.run_live(STEM, runner=lambda s, o, t: (1, "ERROR: Analysis Services instance DEV is not running"))
    assert r["ok"] is False and "cube" in r["error"].lower() and "Traceback" not in r["error"]


def test_powershell_missing_is_friendly():
    def missing(s, o, t):
        raise FileNotFoundError("powershell")
    r = live.run_live(STEM, runner=missing)
    assert r["ok"] is False and "PowerShell" in r["error"]


def test_timeout_is_friendly():
    def slow(s, o, t):
        raise subprocess.TimeoutExpired("powershell", t)
    r = live.run_live(STEM, runner=slow)
    assert r["ok"] is False and "timed out" in r["error"]


def test_runner_that_writes_nothing_is_friendly():
    r = live.run_live(STEM, runner=lambda s, o, t: (0, "OK"))
    assert r["ok"] is False


@pytest.mark.parametrize("bad", ["", "../x", "nope", "05_rank_1;calc"])
def test_unknown_stem_raises(bad):
    with pytest.raises(ValueError):
        live.run_live(bad, runner=_copy_saved)


def test_saved_results_unchanged():
    before = hashlib.sha256(SAVED.read_bytes()).hexdigest()
    live.run_live(STEM, runner=_copy_saved)
    assert hashlib.sha256(SAVED.read_bytes()).hexdigest() == before


def test_real_runner_uses_argument_list(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    live._run_powershell(STEM, "C:/tmp/out", 5)
    assert isinstance(seen["cmd"], list) and seen["kw"].get("shell") in (None, False)
    assert seen["cmd"][-4:] == ["-Stem", STEM, "-OutDir", "C:/tmp/out"] and seen["kw"]["timeout"] == 5
