# Static site contract (GitHub Pages)

The site is served by GitHub Pages at `https://castor-o7.github.io/whatworks/`, so there is **no server**.
Everything is precomputed into `_site/` and the browser does the querying. This file is the contract
between the three pieces: the data builder, the client data layer, and the page builder.

```
data/storms.db  --scripts/build_data.py-->  _site/data/**          (slow, run once; ~minutes)
content + app/templates --scripts/build_site.py-->  _site/**.html, _site/static/**  (fast; never touches _site/data)
scripts/serve.py      preview _site at http://localhost:8000/whatworks/ exactly as Pages serves it
scripts/deploy.sh     publish _site to the gh-pages branch
```

`base_url = "/whatworks"` lives in `site.toml`. Every link, asset and fetch is prefixed with it.
Templates get it as `{{ base }}`; JavaScript reads `window.WW_BASE` (set in `base.html`). Where a full URL
is needed (link previews, the feed, the sitemap), it is `site_url + base_url + path`: templates get
`{{ abs_base }}` (`https://castor-o7.github.io/whatworks`). Link previews, feed and sitemap: [SHARING.md](SHARING.md).

## Conventions

- **Every data file is stored gzipped as `<name>.gz`** (e.g. `cube.json.gz`); the tables below use the logical
  names. Gzip takes the dataset from ~905 MB to ~207 MB, well under Pages' 1 GB limit. Files are written with
  `mtime=0` so rebuilds are byte-identical and git only uploads what changed. Pages serves them as plain
  `application/gzip`; `data.js` `load()` appends `.gz` and decompresses with `DecompressionStream`.
- JSON, UTF-8, compact separators `(",", ":")`. Tabular files are `{"cols": [...], "rows": [[...], ...]}`.
- `s` = state index into `meta.states`, `t` = type index into `meta.types`.
- `date` in tables is an int `YYYYMMDD`. Damage values are whole dollars (int), property + crops.
- "Located" means `begin_lat IS NOT NULL AND begin_lon IS NOT NULL AND begin_lat != 0`.
- "Notable" means `deaths > 0 OR injuries > 0 OR damage >= 250000`.

## Data files (`_site/data/`)

| File | Contents |
|---|---|
| `meta.json` | `types` (all event types, most frequent first), `states` (every state/marine label, A–Z), `menu_states` (states with > 50 events, for the dropdown), `first_year`, `last_year`, `totals` {events, deaths, injuries, damage}, `notable_min_damage` (250000), `shards` (4096), `tiles` (list of existing tile keys `"lat_lon"`), `grid025_blocks` (list of existing block keys) |
| `cube.json` | cols `s,t,y,m,events,deaths,injuries,damage,l_events,l_deaths,l_injuries,l_damage` grouped by state, type, year, month. `l_*` = the located portion. Powers every chart, the state map, and coverage. |
| `grid1.json` | `{"cell": 1, cols: lat,lon,s,t,y,events,deaths,injuries,damage}`. Located events grouped by `round(lat)`, `round(lon)` (cell centers at integer degrees), state, type, year. |
| `grid025/<B>.json` | Same columns with `"cell": 0.25`, centers `round(lat*4)/4`. Split into 5° blocks; `B = "<floor(clat/5)*5>_<floor(clon/5)*5>"` as ints, e.g. `35_-100`, computed from the cell center. |
| `tiles/<K>.json` | Every located event in a 1° tile, `K = "<floor(lat)>_<floor(lon)>"` as ints. cols `id,date,s,t,cz,deaths,injuries,damage,lat,lon` (lat/lon rounded to 4 decimals). |
| `state/<s>.json` | Every event in state index `s`. cols `id,date,t,cz,deaths,injuries,damage`, sorted by date descending. |
| `notable.json` | Every notable event. cols `id,date,s,t,cz,deaths,injuries,damage`. |
| `events/<id % 4096>.json` | `{"<id>": record}` where record = `{id, episode_id, date: "YYYY-MM-DD", year, state, cz_name, event_type, deaths, injuries, damage_property, damage_crops, magnitude, magnitude_type, tor_f_scale, lat, lon, narrative, fatalities: [{type: "D"|"I", age, sex, location}]}`. Fields that would be null are omitted (missing = null; test with `== null`), as is an empty `fatalities`. A record whose episode narrative differs from its episode's usual one (or that has no `episode_id`) carries its own `episode_narrative`. |
| `episodes/<episode_id % 4096>.json` | `{"<episode_id>": "episode narrative"}`; only episodes that have one. |
| `tornado_scale.json` | cols `s,y,scale,events,deaths,injuries,damage` for tornadoes; `scale` is `"0"`–`"5"` (F and EF merged by number) or `"U"` (EFU, null, anything else). Then & Now's tornado lens. |
| `cpi.json` | `{"series": "CPIAUCNS", "source", "retrieved": "YYYY-MM-DD", "base_year", "annual": {"1950": 24.07, ...}}`: CPI-U annual averages from the committed `data_sources/cpi-u-annual.csv` (written by `scripts/fetch_cpi.py`). Real dollars = nominal × `annual[base_year] / annual[year]`. |
| `damage_values.json` | `{"<year>": n}`: distinct nonzero `damage_property` values that year, so Then & Now can show from the data that pre-1993 damage is categorical. |
| `onthisday/<MM-DD>.json` | 366 files (includes `02-29`). Top 6 events beginning on that calendar day in any year, ordered by `deaths*1e9 + injuries*1e7 + damage` desc: `[{id, date: "YYYY-MM-DD", state, cz, type, deaths, injuries, damage, excerpt}]`; excerpt = event narrative with `|` replaced by a space, first 280 chars. |

Narratives keep NOAA's `|` paragraph separators; renderers split on it.

## Client data layer (`app/static/data.js` → `window.WWData`)

All methods return Promises and cache fetched files in memory. `f` is a filters object:
`{state?: label, event_type?: "A" or "A,B", year_from?, year_to?, area?: [s,w,n,e] or "s,w,n,e"}`.
Unknown or empty values are ignored. `metric` is one of `events|deaths|injuries|damage`.

| Method | Returns (same shapes the old FastAPI endpoints returned) |
|---|---|
| `meta()` | `meta.json` |
| `byYear(f)` | `[{year, events, deaths, injuries, damage}]`, years with data only, ascending |
| `breakdown(by, metric, limit, f)` | `[{label, value}]`; `by` = `event_type|state|month`; month labels are numbers 1–12 in month order; others by value desc; rows with value ≤ 0 dropped |
| `events(sort, limit, offset, f)` | `{scope, rows: [{event_id, begin_date: "YYYY-MM-DD", state, cz_name, event_type, deaths, injuries, damage}]}`; `sort` = `date|deaths|injuries|damage` (desc). `scope` says which source answered: `"area"` (tiles; exact for located events), `"state"` (state file; exact), or `"notable"` (no state/area; only notable events) |
| `coverage(metric, f)` | `{total, located}` |
| `map(zoom, bbox, metric, f)` | `{mode: "cells"|"events", cell?, coverage, items}`. Items: cells `{lat, lon, value, events}`; events `{event_id, begin_date, state, cz_name, event_type, deaths, injuries, damage, lat, lon}`. zoom ≤ 4 uses `grid1`; 5–6 uses `grid025` blocks in view; 7–8 aggregates tiles in view to cells of 0.125 / 0.0625 (center `round(lat/cell)*cell`); ≥ 9 returns individual events from tiles (top 1,500 by metric; for `events`, most recent). `f.area` is ignored here (the bbox already bounds it). |
| `event(id)` | event record + `episode_narrative`: the record's own if it has one, else the `episodes` entry (or null) |
| `onThisDay("MM-DD")` | the `onthisday` list |

With `f.area`, `byYear`/`breakdown`/`events`/`coverage` are computed from the tiles intersecting the area
(located events only). If that is more than 80 tiles, they reject with `Error("area-too-large")` and the UI
asks the reader to zoom in. Narrative full-text search is not available on the static site.

## Pages and DOM hooks

| URL (under base) | Template | Notes |
|---|---|---|
| `/` | `home.html` | "On this day" box: `<p class="box-sub" id="on-this-day-sub">` + `<ul class="event-list" id="on-this-day">`, filled by `home.js` using the reader's local date |
| `/section/<slug>/` | `section.html` | not generated for `storms` (that section is `/storms/`) |
| `/storms/` | `storms.html` | same element ids as before (`filters`, `sort`, `results`, `more`, `map-panel`, `near-me`, `area-only`, `area-status`, `chart-years`, `chart-types`, `chart-states`), minus the search input. Stat tiles rendered at build time from `meta.totals`. An element `#list-scope` above the event list where `storms.js` explains the scope (e.g. notable-only). |
| `/storms/then-and-now/` | `thenandnow.html` | Then & Now (contract: [THEN_AND_NOW.md](THEN_AND_NOW.md)), drawn by `then-now.js`. `form#tn-controls` (inputs `then_from`, `then_to`, `now_from`, `now_to`; selects `preset`, `state`, `metric`, `dollars`; the dollars field is `label.tn-dollars`) and empty containers `#tn-status`, `#tn-summary`, `#tn-compare`, `#tn-tornado`, `#tn-tornado-chart`, `#tn-unmatched`, `#tn-caveats`. Section headings and a static Sources list (`#tn-src-noaa`, `#tn-src-cpi`, `#tn-src-ef`, `#tn-src-reports`, `#tn-src-faq`) are in the template. State menu = `meta.menu_states`; the "2024 dollars" label comes from `cpi.json`'s `base_year` at build time. |
| `/storms/event/?id=N` | `event.html` | shell `<article class="story" id="event-root">`; `event.js` renders everything client-side (same markup/classes as the old server template, including the mini map) and sets `document.title`. One shell serves every id, so its head has no canonical link and no `og:url` (a shared link keeps its `?id=`) and carries `robots: noindex` |
| `/post/<slug>/` | `post.html` | `[[storm-chart ...]]` shortcodes become `<figure class="storm-chart" data-...>` rendered by `charts.js` via `WWData`; `[[then-now ...]]` becomes `<figure class="then-now" data-then="YYYY-YYYY" data-now="YYYY-YYYY" data-metric="..." [data-state="..."] [data-dollars="real|nominal"]>` (defaults filled in) rendered by `charts.js` (chart, summary and tornado sentences, a `p.tn-compact-notes` line on the breaks that apply, and the link) |
| `/tools/` | `tools.html` | one card per tool in `content/tools/*.md` (see `app/tools.py`), ordered by `order` then title |
| `/tools/<slug>/` | `tool.html` | the tool's Markdown body + the posts whose front matter says `tool: <slug>` |
| `/about/` | `about.html` | |
| `/404.html` | `404.html` | GitHub Pages serves this for unknown paths. No canonical link (it answers for every missing path); `robots: noindex` |
| `/feed.xml` | (built in `build_site.py`) | Atom 1.0: the 20 newest published posts, full HTML with absolute links; charts become links to the post. Never drafts, so it's identical with or without `--drafts` |
| `/sitemap.xml` | (built in `build_site.py`) | every published page except the event shell and 404; referenced by `<link rel="sitemap">` in each head |
| `/static/og/<slug>.png`, `/static/og/tool-<slug>.png`, `/static/og/site.png` | (drawn by `app/share.py`) | 1200x630 share cards; a post's `og:image` is its `image:`, its YouTube thumbnail, or its card. A post whose slug is `site` or starts with `tool-` or `post-` gets `post-<slug>.png`, so post, tool and site card names never overlap. `og:image:width`/`height` for an `image:` file are its size as displayed (EXIF rotation applied) |
| `/images/<file>` | (copied from `content/images/`) | only the images a rendered post or tool uses (its `image:`, or `/images/...` in its text) |

Every page's head has the link-preview tags from `base.html` (`canonical`, `og:*`, `twitter:card`, and
`article:published_time` on posts), filled from a `share` dict `build_site.py` passes to each page.
Descriptions are the summary, blurb or tagline as written (whitespace collapsed, cut to 200 characters),
escaped by Jinja like any other text, so a summary that mentions `<video>` keeps it.

Script order on every page: `data.js`, `charts.js`, `site.js`, then page scripts. Leaflet/topojson/map.js are
loaded only on `/storms/` and the event page; `then-now.js` on `/storms/then-and-now/`. Links built in JS use `` `${WW_BASE}/storms/event/?id=${id}` ``.
`_site/.nojekyll` must exist.
