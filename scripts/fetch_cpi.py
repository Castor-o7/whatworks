#!/usr/bin/env python3
"""Download CPI-U (FRED series CPIAUCNS) and write annual averages to data_sources/cpi-u-annual.csv.

Usage: .venv/bin/python scripts/fetch_cpi.py   (stdlib only; needs the network)

CPIAUCNS is the Consumer Price Index for All Urban Consumers: All Items in U.S. City Average,
not seasonally adjusted (index 1982-84 = 100), published by the U.S. Bureau of Labor Statistics and
redistributed by FRED. Each calendar year's value is the plain mean of its 12 monthly values, rounded
to 3 decimals; a year with any month missing (the current year, or a month BLS never published) is
left out rather than averaged from fewer months. scripts/build_data.py turns the CSV into cpi.json,
which the Then & Now page uses to show damage in real dollars (docs/THEN_AND_NOW.md).

The CSV is committed so data builds are reproducible offline; re-run this only to add new years.
"""
import csv
import datetime
import io
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_sources" / "cpi-u-annual.csv"
SERIES = "CPIAUCNS"
URL = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}"
SOURCE = "U.S. Bureau of Labor Statistics, via FRED (Federal Reserve Bank of St. Louis)"
TITLE = "CPI-U, all items in U.S. city average, not seasonally adjusted (1982-84=100)"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "whatworks-fetch-cpi/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SystemExit(f"Could not download {URL}: {e}\n"
                         f"Are you offline? {OUT.relative_to(ROOT)} was left unchanged.")


def annual_averages(text):
    """{year: [12 monthly values]} -> {year: mean} for complete years only; also returns skipped years."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) != 2 or rows[0][1] != SERIES:
        raise SystemExit(f"Unexpected CSV from {URL}: header {rows[0] if rows else '(empty)'}")
    months = defaultdict(dict)
    for date, value in rows[1:]:
        value = value.strip()
        if not value or value == ".":       # FRED marks missing observations with "" or "."
            continue
        y, m = int(date[:4]), int(date[5:7])
        months[y][m] = float(value)
    annual, skipped = {}, {}
    for y in sorted(months):
        if len(months[y]) == 12:
            annual[y] = round(sum(months[y].values()) / 12, 3)
        else:
            skipped[y] = sorted(set(range(1, 13)) - set(months[y]))
    return annual, skipped


def main():
    annual, skipped = annual_averages(fetch())
    if len(annual) < 100:
        raise SystemExit(f"Only {len(annual)} complete years in the download; refusing to overwrite {OUT}")
    retrieved = datetime.date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# source: {SOURCE}",
        f"# series: {SERIES} - {TITLE}",
        f"# url: {URL}",
        f"# retrieved: {retrieved}",
        "# method: annual value = mean of the 12 monthly values, rounded to 3 decimals; "
        "years missing any month are omitted",
        "year,cpi",
        *(f"{y},{v:.3f}" for y, v in annual.items()),
    ]
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    first, last = min(annual), max(annual)
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(annual)} years, {first}-{last} "
          f"({first}: {annual[first]}, {last}: {annual[last]})")
    for y, missing in skipped.items():
        print(f"  skipped {y}: missing month(s) {', '.join(map(str, missing))}")


if __name__ == "__main__":
    main()
