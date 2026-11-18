"""The pipeline refuses unusable raw data with a clear message and writes no output (found by the robustness test H1:
a fact table without its Price column used to end in 'KeyError: Price', a header-only one in an unrelated ValueError)."""
import shutil
from pathlib import Path

import pandas as pd
import pytest

from fdw import cli, config
from fdw.load import REQUIRED_COLUMNS, SourceDataError, load_tables

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "raw"
pytestmark = pytest.mark.skipif(not all((CACHE / f"{k}.csv").exists() for k in REQUIRED_COLUMNS),
                                reason="data/raw cache missing (run python -m fdw.cli once)")


@pytest.fixture()
def cache(tmp_path):
    d = tmp_path / "raw"
    shutil.copytree(CACHE, d)
    return d


def _load(cache, tmp_path):
    return load_tables(raw_dir=tmp_path / "nowhere", cache_dir=cache)


def test_good_cache_loads(cache, tmp_path):
    assert set(_load(cache, tmp_path)) == set(REQUIRED_COLUMNS)


@pytest.mark.parametrize("key,col", [("fact", "Price"), ("ticket", "FlightNo"), ("airport", "Ariport_y")])
def test_missing_column_is_named(cache, tmp_path, key, col):
    f = cache / f"{key}.csv"
    pd.read_csv(f, encoding="utf-8-sig").drop(columns=[col]).to_csv(f, index=False, encoding="utf-8-sig")
    with pytest.raises(SourceDataError, match=col):
        _load(cache, tmp_path)


def test_header_only_table_is_refused(cache, tmp_path):
    f = cache / "fact.csv"
    f.write_text(f.read_text(encoding="utf-8-sig").splitlines()[0] + "\n", encoding="utf-8-sig")
    with pytest.raises(SourceDataError, match="no rows"):
        _load(cache, tmp_path)


def test_missing_raw_file_is_named(tmp_path):
    with pytest.raises(SourceDataError, match="not found"):
        load_tables(raw_dir=tmp_path / "nowhere", cache_dir=tmp_path / "emptycache")


def test_cli_exit_code_2_and_no_output(cache, tmp_path, capsys):
    f = cache / "fact.csv"
    pd.read_csv(f, encoding="utf-8-sig").drop(columns=["Price"]).to_csv(f, index=False, encoding="utf-8-sig")
    out = tmp_path / "out"
    code = cli.main(["--cache-dir", str(cache), "--out-dir", str(out)])
    assert code == 2
    assert "SOURCE DATA PROBLEM" in capsys.readouterr().err
    assert not out.exists() or not any(out.iterdir())


def _write_airline_xlsx(raw_dir, names):
    d = raw_dir / config.DIM_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"AirlinesID": range(1, len(names) + 1), "airlines": names,
                  "airlinesCode": ["AA"] * len(names), "planeNumber": [1] * len(names)}).to_excel(
        d / "DW_Dim_Airlines.xlsx", index=False)
    return d / "DW_Dim_Airlines.xlsx"


def test_stale_cache_is_rebuilt_when_the_excel_file_is_newer(tmp_path):
    import os
    from fdw.load import _read_one
    raw, cache = tmp_path / "raw", tmp_path / "cache"
    xlsx = _write_airline_xlsx(raw, ["old one", "old two"])
    assert list(_read_one("airline", raw, cache)["airlines"]) == ["old one", "old two"]
    _write_airline_xlsx(raw, ["new one", "new two", "new three"])
    later = (cache / "airline.csv").stat().st_mtime + 10
    os.utime(xlsx, (later, later))
    assert list(_read_one("airline", raw, cache)["airlines"]) == ["new one", "new two", "new three"]


def test_cache_is_used_when_it_is_newer_than_the_excel_file(tmp_path):
    import os
    from fdw.load import _read_one
    raw, cache = tmp_path / "raw", tmp_path / "cache"
    xlsx = _write_airline_xlsx(raw, ["kept"])
    _read_one("airline", raw, cache)
    earlier = (cache / "airline.csv").stat().st_mtime - 10
    os.utime(xlsx, (earlier, earlier))
    _write_airline_xlsx(raw, ["changed"])
    os.utime(xlsx, (earlier, earlier))
    assert list(_read_one("airline", raw, cache)["airlines"]) == ["kept"]
