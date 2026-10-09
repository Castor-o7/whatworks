# What Works? News Center

A news site for the What Works? channel. It covers politics, economics, tech, science, videos and
clips from YouTube/Twitch, and the **Storm Desk**, an explorer over 75 years of NOAA storm records, with
**Then & Now** (`/storms/then-and-now/`) for comparing two eras fairly ([docs/THEN_AND_NOW.md](docs/THEN_AND_NOW.md)).

It's a fully static site, published on GitHub Pages at <https://castor-o7.github.io/whatworks/>.
There is no server: the storm database is pre-summarized into JSON files, and every chart, map and
event list is computed in the reader's browser. The contract between the pieces (data files, the
browser data layer, pages and URLs) is [docs/STATIC_SITE.md](docs/STATIC_SITE.md).

## Build and preview

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python scripts/build_storm_db.py    # once (~1 min): stormdata/*.csv.gz -> data/storms.db
.venv/bin/python scripts/fetch_cpi.py         # only to add new years of inflation data (needs the network)
.venv/bin/python scripts/build_data.py        # once per database rebuild (minutes): -> _site/data/
.venv/bin/python scripts/build_site.py        # after every change (~1 s): pages + static -> _site/
.venv/bin/python scripts/serve.py             # preview at http://localhost:8000/whatworks/
```

`build_site.py` never touches `_site/data/`, so editing a post or a template only needs that one
step. It reads `_site/data/meta.json.gz` for the Storm Desk's totals and dropdowns, so run it after
`build_data.py`. `serve.py` (add `--port 8001` to change the port) serves `_site/` the way Pages does:
under `/whatworks/`, with directory `index.html` pages and `404.html` for anything missing.

## Publish

```sh
scripts/deploy.sh                    # or: scripts/deploy.sh "Post: heat deaths"
```

This pushes `_site/` to the `gh-pages` branch of `castor-o7/whatworks`. `_site/` is its own small
git repo (made on the first run), so the built site never gets committed to `main`. The script
refuses to run until `_site/data/meta.json.gz` exists. In the GitHub repo settings, set
**Pages → Source** to "Deploy from a branch", branch `gh-pages`, folder `/ (root)`.

## Write a post

```sh
scripts/new_post.py "Your headline" --section science   # start a private draft
scripts/preview.py                                       # preview, drafts included
scripts/publish.py                                       # delete "draft: true" first; builds, deploys, backs up
```

Drafts never leave this computer (the repo is public); `publish.py` commits only published posts,
and a git hook in `scripts/git-hooks/` (switched on by those scripts) refuses any commit that includes a
draft. `publish.py` also stops on template leftovers or an unreadable post (`--force` overrides the
leftover check).
Citations are footnotes (`[^1]`) that become a Sources list. Everything a writer needs, including
videos, links and storm charts, is in **[docs/WRITING.md](docs/WRITING.md)**.

## Layout

| Path | What it is |
|---|---|
| `site.toml` | Site name, tagline, `base_url`, channel links, map tiles, sections |
| `content/posts/` | Markdown posts |
| `content/tools/` | One Markdown file per tool on `/tools/` (Josh's software, starting with the Storm Desk) |
| `app/content.py` | Post loading, Markdown, base-path link rewriting, video-embed URLs |
| `app/tools.py` | Tool loading and checks (reuses content.py's front-matter reader) |
| `app/templates/` | Page templates (Jinja) |
| `app/static/` | CSS, the browser data layer (`data.js`), charts, explorer, map and event-page JS |
| `app/static/vendor/` | Leaflet, topojson-client, US state shapes (served locally) |
| `scripts/build_storm_db.py` | Builds SQLite from `stormdata/*.csv.gz` |
| `data_sources/cpi-u-annual.csv` | CPI-U annual averages (BLS, via FRED series CPIAUCNS) with a provenance header; committed so data builds work offline |
| `scripts/fetch_cpi.py` | Downloads CPIAUCNS from FRED and rewrites `data_sources/cpi-u-annual.csv` (complete years only) |
| `scripts/build_data.py` | Precomputes `_site/data/` (summaries, map grids, tiles, event records) from SQLite |
| `scripts/build_site.py` | Renders the pages and copies `app/static/` into `_site/` |
| `scripts/serve.py`, `scripts/deploy.sh` | Local preview; publish to GitHub Pages |

## What the static site can't do

**Narrative search is gone.** Full-text search over 1.9 million narratives needs a server (or a
download far too big for a browser), so the explorer filters by event type, state, years and map
area only. Without a state or map area selected, the event list draws from the notable events
(any death, injury, or at least $250K damage), and the page says so. Charts, totals, and the map
still cover every event.

## The map

The Storm Desk map has two views driven by the same filters:

- **Locations** shows events with coordinates, aggregated to a grid that refines as you zoom (1° down to about 7 km).
  Past zoom 8 it shows individual events, and clicking one opens its report.
- **By state** colors each state by every matching event, so it's the complete view.

**Near me / Limit to map area.** "Near me" asks the browser for the reader's location and centers the
map there. "Limit everything to the map area" filters the charts and event list to whatever the map
shows, follows panning, and goes into the URL (`?area=south,west,north,east`) so an area view can be
linked. Everything is computed in the browser, so the reader's position never leaves their device.
Browsers only allow geolocation on HTTPS (or localhost); GitHub Pages is HTTPS. Area mode necessarily
drops events without coordinates, and the page says so. Very large areas ask the reader to zoom in.

Only about 61% of events have coordinates. Zone-reported hazards (heat, winter storms, drought, high
wind) have none, so the map switches to By state when most of a selection can't be placed, and
it always states the coverage. Basemap tiles are set in `site.toml` under `[map]`.

## Storm data caveats (worth repeating in stories)

- Only tornado (1950–), thunderstorm wind and hail (1955–) were recorded until 1993; the full modern list of event types starts in 1996 (34 types that year, ~50/year lately).
- Damage is reported estimates in nominal dollars, not inflation-adjusted (Then & Now converts it to 2024
  dollars with CPI-U). Before 1993 it is categorical: only a handful of round values per year.
- Deaths are counted only when attributed to a weather event; attribution practices vary.
- Only ~61% of events have coordinates (see The map).
- About 1,100 narratives contain a character NOAA's own files lost (shown as �). The build repairs the
  unambiguous cases (apostrophes, °F).
