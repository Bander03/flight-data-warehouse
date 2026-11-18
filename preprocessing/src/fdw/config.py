"""Paths, constants and thresholds shared by the pipeline."""
from pathlib import Path

# repo root = parents[3] of preprocessing/src/fdw/config.py
ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "0 2026_DW project_data set_1 Fact+ 8 Dim for 1 Group"
CACHE_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

FACT_FILE = "fact table group_2.xlsx"
DIM_SUBDIR = "维表（8个）"

SEED = 20261112

# guide #2 thresholds
MIN_DEP = 20
MIN_LAND = 20
MIN_STOP_ROWS = 20
MIN_PASSENGERS = 50
MIN_MONTHS = 6
MIN_AIRLINES = 10
TARGET_AIRLINES = 11

# stopover generation
STOP_SHARE = 0.15
DETOUR_MAX = 1.25
MIN_STOP_KM = 150
MIN_STOPOVER_ROUTE_KM = 900     # only routes with a direct distance >= this get a stopover

CABIN_MIX = {"Y": 0.70, "C": 0.22, "F": 0.08}
MIN_PREMIUM_CABIN_SEATS = 100   # F and C cabins only on planes with >= this many seats

# full-fare model: full_fare(class, km) = anchor[class] x (km / FARE_REF_KM) ** FARE_DISTANCE_ALPHA
# anchor[Y], anchor[C] = source median of Price / Rate per class (the source mileage is 1178 km on
# every row); anchor[F] = F_OVER_C x anchor[C]. ALPHA < 1 tapers the fare with distance, and with
# these values the longest route (incl. a stopover leg) at Rate 1.0 stays below the top price band.
FARE_REF_KM = 1178.0
FARE_DISTANCE_ALPHA = 0.25
F_OVER_C = 1.15

# airline code -> hub airport codes
HUBS = {
    "MU": ["SHA", "PVG"],
    "FM": ["SHA", "PVG"],
    "HO": ["SHA", "PVG"],
    "CA": ["PEK", "CTU"],
    "CZ": ["CAN"],
    "HU": ["HAK", "XIY"],
    "MF": ["XMN", "FOC"],
    "3U": ["CTU", "CKG"],
    "SC": ["TAO", "JNG"],
    "ZH": ["SZX"],
    "9C": ["PVG", "SHA"],
}
