import pandas as pd
import pytest

from fdw.geo import airport_distance_km, haversine_km
from fdw.load import load_tables


@pytest.fixture(scope="module")
def tables():
    return load_tables()


def test_pek_sha_distance(tables):
    d = airport_distance_km(tables["airport"], 74, 22)
    assert 1000 < d < 1150


def test_zero_distance():
    assert haversine_km(31.2, 121.8, 31.2, 121.8) == 0.0


def test_symmetric():
    a = haversine_km(40.08, 116.58, 31.2, 121.8)
    b = haversine_km(31.2, 121.8, 40.08, 116.58)
    assert a == pytest.approx(b)


def test_airport_distance_uses_lat_lon_columns():
    airport = pd.DataFrame(
        {"AirportID": [1, 2], "Ariport_X": [0.0, 90.0], "Ariport_y": [0.0, 0.0]}
    )
    # 90 degrees of longitude on the equator = quarter of the great circle
    assert airport_distance_km(airport, 1, 2) == pytest.approx(
        6371 * 3.141592653589793 / 2
    )
