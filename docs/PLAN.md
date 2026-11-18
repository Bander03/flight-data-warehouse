# Project plan

Internal dates are earlier than the real deadline (Mon 2026-12-21) to leave buffer.

| Window | Goal | Done when |
|---|---|---|
| Nov 12–18 | Setup and schema design | Everyone has tools installed; star schema diagram agreed |
| Nov 19–25 | Preprocessing and warehouse tables | Cleaned fact table passes every check; tables created and loaded |
| Nov 26–Dec 2 | Cube | SSAS cube processes; first MDX queries run |
| Dec 3–9 | OLAP + stopover analysis | 21+ MDX statements with screenshots; stopover analysis done |
| Dec 10–16 | Report | Full draft, formatted, peer reviewed |
| Dec 17–20 | Buffer and printing | Paper copy printed, e-version checked |
| **Dec 21** | **Submit** | |

## Environment (verify first)

- SQL Server **Developer Edition** (free). Express does **not** include Analysis Services (SSAS), which MDX needs.
- SQL Server Management Studio (SSMS).
- Visual Studio with the "Analysis Services Projects" and "Integration Services Projects" extensions.
- Python 3 with `pandas` and `openpyxl` for preprocessing.
- draw.io for the star schema diagram.

## Design decisions to settle (week 1)

- Main dimensions: Date, Passenger, Ticket/Flight, Airport. Secondary: Airline, Plane, Seat/Cabin, PriceRange.
- Airport is used three times (departure, transit, landing): use a role-playing dimension.
- Only the date goes in the Date dimension, not hour-minute. Departure and arrival times belong with the flight/ticket.
- Airline is not a column in the ticket table; derive it from the `FlightNo` prefix (MU, CA, HU ...) and join to the Airlines table.
- Stopover: keep a stopover airport key in the fact table. Transit time is ignored per the instructions.

## Report rules (from guide #4)

- Cover page, then sections 2–6. Sections 2–5 in Times New Roman, size 11.
- Code in the report must not exceed one third of an A4 page per item; longer code goes in an appendix.
- Figure captions below figures, table captions above tables; number them separately; page numbers required.
- Sections 4 and 5 are written separately by each member under their own name.
- References in SWJTU Journal format.
