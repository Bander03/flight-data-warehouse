"""Draws the control flow of the SSIS package LoadFlightDW (report figure D4) into docs/figures/ssis-control-flow.png.

Usage (repo root):  python tools/make_ssis_diagram.py
The task names and their order are read from the generated package ssis/FlightDWLoad/LoadFlightDW.dtsx,
so the figure cannot drift from the package. All tasks are drawn green because the package ran to
DTSER_SUCCESS with dtexec (see docs/ssis-guide.md); re-run the package before regenerating if it changed.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
DTSX = ROOT / "ssis" / "FlightDWLoad" / "LoadFlightDW.dtsx"
OUT = ROOT / "docs" / "figures" / "ssis-control-flow.png"
DTS = "{www.microsoft.com/SqlServer/Dts}"

NOTES = {  # short description printed to the right of each task
    "Copy CSVs to DataDir": "cmd /c copy data\\processed\\*.csv to C:\\fdw_data",
    "01 create database": "sqlcmd -i sql\\01_create_db.sql   (drops and creates FlightDW)",
    "02 staging tables": "sqlcmd -i sql\\02_stg_tables.sql",
    "03 star schema": "sqlcmd -i sql\\03_dw_tables.sql   (dimensions and fact table)",
    "04 load": "sqlcmd -v DataDir=... -i sql\\04_load.sql   (BULK INSERT, then dw tables)",
    "99 checks": "sqlcmd -i sql\\99_checks.sql   (stops the package if a check fails)",
    "05 grant cube read": "sqlcmd -i sql\\05_grant_ssas_read.sql   (read access for Analysis Services)",
}


def task_names() -> list:
    root = ET.parse(DTSX).getroot()
    return [e.get(DTS + "ObjectName") for e in root.find(DTS + "Executables")]


def main() -> None:
    names = task_names()
    n = len(names)
    fig, ax = plt.subplots(figsize=(11, 1.3 + 0.95 * n))
    ax.set_xlim(0, 11)
    ax.set_ylim(-0.5, 0.8 + 0.95 * n)
    ax.axis("off")
    ax.text(0.2, 0.35 + 0.95 * n, "Package LoadFlightDW: Control Flow", fontsize=13, fontweight="bold")
    x, w, h = 0.5, 3.0, 0.5
    tops = [0.1 + 0.95 * (n - 1 - i) for i in range(n)]
    for i, (name, y) in enumerate(zip(names, tops)):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc="#f5f9ff", ec="#3b6ea5", lw=1.4))
        ax.text(x + 0.45, y + h / 2, name, va="center", fontsize=11)
        ax.add_patch(Circle((x + 0.22, y + h / 2), 0.13, fc="#2e9d4a", ec="#1f7a37"))
        ax.text(x + 0.22, y + h / 2, "\u2713", color="white", ha="center", va="center", fontsize=10,
                fontweight="bold")
        ax.text(x + w + 0.25, y + h / 2, NOTES.get(name, ""), va="center", fontsize=9, color="#444444",
                family="monospace")
        if i + 1 < n:
            ax.add_patch(FancyArrowPatch((x + w / 2, y), (x + w / 2, tops[i + 1] + h), arrowstyle="-|>",
                                         mutation_scale=14, color="#2e9d4a", lw=1.8))
    ax.text(0.5, -0.4, "Green arrow: run the next task only if the previous one succeeded (exit code 0).",
            fontsize=8.5, color="#555555")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
