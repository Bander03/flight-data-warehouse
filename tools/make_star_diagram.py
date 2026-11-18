"""Draws the star schema of FlightDW (report figure D1) into docs/figures/star-schema.png and .svg.

Usage (repo root):  python tools/make_star_diagram.py
The table and column lists mirror sql/03_dw_tables.sql; a small self-check below fails if a
column named here is missing from that file, so the figure cannot drift from the schema.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"

FACT = (
    "Fact_FlightSegment",
    [
        "SegmentID  (PK)",
        "DepartureDateKey  (FK)",
        "ArrivalDateKey  (FK)",
        "PassengerKey  (FK)",
        "TicketKey  (FK)",
        "DepartureAirportKey  (FK)",
        "TransitAirportKey  (FK, 0 = No stopover)",
        "LandingAirportKey  (FK)",
        "PlaneKey  (FK)",
        "CabinKey  (FK)",
        "PriceRangeKey  (FK)",
        "Price",
        "Rate",
        "Mileage",
        "HasStopover",
        "SegmentCount",
    ],
)

# name: (columns, x, y of the top-left corner, width)
DIMS = {
    "DimDate": (["DateKey  (PK)", "FullDate", "Year", "Quarter", "Month", "Day", "DayName", "IsSpringFestival"], 0.2, 10.2, 3.6),
    "DimPassenger": (["PassengerKey  (PK)", "Gender", "Age", "AgeBand", "FFPTier", "Workplace"], 5.3, 10.5, 3.6),
    "DimTicket": (["TicketKey  (PK)", "FlightNo", "DepartureTime", "ArrivalTime", "DelayMinutes", "AirlineKey  (FK)", "IsSupplemented"], 10.2, 10.0, 3.6),
    "DimAirline": (["AirlineKey  (PK)", "AirlineCode", "AirlineName"], 10.2, 6.6, 3.6),
    "DimAirport": (["AirportKey  (PK; 0 = No stopover)", "AirportName", "AirportCode", "Province", "Longitude", "Latitude"], 0.2, 6.6, 3.6),
    "DimPlane": (["PlaneKey  (PK)", "PlaneModel", "SeatCount", "SizeClass"], 0.2, 3.5, 3.6),
    "DimSeat": (["CabinKey  (PK)", "CabinClass  (F / C / Y)", "SeatRow", "SeatLine"], 5.3, 1.6, 3.6),
    "DimPriceRange": (["PriceRangeKey  (PK)", "MinPrice", "MaxPrice", "PriceGrade"], 10.2, 3.5, 3.6),
}

# (dimension, label drawn on the link, side of the fact box, y of the attachment on the fact box)
LINKS = [
    ("DimDate", "Departure- /\nArrivalDateKey\n(role-playing)", "left", 6.8),
    ("DimAirport", "Departure- /\nTransit- /\nLandingAirportKey\n(role-playing)", "left", 5.0),
    ("DimPlane", "PlaneKey", "left", 3.2),
    ("DimPassenger", "PassengerKey", "top", None),
    ("DimTicket", "TicketKey", "right", 6.8),
    ("DimPriceRange", "PriceRangeKey", "right", 3.2),
    ("DimSeat", "CabinKey", "bottom", None),
]

LINE_H = 0.26
HEAD_H = 0.5
PAD = 0.16


def box_height(n_cols: int) -> float:
    return HEAD_H + n_cols * LINE_H + PAD


def self_check() -> None:
    ddl = (ROOT / "sql" / "03_dw_tables.sql").read_text(encoding="utf-8")
    all_tables = {FACT[0]: FACT[1], **{k: v[0] for k, v in DIMS.items()}}
    for table, cols in all_tables.items():
        m = re.search(r"CREATE TABLE dw\.%s \((.*?)\n\);" % re.escape(table), ddl, re.S)
        if not m:
            sys.exit(f"table {table} not found in sql/03_dw_tables.sql")
        body = m.group(1)
        for col in cols:
            name = col.split()[0]
            if not re.search(r"(^|\s|\[)%s(\]|\s)" % re.escape(name), body):
                sys.exit(f"column {table}.{name} not found in sql/03_dw_tables.sql")


def draw_box(ax, title, cols, x, y_top, w, header_color, body_color):
    h = box_height(len(cols))
    y = y_top - h
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                linewidth=1.6, edgecolor="#2b3a55", facecolor=body_color, zorder=2))
    ax.add_patch(FancyBboxPatch((x, y_top - HEAD_H), w, HEAD_H, boxstyle="round,pad=0.02,rounding_size=0.12",
                                linewidth=1.6, edgecolor="#2b3a55", facecolor=header_color, zorder=3))
    ax.text(x + w / 2, y_top - HEAD_H / 2, title, ha="center", va="center", fontsize=12.5, fontweight="bold",
            color="white", zorder=4)
    for i, col in enumerate(cols):
        ax.text(x + 0.2, y_top - HEAD_H - LINE_H * (i + 0.62), col, ha="left", va="center", fontsize=10, color="#1b2433", zorder=4)
    return x, y, w, h


def main() -> None:
    self_check()
    fig, ax = plt.subplots(figsize=(17, 13))
    ax.set_xlim(0, 14.2)
    ax.set_ylim(-0.6, 11.4)
    ax.axis("off")

    fx, fy_top, fw = 5.0, 7.4, 4.2
    f_x, f_y, f_w, f_h = draw_box(ax, FACT[0], FACT[1], fx, fy_top, fw, "#b5382c", "#fdeceb")

    boxes = {}
    for name, (cols, x, y_top, w) in DIMS.items():
        boxes[name] = draw_box(ax, name, cols, x, y_top, w, "#1f5f8b", "#eaf3fa")

    for dim, label, side, y_attach in LINKS:
        bx, by, bw, bh = boxes[dim]
        if side == "left":
            p_fact = (f_x, y_attach)
            p_dim = (bx + bw, by + bh / 2)
        elif side == "right":
            p_fact = (f_x + f_w, y_attach)
            p_dim = (bx, by + bh / 2)
        elif side == "top":
            p_fact = (f_x + f_w / 2, fy_top)
            p_dim = (bx + bw / 2, by)
        else:
            p_fact = (f_x + f_w / 2, f_y)
            p_dim = (bx + bw / 2, by + bh)
        ax.plot([p_dim[0], p_fact[0]], [p_dim[1], p_fact[1]], color="#44546a", linewidth=1.8, zorder=1)
        mx, my = (p_dim[0] + p_fact[0]) / 2, (p_dim[1] + p_fact[1]) / 2
        multi = "\n" in label
        ax.text(mx, my + (0.0 if multi else 0.14), label, ha="center", va="center" if multi else "bottom", fontsize=8.8, linespacing=1.15, color="#233047", zorder=5,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.9))

    # snowflake link DimTicket -> DimAirline
    tx, ty, tw, th = boxes["DimTicket"]
    ax2, ay2, aw2, ah2 = boxes["DimAirline"]
    ax.plot([tx + tw / 2, ax2 + aw2 / 2], [ty, ay2 + ah2], color="#44546a", linewidth=1.8, zorder=1)
    ax.text(tx + tw / 2 + 0.1, (ty + ay2 + ah2) / 2, "AirlineKey  (snowflake)", ha="left", va="center", fontsize=8.8,
            color="#233047", zorder=5, bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.9))

    ax.text(7.1, 11.3, "Flight data warehouse FlightDW: star schema (Group 2)", ha="center", va="top", fontsize=17,
            fontweight="bold", color="#1b2433")
    ax.text(7.1, -0.5, "Grain: one passenger on one flight segment. Red = fact table, blue = dimension tables. Role-playing: DimDate is used as departure and arrival date; "
                       "DimAirport as departure, transit and landing airport.",
            ha="center", va="bottom", fontsize=9.5, color="#44546a")

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "star-schema.png", dpi=170, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / "star-schema.svg", bbox_inches="tight", facecolor="white")
    print("wrote", OUT / "star-schema.png")


if __name__ == "__main__":
    main()
