import hashlib

import pandas as pd
import pytest

from fdw import config
from fdw.pipeline import run

CSV_FILES = ["fact_flight_segment.csv", "dim_ticket.csv", "dim_passenger.csv",
             "dim_airport.csv", "dim_airline.csv", "dim_plane.csv", "dim_seat.csv",
             "dim_price_range.csv", "dim_date.csv"]
ALL_FILES = CSV_FILES + ["profile_before_after.md"]
FACT_COLUMNS = ["PriceRangeID", "Departure_ariportID", "Transit_ariportID",
                "Landing_ariportID", "DepartureDateID", "ArrivalDateID", "PassengerID",
                "TicketID", "PlaneID", "CabinID", "mileage", "Price", "Rate", "ian"]


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("processed")
    rules = run(config.RAW_DIR, out_dir, config.SEED)
    return rules, out_dir


def _fact_text(out_dir):
    return pd.read_csv(out_dir / "fact_flight_segment.csv", encoding="utf-8-sig",
                       dtype=str, keep_default_na=False)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_passes_all_rules(result):
    rules, _ = result
    assert len(rules) == 17
    assert all(r.passed for r in rules), [r for r in rules if not r.passed]


def test_all_output_files_written_with_bom(result):
    _, out_dir = result
    for name in ALL_FILES:
        assert (out_dir / name).is_file(), name
    for name in CSV_FILES:
        assert (out_dir / name).read_bytes().startswith(b"\xef\xbb\xbf"), name


def test_row_count_600(result):
    _, out_dir = result
    fact = _fact_text(out_dir)
    assert len(fact) == 600
    assert list(fact.columns) == FACT_COLUMNS


def test_csv_clean_integers(result):
    _, out_dir = result
    fact = _fact_text(out_dir)
    for col in FACT_COLUMNS:
        if col in ("Rate", "Transit_ariportID"):
            continue
        assert fact[col].str.fullmatch(r"\d+").all(), col      # no '.0', no blanks
    assert fact["Rate"].str.fullmatch(r"\d\.\d{1,2}").all()   # no 0.719999999999999
    raw = (out_dir / "fact_flight_segment.csv").read_text(encoding="utf-8-sig")
    for bad in ("nan", "NaN", "<NA>", "None"):
        assert bad not in raw, bad
    for name in CSV_FILES[1:]:
        text = (out_dir / name).read_text(encoding="utf-8-sig")
        assert "<NA>" not in text, name
    age = pd.read_csv(out_dir / "dim_passenger.csv", encoding="utf-8-sig", dtype=str,
                      keep_default_na=False)["PassengerAge"]
    assert not age.str.endswith(".0").any()


def test_stopover_cells_are_empty_not_nan(result):
    _, out_dir = result
    transit = _fact_text(out_dir)["Transit_ariportID"]
    stops = transit[transit != ""]
    assert len(stops) >= 20 and stops.str.fullmatch(r"\d+").all()
    assert (transit == "").sum() == 600 - len(stops)
    assert (transit == "").sum() > 0
    raw_lines = (out_dir / "fact_flight_segment.csv").read_text(encoding="utf-8-sig").splitlines()
    assert any(",," in line for line in raw_lines[1:])


def test_dimension_contents(result):
    _, out_dir = result
    ticket = pd.read_csv(out_dir / "dim_ticket.csv", encoding="utf-8-sig")
    assert "IsSupplemented" in ticket.columns
    assert ticket["IsSupplemented"].sum() == 240
    assert len(ticket) == 568917 + 240
    assert len(pd.read_csv(out_dir / "dim_passenger.csv", encoding="utf-8-sig")) == 62044
    assert len(pd.read_csv(out_dir / "dim_airport.csv", encoding="utf-8-sig")) == 184


def test_profile_written(result):
    _, out_dir = result
    text = (out_dir / "profile_before_after.md").read_text(encoding="utf-8")
    assert "before" in text.lower() and "after" in text.lower()
    assert "departure_airports_ge_20" in text
    assert "8871" in text                                   # remapped passenger rows
    assert "clipped" in text.lower()
    assert "nan" not in text.lower() and "<NA>" not in text


def test_profile_reports_clipping_per_class(result):
    _, out_dir = result
    text = (out_dir / "profile_before_after.md").read_text(encoding="utf-8")
    section = text.split("## Price clipping", 1)[1].split("\n## ", 1)[0]
    rows = {line.split("|")[1].strip(): line.split("|")[2].strip()
            for line in section.splitlines() if line.startswith("|")}
    for k in ("F", "C", "Y", "All"):
        assert k in rows, rows
    assert rows["All"] == "0"                               # the clip is only a safety net


def test_profile_header_uses_the_run_seed(valid_tables):
    from fdw.pipeline import _profile
    from fdw.validate import validate_fact
    rules = validate_fact(valid_tables)
    text = _profile(valid_tables, valid_tables, valid_tables, rules, rules, seed=123)
    header = text.split("\n## ", 1)[0]
    assert "seed 123" in header
    assert str(config.SEED) not in header


def test_profile_has_no_airports_without_code(result):
    _, out_dir = result
    text = (out_dir / "profile_before_after.md").read_text(encoding="utf-8")
    assert "no code" not in text


def test_profile_has_ten_sample_rows_with_codes(result):
    _, out_dir = result
    text = (out_dir / "profile_before_after.md").read_text(encoding="utf-8")
    section = text.split("## Sample fact rows", 1)[1].split("\n## ", 1)[0]
    data_rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    assert len(data_rows) == 10


def test_deterministic_output(result, tmp_path_factory):
    _, first = result
    second = tmp_path_factory.mktemp("processed2")
    run(config.RAW_DIR, second, config.SEED)
    for name in ALL_FILES:
        assert _sha(first / name) == _sha(second / name), name


def test_cli_prints_rules_and_returns_zero(tmp_path, capsys, monkeypatch):
    from fdw import cli
    from fdw.validate import RuleResult
    monkeypatch.setattr(cli, "run", lambda *a, **k: [RuleResult("r1", True, "ok")] * 17)
    assert cli.main(["--out-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.count("[PASS]") == 17 and "17/17" in out


def test_cli_exit_code_1_on_validation_error(tmp_path, capsys, monkeypatch):
    from fdw import cli
    from fdw.validate import ValidationError

    def boom(*a, **k):
        raise ValidationError("1 rule(s) failed: x is bad")
    monkeypatch.setattr(cli, "run", boom)
    assert cli.main(["--out-dir", str(tmp_path)]) == 1
    assert "x is bad" in capsys.readouterr().err
