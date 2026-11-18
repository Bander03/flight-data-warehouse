"""Scaffolds report section 3.3 (OLAP functions with MDX) from the verified results.

For each of the 28 statements it writes: the business question (from the MDX header), the MDX text
(comment lines removed), a result table (first rows of mdx/results/<stem>.csv, caption above) and a
short reading of the result, plus a placeholder for the SSMS screenshot. Captions are written as
`**Table N**` and `Figure N`: tools/build_report.py numbers them in document order.

The 'meaning' and 'result' sentences below are hand-written; preprocessing/tests/test_functions_section.py
checks that every number with 3 or more digits in a result sentence appears in that statement's result
file (rounded) or is listed in DERIVED, so a sentence cannot quote a figure the cube did not produce.

Usage (repo root):
    python tools/make_functions_section.py           # writes report/sections/03_3_functions.md
    python tools/make_functions_section.py --force   # overwrite a section you already edited by hand
After the first run, edit the Markdown by hand; do not re-run with --force unless you want to start over.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MDX_DIR = ROOT / "mdx"
RESULTS = ROOT / "mdx" / "results"
OUT = ROOT / "report" / "sections" / "03_3_functions.md"

OPERATIONS = [
    ("01_drill_down", "Drill down", "Drill down moves from a coarse level of a hierarchy to its finer level, for example from a province to its airports."),
    ("02_roll_up", "Roll up", "Roll up is the opposite: figures of a fine level are aggregated to the coarser level above it."),
    ("03_slice", "Slice", "A slice fixes one member of one dimension and shows the rest of the cube for that member only."),
    ("04_dice", "Dice", "A dice selects a sub-cube by restricting several dimensions at the same time."),
    ("05_rank", "Rank", "Rank orders the members of a level by a measure and shows their position."),
    ("06_top_n", "Top N", "Top N keeps only the N members with the highest value of a measure."),
    ("07_moving_avg", "Moving average", "A moving average smooths a series: each value is the mean of the current period and the periods just before it. The first two statements use a 3-month window on monthly figures (the first two months use the months available); the third uses a 7-day window on daily figures."),
    ("08_running_total", "Running total", "A running total (year to date) accumulates a monthly measure from January to the current month."),
    ("09_stopover", "Stopover analysis", "These statements analyse flights with a stopover, using the transit-airport role of the airport dimension; the member 'No stopover' is excluded wherever hubs are ranked."),
]

# stem -> (meaning, result sentence). Numbers in the result sentences are checked against mdx/results.
NOTES: dict[str, tuple[str, str]] = {
    "01_drill_down_1": (
        "The first quarter of 2021 is split into its three months to see how traffic builds up during the quarter.",
        "January had 61 segments, February 78 and March 91, so traffic grew from month to month during the quarter."),
    "01_drill_down_2": (
        "A province can have several airports. Drilling from the province to its airports shows how the price level differs between airports of the same city.",
        "Shanghai has two departure airports in the data: segments leaving Hongqiao (虹桥机场) average 2,519.87 and those leaving Pudong (浦东机场) 2,133.93, so Hongqiao is the more expensive departure airport."),
    "01_drill_down_3": (
        "Drilling from an airline to its flight numbers shows which individual flights earn the revenue.",
        "Air China operates 21 flight numbers in the data. CA1517 earns the most with 42,740, followed by CA1501 with 32,790, while the smallest, CA1886, earns 4,940."),
    "02_roll_up_1": (
        "Daily figures are aggregated to months to see the seasonal profile of revenue.",
        "Monthly revenue peaks in February with 213,460 and is lowest in August with 145,970; the eight months add up to the total revenue of 1,400,460."),
    "02_roll_up_2": (
        "The kilometres flown into each province, rolled up from the airports to the provinces, show where long-distance traffic lands.",
        "Shanghai (上海) receives by far the most kilometres, 344,106, followed by Sichuan (四川) with 108,176 and Inner Mongolia (内蒙古) with 75,065; Henan (河南) is the lowest of the 24 provinces with 4,785."),
    "02_roll_up_3": (
        "Distinct passengers cannot simply be added up. When flight numbers are rolled up to airlines the cube counts each passenger once per airline.",
        "China Eastern Airlines (中国东方航空) carried 300 different passengers, Air China (中国国际航空) 157 and Hainan Airlines (海南航空) 65; the smallest airlines, Sichuan Airlines and Spring Airlines, carried 2 each."),
    "03_slice_1": (
        "Only economy-class segments are kept (slice on the cabin class Y) and the revenue is shown per airline.",
        "In economy class China Eastern Airlines earns 273,130, Air China 142,620 and Hainan Airlines 48,690; each of the remaining eight airlines earns less than 23,000."),
    "03_slice_2": (
        "Fixing the departure airport to Beijing Capital Airport (首都机场) shows all destinations served from it.",
        "Beijing Capital has six destinations in the data: Qingyang (庆阳机场) receives 15 segments and Jiayuguan (嘉峪关机场) 12, the other four airports 8, 8, 3 and 3."),
    "03_slice_3": (
        "The slice on the Spring Festival flag restricts the analysis to the festival week (2021-02-11 to 2021-02-17) and compares the average ticket price per cabin class.",
        "During the festival week the average ticket price is 1,306.84 in economy (Y), 5,777.50 in business (C) and 7,045.00 in first class (F)."),
    "04_dice_1": (
        "The dice selects two provinces and two quarters at once to compare departures from Shanghai and Beijing.",
        "Shanghai had 73 departures in the first quarter and 63 in the second, Beijing only 14 and 11."),
    "04_dice_2": (
        "The dice on aircraft size class and premium cabin class compares the revenue of wide-body and narrow-body aircraft in business and first class.",
        "Wide-body aircraft earn 402,670 in business class and 196,570 in first class, narrow-body aircraft 206,710 and 73,670."),
    "04_dice_3": (
        "The dice cuts the cube along two different dimensions at once, the passenger's frequent-flyer tier (Passenger) and the cabin class (Cabin), and counts distinct passengers in each cell (the counts are per cell and are not additive).",
        "The top-tier passengers mostly fly economy: in tier 5, 21 passengers flew in economy (Y) and 4 in business (C); in tier 6, 9 flew in economy and 3 in business."),
    "05_rank_1": (
        "Airlines are ranked by total ticket revenue.",
        "China Eastern Airlines ranks first with 699,600, Air China second with 409,590 and Hainan Airlines third with 151,680; Spring Airlines (春秋航空) is last, 11th, with 2,390."),
    "05_rank_2": (
        "Departure airports with at least 10 segments are ranked by revenue, so that no airport is ranked on a handful of tickets.",
        "Of the 16 airports with at least 10 segments, Hongqiao ranks first with 199,070, Pudong second with 189,920, Shuangliu (双流机场) third with 124,350 and Beijing Capital fourth with 117,830; Linyi (临沂机场) is 16th with 20,940."),
    "05_rank_3": (
        "Price grades are 300-yuan price bands (grade g covers 300g to 300(g+1) yuan). Ranking them by revenue shows which price band produces most of the revenue.",
        "Grade 5 (1,500 to 1,800 yuan) brings the most revenue with 188,920, followed by grade 4 (1,200 to 1,500 yuan) with 126,870; of the 28 grades used, grade 26 is last with 7,870."),
    "06_top_n_1": (
        "Routes are combinations of a departure and a landing airport; the five routes with the highest revenue are listed.",
        "The most valuable route is Sanjiazi (三家子机场) to Shuangliu with 42,740, followed by Fuyun (富蕴机场) to Hongqiao with 41,160; the fifth is Pudong to Yushu Batang (玉树巴塘机场) with 32,710."),
    "06_top_n_2": (
        "The total kilometres flown per flight number show which flights do the long-distance work.",
        "MU5112 tops the list with 47,606 km and MU5106 follows with 45,066 km; the tenth is MU5160 with 21,360 km."),
    "06_top_n_3": (
        "The workplace is a free-text attribute of the passenger; the five workplaces with the most segments show where the customers come from (workplace 'Unknown' is excluded).",
        "Guangzhou (中国广东广州) leads with 74 segments, followed by Beijing (中国北京) with 57, Shenzhen (中国广东深圳) with 41, Shanghai (中国上海上海) with 36 and Dalian (中国辽宁大连) with 22."),
    "07_moving_avg_1": (
        "The 3-month moving average of the monthly revenue smooths the month-to-month variation.",
        "The smoothed revenue rises from 149,130 in January to 199,503.33 in April and then declines to 160,650 in August."),
    "07_moving_avg_2": (
        "The same smoothing is applied to the number of segments arriving per month; this statement uses the arrival-date role of the date dimension.",
        "The average number of arriving segments peaks in April at 83.67 and falls to 72 in August."),
    "07_moving_avg_3": (
        "At day grain the 7-day moving average smooths the day-to-day variation of departures in February 2021, the month of the Spring Festival: each value averages the current and the six previous calendar days, counting only days with departures (MDX AVG skips empty days).",
        "The average starts at 2 segments per day in early February, rises through the festival week (2021-02-11 to 2021-02-17) to 5.4 on 15 February and 6 on 18 February, and reaches its highest value, 7, on 28 February."),
    "08_running_total_1": (
        "The running total accumulates the monthly revenue from January (year to date).",
        "Cumulative revenue reaches 362,590 at the end of February, 918,510 in May and 1,400,460 in August, the total revenue of all 600 segments."),
    "08_running_total_2": (
        "The cumulative number of arrived segments follows the arrival-date role.",
        "The cumulative count of arrived segments grows from 61 in January to 464 in June and 600 in August, equal to all fact rows."),
    "08_running_total_3": (
        "The running total of segments with a stopover shows how quickly stopover traffic builds up.",
        "Cumulative stopover segments rise from 9 in January to 95 in August; the largest monthly increase is in March, from 18 to 52."),
    "09_stopover_1": (
        "Transit hubs are the airports where passengers change planes. The member 'No stopover' is excluded so that only real hubs are ranked.",
        "The five hubs with the most revenue are Sanxia (三峡机场) with 45,110, Beijiao (北郊机场) with 42,740, Tianzhushan (天柱山机场) with 30,740, Hehua (荷花机场) with 27,440 and Weifang (潍坊机场) with 25,650."),
    "09_stopover_2": (
        "Comparing segments with and without a stopover answers whether indirect travel is more expensive on average.",
        "Segments with a stopover cost 2,901.68 on average and direct segments 2,227.33. The statement compares price only: stopovers were only given to routes of at least 900 km (a preprocessing rule), so the two groups differ in route length and the comparison is not like-for-like; it does not measure how much of the difference comes from distance."),
    "09_stopover_3": (
        "The share of stopover segments per airline shows how much each airline relies on stopovers.",
        "Air China has the highest share among the large airlines (0.3101), followed by China Eastern (0.1067) and Hainan Airlines (0.0923); Shandong Airlines and Spring Airlines reach a share of 1 only because they are two of the airlines added in preprocessing with very few segments (6 and 2), all of them with a stopover."),
    "09_stopover_4": (
        "Routes on which every segment makes a stopover show which connections are flown only with a stopover.",
        "14 routes are flown only with a stopover; together they account for all 95 stopover segments, the largest being Pudong to Beijing Capital with 14 segments and Sanjiazi to Shuangliu with 13."),
}

# numbers (3 or more digits) in a result sentence that are derived, not stored in that statement's result file
DERIVED: dict[str, set[float]] = {
    "02_roll_up_1": {1400460},
    "03_slice_1": {23000},
    "05_rank_3": {1500, 1800, 1200},
    "08_running_total_1": {600},
    "09_stopover_2": {900},  # the preprocessing rule: stopovers only on routes of at least 900 km
}

DISCUSSION = (
    "**Role-playing dimensions.** The arrival-date role is used by the arrival statements (07_moving_avg_2 and 08_running_total_2) and the "
    "departure-date role by the others; the transit-airport role carries all stopover statements.\n\n"
    "**Spring Festival.** The slice on the festival week (03_slice_3) is the analysis the course guide suggests for holiday traffic; "
    "in the data, first class costs more than business class, and business more than economy, during that week.\n\n"
    "**Stopover versus direct.** Segments with a stopover cost more on average than direct ones (09_stopover_2), but stopovers were only "
    "assigned to routes of at least 900 km, so the two groups are not like-for-like and the statement does not separate a stopover effect from a distance effect. Only 14 routes are flown "
    "with a stopover (09_stopover_4), and they carry all 95 stopover segments.\n\n"
    "**What the data cannot show.** Flight durations come from the source tickets and do not scale with distance, and passenger names "
    "are not unique, so no statement analyses duration or groups by name (see 'Known artefacts' in docs/DATA_FINDINGS.md).\n\n"
    "**Verification.** Every statement was checked against an independent T-SQL query on the relational warehouse: all 28 results match "
    "(tools/compare_results.py)."
)


def read_results(stem: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(open(RESULTS / f"{stem}.csv", encoding="utf-8")))
    return rows[0], rows[1:]


def mdx_parts(stem: str) -> tuple[str, str]:
    text = (MDX_DIR / f"{stem}.mdx").read_text(encoding="utf-8")
    question = ""
    code = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("-- Question:"):
            question = s[len("-- Question:"):].strip()
        elif s.startswith("--") or not s:
            continue
        else:
            code.append(line.rstrip())
    return question, "\n".join(code)


def _fmt(value: str) -> str:
    try:
        f = float(value)
    except ValueError:
        return value
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f)):,}"
    return f"{f:,.4f}".rstrip("0").rstrip(".")


def _table(stem: str) -> str:
    hdr, body = read_results(stem)
    shown = body[:6]
    lines = [f"**Table N** Result of `{stem}`" + (f" (first 6 of {len(body)} rows)." if len(body) > 6 else f" ({len(body)} rows)."), ""]
    lines.append("| " + " | ".join(hdr) + " |")
    lines.append("|" + "---|" * len(hdr))
    for r in shown:
        cells = [c.replace("|", "\\|") for c in r[:-1]] + [_fmt(r[-1])]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_markdown() -> str:
    out = ["## 3.3 Functions: OLAP analysis with MDX", ""]
    out.append(
        "All statements run on the cube `FlightCube` (Analysis Services, Multidimensional) and every result was checked against an independent "
        "T-SQL query on the warehouse. Each statement below gives its business meaning, the MDX, the first rows of the result and a short reading; "
        "each figure is the SSMS result window of the statement. SSMS shows the values with the number format of the cube (for example 69.5 is displayed as 70), while the result tables below give the exact values."
    )
    out.append("")
    for i, (prefix, title, intro) in enumerate(OPERATIONS, start=1):
        out.append(f"### 3.3.{i} {title}")
        out.append("")
        out.append(intro)
        out.append("")
        stems = sorted(p.stem for p in MDX_DIR.glob(f"{prefix}_*.mdx"))
        for stem in stems:
            question, code = mdx_parts(stem)
            meaning, result = NOTES[stem]
            sid = "M" + stem[:2] + "." + stem.rsplit("_", 1)[1]
            out.append(f"**{stem}.** {question}")
            out.append("")
            out.append(f"*Meaning.* {meaning}")
            out.append("")
            out.append("```")
            out.append(code)
            out.append("```")
            out.append("")
            out.append(_table(stem))
            out.append("")
            out.append(f"*Result.* {result}")
            out.append("")
            shot = ROOT / "report" / "figures" / f"{sid}.jpg"
            if shot.exists():
                out.append(f"![Figure N SSMS result window of `{stem}`.](../figures/{sid}.jpg)")
            else:
                out.append(f"*(Screenshot {sid} to insert here as Figure N: SSMS result window of `{stem}`.)*")
            out.append("")
    out.append(f"### 3.3.{len(OPERATIONS) + 1} Highlights and discussion of the results")
    out.append("")
    out.append(DISCUSSION)
    out.append("")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if OUT.exists() and "--force" not in argv:
        existing = OUT.read_text(encoding="utf-8")
        if "Skeleton." not in existing:
            print(f"{OUT.name} was already generated or edited: use --force to overwrite it.")
            return 1
    OUT.write_text(build_markdown(), encoding="utf-8", newline="\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
