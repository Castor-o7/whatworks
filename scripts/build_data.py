#!/usr/bin/env python3
"""Precompute the Storm Desk's data files from data/storms.db into _site/data/ (see docs/STATIC_SITE.md).

Usage: .venv/bin/python scripts/build_data.py   (stdlib only, about a minute, peak ~2 GB of RAM)

The whole events table is streamed once in event_id order and grouped in Python, so nothing scans
the table per shard. Output goes to _site/data.tmp and only replaces _site/data once every file is
written, so a failed run never leaves half a dataset. Nothing else in _site/ is touched.
"""
import gzip
import heapq
import json
import math
import shutil
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "storms.db"
SITE = ROOT / "_site"
OUT = SITE / "data"
TMP = SITE / "data.tmp"

SHARDS = 4096
NOTABLE_MIN_DAMAGE = 250_000
MENU_MIN_EVENTS = 50     # states need more than this many events to appear in the dropdown
ON_THIS_DAY = 6
EXCERPT = 280
BLOCK = 5                # grid025 files cover 5-degree blocks
HAS_COORDS = "begin_lat IS NOT NULL AND begin_lon IS NOT NULL AND begin_lat != 0"

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


WRITTEN = []  # every relative path written, checked before the swap


def write(path, obj=None, text=None):
    """Write one gzipped JSON file under TMP as <path>.gz (text = already-serialized JSON).

    Pages limits a site to 1 GB on disk; gzip takes the dataset from ~905 MB to roughly a quarter of
    that. mtime=0 keeps the bytes identical across rebuilds, so git only re-uploads files that changed.
    data.js fetches <path>.gz and decompresses it in the browser."""
    path = f"{path}.gz"
    WRITTEN.append(path)
    path = TMP / path
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (dumps(obj) if text is None else text).encode("utf-8")
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))


def table(cols, rows):
    return {"cols": cols, "rows": rows}


def dollars(x):
    """NOAA damage is stored as REAL; the site uses whole dollars (all values are >= 0)."""
    return int(x + 0.5) if x else 0


def sql_round(x):
    """SQLite's round(): halves go away from zero (Python's round() goes to even)."""
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def num(x):
    """35.0 -> 35 (and -0.0 -> 0) so grid coordinates stay short."""
    return int(x) if x == int(x) else x


def ymd(date):
    """'2011-05-22' -> 20110522"""
    return int(date[:4]) * 10000 + int(date[5:7]) * 100 + int(date[8:10])


def by_date_desc(rows, date_col=1):
    """Newest first; ties broken by event id (col 0), highest first."""
    rows.sort(key=lambda r: (r[date_col], r[0]), reverse=True)
    return rows


def main():
    if not DB.exists():
        raise SystemExit(f"{DB} not found; build it with scripts/build_storm_db.py first")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)

    # ---- Lookups: states A-Z, types most frequent first, fatalities by event ------------------
    states = [s for (s,) in con.execute("SELECT DISTINCT state FROM events ORDER BY state")]
    type_counts = con.execute("SELECT event_type, COUNT(*) n FROM events GROUP BY event_type").fetchall()
    types = [t for t, n in sorted(type_counts, key=lambda r: (-r[1], r[0]))]
    S = {s: i for i, s in enumerate(states)}
    T = {t: i for i, t in enumerate(types)}
    fatalities = defaultdict(list)
    for eid, ftype, age, sex, loc in con.execute(
            "SELECT event_id, fatality_type, age, sex, location FROM fatalities ORDER BY fatality_id"):
        fatalities[eid].append({"type": ftype, "age": age, "sex": sex, "location": loc})
    log(f"{len(states)} states, {len(types)} types, {sum(map(len, fatalities.values())):,} fatality records")

    # A few dozen NOAA episodes give different events different episode narratives. The episode
    # shard keeps the one most of its events share (ties: the earliest event's); the odd events out,
    # and the few with a narrative but no episode_id, carry their own as record["episode_narrative"].
    episode_text = {}
    for epid, text, _, _ in con.execute("""
            SELECT episode_id, episode_narrative, COUNT(*), MIN(event_id) FROM events
            WHERE episode_narrative != '' AND episode_id IN (
              SELECT episode_id FROM events WHERE episode_narrative != ''
              GROUP BY episode_id HAVING COUNT(DISTINCT episode_narrative) > 1)
            GROUP BY 1, 2 ORDER BY 1, 3 DESC, 4"""):
        episode_text.setdefault(epid, text)
    log(f"{len(episode_text)} episodes with conflicting narratives")

    # ---- One pass over every event -----------------------------------------------------------
    cube = defaultdict(lambda: [0] * 8)        # (s, t, y, m) -> events..damage, l_events..l_damage
    grid1 = defaultdict(lambda: [0] * 4)       # (lat, lon, s, t, y) -> events, deaths, injuries, damage
    grid025 = defaultdict(lambda: [0] * 4)     # (lat*4, lon*4, s, t, y) -> same
    tiles = defaultdict(list)                  # "lat_lon" -> rows
    by_state = defaultdict(list)               # s -> rows
    notable = []
    shards = [[] for _ in range(SHARDS)]       # serialized '"id":{record}' pieces
    episodes = {}                              # episode_id -> its narrative
    days = defaultdict(list)                   # "MM-DD" -> min-heap of the top ON_THIS_DAY
    totals = [0, 0, 0, 0]
    located = 0

    rows = con.execute("""SELECT event_id, episode_id, year, month, begin_date, state, cz_name, event_type,
                                 deaths, injuries, damage_property, damage_crops, magnitude, magnitude_type,
                                 tor_f_scale, begin_lat, begin_lon, episode_narrative, event_narrative
                          FROM events ORDER BY event_id""")
    for n, (eid, epid, year, month, date, state, cz, etype, deaths, injuries, dp, dc, mag, mag_type,
            fscale, lat, lon, ep_narr, narr) in enumerate(rows, 1):
        s, t, d = S[state], T[etype], ymd(date)
        prop, crops = dollars(dp), dollars(dc)
        damage = prop + crops
        has_coords = lat is not None and lon is not None and lat != 0

        totals[0] += 1; totals[1] += deaths; totals[2] += injuries; totals[3] += damage
        c = cube[(s, t, year, month)]
        c[0] += 1; c[1] += deaths; c[2] += injuries; c[3] += damage
        by_state[s].append((eid, d, t, cz, deaths, injuries, damage))
        if deaths > 0 or injuries > 0 or damage >= NOTABLE_MIN_DAMAGE:
            notable.append((eid, d, s, t, cz, deaths, injuries, damage))

        if has_coords:
            located += 1
            c[4] += 1; c[5] += deaths; c[6] += injuries; c[7] += damage
            for grid, k in ((grid1, 1), (grid025, 4)):
                g = grid[(sql_round(lat * k), sql_round(lon * k), s, t, year)]
                g[0] += 1; g[1] += deaths; g[2] += injuries; g[3] += damage
            tiles[f"{math.floor(lat)}_{math.floor(lon)}"].append(
                (eid, d, s, t, cz, deaths, injuries, damage, round(lat, 4), round(lon, 4)))

        record = {"id": eid, "episode_id": epid, "date": date, "year": year, "state": state, "cz_name": cz,
                  "event_type": etype, "deaths": deaths, "injuries": injuries, "damage_property": prop,
                  "damage_crops": crops, "magnitude": mag, "magnitude_type": mag_type, "tor_f_scale": fscale,
                  "lat": lat if has_coords else None, "lon": lon if has_coords else None,
                  "narrative": narr, "fatalities": fatalities.get(eid)}
        if ep_narr and epid is not None:
            episodes.setdefault(epid, episode_text.get(epid, ep_narr))
        if ep_narr and (epid is None or episodes[epid] != ep_narr):
            record["episode_narrative"] = ep_narr
        # Null fields and an empty fatality list are left out (readers treat missing as null): the
        # repeated '"tor_f_scale":null' and friends would otherwise push the site past Pages' 1 GB.
        record = {k: v for k, v in record.items() if v is not None}
        shards[eid % SHARDS].append(f'"{eid}":{dumps(record)}')

        # Same ranking as the old on_this_day() query (on the unrounded damage); ties go to the lower id.
        score = (deaths * 1e9 + injuries * 1e7 + dp + dc, -eid)
        heap = days[date[5:]]
        if len(heap) < ON_THIS_DAY or score > heap[0][0]:
            item = (score, {"id": eid, "date": date, "state": state, "cz": cz, "type": etype, "deaths": deaths,
                            "injuries": injuries, "damage": damage,
                            "excerpt": narr.replace("|", " ")[:EXCERPT] if narr is not None else None})
            (heapq.heappush if len(heap) < ON_THIS_DAY else heapq.heapreplace)(heap, item)
        if n % 250_000 == 0:
            log(f"  {n:,} events read")
    con.close()
    log(f"{totals[0]:,} events read ({located:,} located, {len(notable):,} notable, {len(episodes):,} episodes)")

    # ---- Event and episode shards --------------------------------------------------------------
    for i, pieces in enumerate(shards):
        write(f"events/{i}.json", text="{" + ",".join(pieces) + "}")
        shards[i] = None
    del shards
    ep_shards = defaultdict(dict)
    for epid, text in episodes.items():
        ep_shards[epid % SHARDS][str(epid)] = text
    del episodes
    for i, shard in ep_shards.items():
        write(f"episodes/{i}.json", shard)
    log(f"events/ ({SHARDS} files) and episodes/ ({len(ep_shards)} files) written")
    del ep_shards

    # ---- Tables ------------------------------------------------------------------------------
    cols = ["s", "t", "y", "m", "events", "deaths", "injuries", "damage",
            "l_events", "l_deaths", "l_injuries", "l_damage"]
    write("cube.json", table(cols, [[*k, *v] for k, v in sorted(cube.items())]))
    years = sorted({y for (_, _, y, _) in cube})
    log(f"cube.json ({len(cube):,} rows)")
    del cube

    gcols = ["lat", "lon", "s", "t", "y", "events", "deaths", "injuries", "damage"]
    write("grid1.json", {"cell": 1, **table(gcols, [[*k, *v] for k, v in sorted(grid1.items())])})
    log(f"grid1.json ({len(grid1):,} rows)")
    del grid1
    blocks = defaultdict(list)
    for (la, lo, s, t, y), v in sorted(grid025.items()):
        clat, clon = la / 4, lo / 4
        key = f"{math.floor(clat / BLOCK) * BLOCK}_{math.floor(clon / BLOCK) * BLOCK}"
        blocks[key].append([num(clat), num(clon), s, t, y, *v])
    for key, rows in blocks.items():
        write(f"grid025/{key}.json", {"cell": 0.25, **table(gcols, rows)})
    log(f"grid025/ ({len(blocks)} blocks, {len(grid025):,} rows)")
    del grid025

    tcols = ["id", "date", "s", "t", "cz", "deaths", "injuries", "damage", "lat", "lon"]
    for key, rows in tiles.items():
        write(f"tiles/{key}.json", table(tcols, by_date_desc(rows)))
    log(f"tiles/ ({len(tiles)} files)")

    scols = ["id", "date", "t", "cz", "deaths", "injuries", "damage"]
    for s, rows in by_state.items():
        write(f"state/{s}.json", table(scols, by_date_desc(rows)))
    menu_states = [states[s] for s in sorted(by_state) if len(by_state[s]) > MENU_MIN_EVENTS]
    log(f"state/ ({len(by_state)} files)")
    del by_state

    write("notable.json", table(["id", "date", "s", "t", "cz", "deaths", "injuries", "damage"],
                                by_date_desc(notable)))
    log(f"notable.json ({len(notable):,} rows)")

    # Every calendar day gets a file, even one with no events (02-29 always has some).
    for m in range(1, 13):
        for d in range(1, 32):
            try:
                time.strptime(f"2000-{m:02d}-{d:02d}", "%Y-%m-%d")  # 2000 is a leap year
            except ValueError:
                continue
            md = f"{m:02d}-{d:02d}"
            write(f"onthisday/{md}.json", [item for _, item in sorted(days.get(md, []), reverse=True)])
    log("onthisday/ written")

    write("meta.json", {
        "types": types, "states": states, "menu_states": menu_states,
        "first_year": years[0], "last_year": years[-1],
        "totals": dict(zip(["events", "deaths", "injuries", "damage"], totals)),
        "notable_min_damage": NOTABLE_MIN_DAMAGE, "shards": SHARDS,
        "tiles": sorted(tiles), "grid025_blocks": sorted(blocks),
    })

    # ---- Swap into place, then report ------------------------------------------------------------
    # Something else may have cleared _site/ while we ran (build_site.py keeps only data/), so make
    # sure every file is still there before replacing a good dataset with this one.
    missing = [p for p in WRITTEN if not (TMP / p).is_file()]
    if missing:
        raise SystemExit(f"{len(missing):,} of {len(WRITTEN):,} files vanished from {TMP} during the build "
                         f"(e.g. {missing[0]}); _site/data was left as it was. Run it again.")
    old = SITE / "data.old"
    if old.exists():
        shutil.rmtree(old)
    if OUT.exists():
        OUT.rename(old)
    TMP.rename(OUT)
    if old.exists():
        shutil.rmtree(old)

    files = [p for p in OUT.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    big = max(files, key=lambda p: p.stat().st_size)
    log(f"Done: {len(files):,} files, {size / 1e6:,.1f} MB in {OUT.relative_to(ROOT)}/; "
        f"largest {big.relative_to(OUT)} ({big.stat().st_size / 1e6:,.1f} MB)")
    if size > 1e9 or big.stat().st_size > 100e6:
        print("WARNING: over GitHub Pages limits (site <= 1 GB, files <= 100 MB)")


if __name__ == "__main__":
    main()
