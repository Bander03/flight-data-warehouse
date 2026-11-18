"""Shared test fixtures.

``make_valid_tables`` builds a small synthetic data set that satisfies every
guide #2 rule at the *real* thresholds from ``fdw.config`` (>= 20 departure
airports, >= 50 passengers, ...). It is a pure function of constants defined
here: no real data, no randomness.
"""
import pandas as pd
import pytest

N_ROWS = 60
N_AIRPORTS = 25
N_PASSENGERS = 55          # distinct passengers used by the fact rows
N_PLANES = 6
N_CABINS = 20
AIRLINE_CODES = ["CA", "CZ", "MU", "FM", "HO", "HU", "MF", "3U", "SC", "ZH", "9C"]  # 11
N_TICKETS = N_ROWS // 2    # two fact rows (one ticket group) per ticket
N_PRICE_RANGES = 10
IAN_START = 257286
PASSENGER_ID0 = 1000
TICKET_ID0 = 5000


def make_valid_tables() -> dict[str, pd.DataFrame]:
    """Return a fresh dict of DataFrames (source column names, nullable Int64 ids)."""
    # --- dimensions ---------------------------------------------------------
    airport = pd.DataFrame({
        "AirportID": range(1, N_AIRPORTS + 1),
        "ariport": [f"Airport {i}" for i in range(1, N_AIRPORTS + 1)],
        "airportCode": [f"A{i:02d}" for i in range(1, N_AIRPORTS + 1)],
        "Ariport_X": [100.0 + i for i in range(N_AIRPORTS)],
        "Ariport_y": [20.0 + i for i in range(N_AIRPORTS)],
        "city": [f"City {i}" for i in range(1, N_AIRPORTS + 1)],
    })
    days = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    date = pd.DataFrame({
        "DateRangeID": range(1, len(days) + 1),
        "Date": [d.strftime("%Y-%m-%d") for d in days],
        "Year": 2021,
        "Month": [d.month for d in days],
    })
    plane = pd.DataFrame({
        "PlaneID": range(1, N_PLANES + 1),
        "planeModel": [f"Model {i}" for i in range(1, N_PLANES + 1)],
        "SeatNum": [120 + 10 * i for i in range(N_PLANES)],
    })
    seat = pd.DataFrame({
        "CabinID": range(1, N_CABINS + 1),
        "CabinClass": ["F" if i < 2 else "C" if i < 6 else "Y" for i in range(N_CABINS)],
        "SeatRow": [1 + i // 4 for i in range(N_CABINS)],
        "SeatLine": [("A", "B", "C", "D")[i % 4] for i in range(N_CABINS)],
    })
    price_range = pd.DataFrame({
        "PriceRangeID": range(1, N_PRICE_RANGES + 1),
        "MinNum": [300 * i for i in range(N_PRICE_RANGES)],
        "MaxNum": [300 * (i + 1) for i in range(N_PRICE_RANGES)],
        "PriceGrade": range(N_PRICE_RANGES),
    })
    airline = pd.DataFrame({
        "AirlinesID": range(1, len(AIRLINE_CODES) + 1),
        "airlines": [f"Airline {c}" for c in AIRLINE_CODES],
        "airlinesCode": AIRLINE_CODES,
        "planeNumber": 100,
    })
    passenger = pd.DataFrame({
        "PassengerID": range(PASSENGER_ID0, PASSENGER_ID0 + N_ROWS),
        "PassengerGender": ["M" if i % 2 else "F" for i in range(N_ROWS)],
        "PassengerAge": [20.0 + i for i in range(N_ROWS)],
        "PassengerWorkplace": "Somewhere",
        "FFP_TIER": [4 + i % 3 for i in range(N_ROWS)],
        "FLIGHT_COUNT": [1 + i for i in range(N_ROWS)],
        "PassengerName": [f"Passenger {i}" for i in range(N_ROWS)],
    })

    # --- fact rows ----------------------------------------------------------
    rows = []
    for i in range(N_ROWS):
        month = 1 + i % 8                                  # Jan..Aug
        day = 1 + i // 8
        dep_ts = pd.Timestamp(2021, month, day)
        arr_ts = dep_ts + pd.Timedelta(days=1 if i % 5 == 0 else 0)
        rid = 1 + i % N_PRICE_RANGES
        rows.append({
            "PriceRangeID": rid,
            "Departure_ariportID": i % N_AIRPORTS + 1,
            # even rows have a stopover (30 rows); offsets 0 / 7 / 13 never coincide
            "Transit_ariportID": (i + 13) % N_AIRPORTS + 1 if i % 2 == 0 else pd.NA,
            "Landing_ariportID": (i + 7) % N_AIRPORTS + 1,
            "DepartureDateID": dep_ts.dayofyear,
            "ArrivalDateID": arr_ts.dayofyear,
            "PassengerID": PASSENGER_ID0 + i % N_PASSENGERS,
            "TicketID": TICKET_ID0 + i // 2,
            "PlaneID": 1 + i % N_PLANES,
            "CabinID": 1 + i % N_CABINS,
            "mileage": 1000 + 10 * i,
            "Price": rid * 300 - 150,                     # mid-range, multiple of 10
            "Rate": 0.5 + (i % 5) / 10,
            "ian": IAN_START + i,
        })
    fact = pd.DataFrame(rows)
    for col in ["PriceRangeID", "Departure_ariportID", "Transit_ariportID",
                "Landing_ariportID", "DepartureDateID", "ArrivalDateID",
                "PassengerID", "TicketID", "PlaneID", "CabinID", "ian"]:
        fact[col] = fact[col].astype("Int64")

    # --- tickets (one per ticket group) --------------------------------------
    t_rows = []
    for k in range(N_TICKETS):
        code = AIRLINE_CODES[k % len(AIRLINE_CODES)]
        dep = pd.Timestamp(2021, 1 + (2 * k) % 8, 1 + (2 * k) // 8, 8, 0)
        arr = dep + pd.Timedelta(hours=2, minutes=30)
        t_rows.append({
            "TicketID": TICKET_ID0 + k,
            "departureTime": dep.strftime("%Y-%m-%d %H:%M:%S"),
            "delayTime": 10 * (k % 5),
            "arrivalTime": arr.strftime("%Y-%m-%d %H:%M:%S"),
            "FlightNo": f"{code}{1000 + k}",
        })
    ticket = pd.DataFrame(t_rows)
    ticket["TicketID"] = ticket["TicketID"].astype("Int64")

    return {
        "fact": fact, "ticket": ticket, "passenger": passenger, "airport": airport,
        "airline": airline, "plane": plane, "seat": seat,
        "price_range": price_range, "date": date,
    }


@pytest.fixture
def valid_tables() -> dict[str, pd.DataFrame]:
    """A fresh, mutable copy of the valid synthetic tables for each test."""
    return make_valid_tables()


@pytest.fixture(scope="session")
def real_tables() -> dict[str, pd.DataFrame]:
    """The real data set, loaded once per session. Tests must not mutate it."""
    from fdw.load import load_tables
    return load_tables()
