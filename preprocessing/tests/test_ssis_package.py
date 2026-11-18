"""Static checks of the generated SSIS package ssis/FlightDWLoad/LoadFlightDW.dtsx.

Running the package (dtexec) drops and rebuilds FlightDW, so it is not part of the test run; these tests
pin its structure: seven tasks in the documented order, a strict chain of precedence constraints,
every task fails the package on a non-zero exit code, and the generator output equals the committed file.
"""
import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DTSX = REPO / "ssis" / "FlightDWLoad" / "LoadFlightDW.dtsx"
DTS = "{www.microsoft.com/SqlServer/Dts}"

ORDER = ["Copy CSVs to DataDir", "01 create database", "02 staging tables", "03 star schema",
         "04 load", "99 checks", "05 grant cube read"]
SCRIPTS = ["01_create_db.sql", "02_stg_tables.sql", "03_dw_tables.sql", "04_load.sql",
           "99_checks.sql", "05_grant_ssas_read.sql"]


def _gen():
    spec = importlib.util.spec_from_file_location("build_ssis_package", REPO / "tools" / "build_ssis_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _root():
    return ET.parse(DTSX).getroot()


def test_file_equals_generator_output():
    assert DTSX.read_text(encoding="utf-8") == _gen().build()


def test_package_has_no_personal_or_absolute_repo_path():
    """RepoDir is relative ('.'): the package runs from the repository root of any clone."""
    text = DTSX.read_text(encoding="utf-8")
    assert "Users" not in text and "Desktop" not in text
    repo_dir = next(v.find(DTS + "VariableValue").text for v in _root().find(DTS + "Variables")
                    if v.get(DTS + "ObjectName") == "RepoDir")
    assert repo_dir == "."


def test_seven_tasks_in_order():
    names = [e.get(DTS + "ObjectName") for e in _root().find(DTS + "Executables")]
    assert names == ORDER


def test_chain_of_precedence_constraints():
    pcs = [(c.get(DTS + "From"), c.get(DTS + "To"))
           for c in _root().find(DTS + "PrecedenceConstraints")]
    assert pcs == [("Package\\" + a, "Package\\" + b) for a, b in zip(ORDER, ORDER[1:])]


def test_every_task_fails_the_package_on_nonzero_exit():
    for e in _root().find(DTS + "Executables"):
        data = e.find(DTS + "ObjectData")[0]
        assert data.get("FailTaskIfReturnCodeIsNotSuccessValue") == "True"
        assert data.get("SuccessValue") == "0"


def test_each_sql_script_is_called_once_with_sqlcmd():
    execs = list(_root().find(DTS + "Executables"))
    for e, script in zip(execs[1:], SCRIPTS):
        data = e.find(DTS + "ObjectData")[0]
        assert data.get("Executable") == "sqlcmd.exe"
        assert script in data.get("Arguments")
        assert "-b" in data.get("Arguments").split()           # sqlcmd must return non-zero on error
        expr = e.find(DTS + "PropertyExpression").text
        assert "@[User::SqlInstance]" in expr and "@[User::RepoDir]" in expr and script in expr


def test_load_task_passes_datadir_and_other_tasks_do_not():
    for e in _root().find(DTS + "Executables"):
        args = e.find(DTS + "ObjectData")[0].get("Arguments")
        assert ("-v DataDir=" in args) == (e.get(DTS + "ObjectName") == "04 load")


def test_variables_and_scripts_exist():
    vars_ = {v.get(DTS + "ObjectName") for v in _root().find(DTS + "Variables")}
    assert vars_ == {"RepoDir", "DataDir", "SqlInstance"}
    for s in SCRIPTS:
        assert (REPO / "sql" / s).exists()
