import pandas as pd
import pytest

from fdw import config
from fdw.load import load_tables

KEYS = {"fact", "ticket", "passenger", "airport", "airline", "plane",
        "seat", "price_range", "date"}


@pytest.fixture(scope="module")
def tables():
    # first run reads the 20 MB ticket xlsx (slow); later runs hit the CSV cache
    return load_tables()


def test_keys(tables):
    assert set(tables) == KEYS


def test_row_counts(tables):
    expected = {"fact": 600, "ticket": 568917, "airline": 18, "airport": 184,
                "plane": 18, "price_range": 30, "seat": 1353, "date": 365}
    for key, n in expected.items():
        assert len(tables[key]) == n, key


def test_chinese_text_preserved(tables):
    assert tables["airline"].airlines.iloc[0] == "中国国际航空"


def test_ffp_tier_renamed(tables):
    cols = tables["passenger"].columns
    assert "FFP_TIER" in cols
    assert not any("会员卡级别" in c for c in cols)


def test_plane_nullable_int(tables):
    assert tables["fact"].PlaneID.dtype == "Int64"
    assert tables["fact"].ian.dtype == "Int64"
    assert tables["fact"].Transit_ariportID.dtype == "Int64"
    assert tables["fact"].Transit_ariportID.isna().all()


def test_cache_roundtrip(tables, tmp_path):
    cache = tmp_path / "cache"
    first = load_tables(cache_dir=cache)
    assert (cache / "fact.csv").exists()
    # file must be UTF-8 with BOM
    assert (cache / "airline.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    second = load_tables(raw_dir=tmp_path / "missing", cache_dir=cache)  # raises if the cache is bypassed
    for key in KEYS:
        pd.testing.assert_frame_equal(first[key], second[key])
        pd.testing.assert_frame_equal(first[key], tables[key])


def test_config_constants():
    assert config.CACHE_DIR == config.ROOT / "data" / "raw"
    assert config.OUT_DIR == config.ROOT / "data" / "processed"
    assert config.SEED == 20261112
    assert config.HUBS["CA"] == ["PEK", "CTU"]
    assert abs(sum(config.CABIN_MIX.values()) - 1.0) < 1e-9
    assert config.RAW_DIR.is_dir()
