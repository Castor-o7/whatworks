#!/usr/bin/env python3
"""Build data/storms.db from the NOAA Storm Events gzipped CSVs in stormdata/.

Usage: python3 scripts/build_storm_db.py   (stdlib only, ~1-3 minutes)
"""
import csv
import gzip
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "stormdata"
DB = ROOT / "data" / "storms.db"

csv.field_size_limit(sys.maxsize)

MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "H": 1e2, "": 1}


def money(s):
    """NOAA damage strings look like '10.00K', '2.5M', '0' or ''."""
    s = (s or "").strip().upper()
    if not s:
        return 0.0
    suffix = s[-1] if s[-1].isalpha() else ""
    num = s[:-1] if suffix else s
    try:
        return float(num or 1) * MULT.get(suffix, 1)
    except ValueError:
        return 0.0


LOST = "\ufffd"  # NOAA's files already contain replacement chars where curly quotes etc. were lost


def tidy(text):
    """Repair the unambiguous cases (John's, 90°F) and collapse other lost-character runs to one."""
    if not text or LOST not in text:
        return text or None
    text = re.sub(rf"(?<=\w){LOST}+(?=(s|t|ll|re|ve|d|m)\b)", "'", text)
    text = re.sub(rf"(?<=\d) ?{LOST}+ ?(?=[FC]\b)", "°", text)
    return re.sub(rf"{LOST}+", LOST, text)


def num(s, cast=int):
    try:
        return cast(s) if s not in (None, "") else None
    except ValueError:
        return None



def begin_date(row):
    ym = row["BEGIN_YEARMONTH"]
    return f"{ym[:4]}-{ym[4:6]}-{int(row['BEGIN_DAY']):02d}"


SCHEMA = """
CREATE TABLE events (
  event_id INTEGER PRIMARY KEY,
  episode_id INTEGER,
  year INTEGER, month INTEGER, begin_date TEXT,
  state TEXT, cz_name TEXT, event_type TEXT,
  injuries INTEGER, deaths INTEGER,
  damage_property REAL, damage_crops REAL,
  magnitude REAL, magnitude_type TEXT, tor_f_scale TEXT,
  begin_lat REAL, begin_lon REAL,
  episode_narrative TEXT, event_narrative TEXT
);
CREATE TABLE fatalities (
  fatality_id INTEGER PRIMARY KEY,
  event_id INTEGER, fatality_type TEXT, fatality_date TEXT,
  age INTEGER, sex TEXT, location TEXT
);
"""

INDEXES = """
CREATE INDEX ix_year ON events(year);
CREATE INDEX ix_state ON events(state);
CREATE INDEX ix_type ON events(event_type);
CREATE INDEX ix_date ON events(begin_date);
CREATE INDEX ix_md ON events(substr(begin_date, 6));
CREATE INDEX ix_fat_event ON fatalities(event_id);
CREATE INDEX ix_latlon ON events(begin_lat, begin_lon);
"""


def main():
    DB.parent.mkdir(exist_ok=True)
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)

    total = 0
    for f in sorted((SRC / "details_zip").glob("*.csv.gz")):
        with gzip.open(f, "rt", encoding="utf-8", errors="replace", newline="") as fh:
            rows = []
            for r in csv.DictReader(fh):
                rows.append((
                    num(r["EVENT_ID"]), num(r["EPISODE_ID"]),
                    num(r["YEAR"]), int(r["BEGIN_YEARMONTH"][4:6]), begin_date(r),
                    r["STATE"].title(), r["CZ_NAME"].title(), r["EVENT_TYPE"],
                    (num(r["INJURIES_DIRECT"]) or 0) + (num(r["INJURIES_INDIRECT"]) or 0),
                    (num(r["DEATHS_DIRECT"]) or 0) + (num(r["DEATHS_INDIRECT"]) or 0),
                    money(r["DAMAGE_PROPERTY"]), money(r["DAMAGE_CROPS"]),
                    num(r["MAGNITUDE"], float), r["MAGNITUDE_TYPE"] or None, r["TOR_F_SCALE"] or None,
                    num(r["BEGIN_LAT"], float), num(r["BEGIN_LON"], float),
                    tidy(r["EPISODE_NARRATIVE"]), tidy(r["EVENT_NARRATIVE"]),
                ))
            con.executemany(f"INSERT OR REPLACE INTO events VALUES ({','.join('?' * 19)})", rows)
            total += len(rows)
            print(f"{f.name[:45]:45} {len(rows):>7,}  (total {total:,})")

    for f in sorted((SRC / "fatalaties_zip").glob("*.csv.gz")):
        with gzip.open(f, "rt", encoding="utf-8", errors="replace", newline="") as fh:
            con.executemany(
                "INSERT OR REPLACE INTO fatalities VALUES (?,?,?,?,?,?,?)",
                ((num(r["FATALITY_ID"]), num(r["EVENT_ID"]), r["FATALITY_TYPE"],
                  r["FATALITY_DATE"], num(r["FATALITY_AGE"]), r["FATALITY_SEX"] or None,
                  r["FATALITY_LOCATION"] or None) for r in csv.DictReader(fh)),
            )

    print("Building indexes and search index...")
    con.executescript(INDEXES)
    con.executescript("""
      CREATE VIRTUAL TABLE events_fts USING fts5(
        event_narrative, episode_narrative, content='events', content_rowid='event_id');
      INSERT INTO events_fts(rowid, event_narrative, episode_narrative)
        SELECT event_id, coalesce(event_narrative,''), coalesce(episode_narrative,'') FROM events;
    """)
    con.commit()
    con.execute("ANALYZE")
    con.close()
    tmp.replace(DB)
    print(f"Done: {total:,} events -> {DB} ({datetime.now():%H:%M:%S})")


if __name__ == "__main__":
    main()
