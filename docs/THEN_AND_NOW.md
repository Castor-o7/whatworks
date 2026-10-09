# Then & Now (Storm Desk) — contract

**Question it answers:** "Are storms getting worse, or are we just counting more?" It compares two eras
of NOAA storm records *fairly*, and says plainly what the records can't tell us.

URL: `/storms/then-and-now/` (under the site base). It's listed as its own tool in `content/tools/`.

## Principles (non-negotiable)

1. **Only compare what was recorded in both eras.** An event type is *comparable* when NOAA recorded it
   in **every year** of both eras, judged **nationally** from `cube.json` (record-keeping is national,
   so a state filter never changes which types are comparable). Everything else is listed under
   "Can't be compared yet", with the first year it appears in every subsequent year.
   A **toll** (deaths, injuries, damage) counts for a compared type in an era only if the national records hold
   it from the era's **first year** (its first nonzero year ≤ era start). One that starts part-way through an era
   (Hail damage from 1993, Thunderstorm Wind deaths from 1983) shows as "recorded from YYYY", is left out of the
   summary sum, and is named in the caveats: averaging it over the whole era would count years that hold nothing.
   Recorded every year is not the same as like with like: NOAA split some types after 1996 (Heat / Excessive Heat,
   Cold/Wind Chill / Extreme Cold/Wind Chill, Tropical Storm / Hurricane, ...). A static family map in `data.js`
   (`FAMILIES`) finds related types that aren't compared; the page says how much each holds in each era.
2. **Recorded events, not storms.** Label counts as *recorded events* everywhere. A rise in reports
   isn't by itself a rise in storms. Tornado rows are county segments of tracks (SPC Tornado FAQ), so the
   tornado lens counts *recorded tornado segments*.
3. **Real dollars by default.** Damage is shown in base-year dollars (the latest year in `cpi.json`,
   2024), adjusted per event year with CPI-U annual averages, with a toggle to show the dollars as reported.
   Dollars as reported get no percent change (they are dollars of different years).
4. **Every sentence is either computed from the data or cited to a source that has been opened and
   checked.** No claims from memory. Generated sentences use the actual numbers.
5. **Name the known breaks in the record**, computed from the data where possible: damage values
   before 1993 are category midpoints, not estimates (6–10 distinct values a year, computed on the page from `damage_values.json`; real estimates from
   1996, with 1993–1995 transitional); which event types each era includes; F vs EF scale.

## Data (`scripts/build_data.py` → `_site/data/`, gzipped like everything else)

| File | Contents |
|---|---|
| `tornado_scale.json` | cols `s,y,scale,events,deaths,injuries,damage` for `event_type = 'Tornado'`; `scale` is `"0"`–`"5"` (F and EF merged by number) or `"U"` (EFU, null, or anything else). |
| `cpi.json` | `{"series": "CPIAUCNS", "source": "...", "retrieved": "YYYY-MM-DD", "base_year": 2024, "annual": {"1950": 24.1, ...}}`, written from the committed `data_sources/cpi-u-annual.csv`. |
| `damage_values.json` | `{"<year>": <number of distinct nonzero damage_property values that year>}`. Lets the page show the categorical-damage break from the data itself. |

`scripts/fetch_cpi.py` downloads FRED series **CPIAUCNS** (CPI-U, all items, U.S. city average, not seasonally
adjusted; source: U.S. Bureau of Labor Statistics) from `https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS`,
averages **complete** calendar years (12 months), and writes `data_sources/cpi-u-annual.csv` with a provenance header
(`# source, series, url, retrieved, method`). The CSV is committed so builds are reproducible offline.

## Client (`app/static/data.js` → `WWData`)

- `cpi()` → `{base_year, factor(year)}` where `factor(y) = annual[base_year] / annual[y]`.
- `thenNow(then: [y0, y1], now: [y0, y1], f: {state?}, opts: {dollars: "real"|"nominal"})` →

  ```
  { then: {from, to, years}, now: {from, to, years}, base_year,
    comparable: [{type, then: {events, deaths, injuries, damage}, now: {...}}],   // per-year averages
    only_now: [{type, since}], only_then: [{type, since}],                        // not comparable
    tornado: {then: {weak, strong, unknown}, now: {...}},                         // events per year; weak = 0–1, strong = 2–5
    damage_categorical: {then: bool, now: bool},                                 // era overlaps 1950–1992
    types_recorded: {then: n, now: n} }
  ```
  Each `comparable` row also carries `recorded: {then: {deaths, injuries, damage}: bool, now: {...}}` (toll held
  from the era's first year), `first_recorded: {deaths, injuries, damage}` (national first nonzero year or null)
  and `related: [{type, since, first, last, then: {...}, now: {...}}]` (same-family types not compared, per-year).
  `comparable` is sorted by `now.events` desc. Per-year average = era total / number of years in the era.
  `f.state` filters the numbers (not which types are comparable). Damage is real or nominal per `opts`.
- `byYearReal(f, dollars)` → `byYear(f)` with `damage` converted when `dollars === "real"`.
- `tornadoByYear(f)` → `[{year, weak, strong, unknown}]`.

## Page (`app/templates/thenandnow.html` + `app/static/then-now.js`)

- **Controls** (one row, URL state like the Storm Desk): Then from/to, Now from/to, presets
  (default *1955–1974 vs 2005–2024*; also *1975–1994 vs 2005–2024* and *1996–2005 vs 2015–2024*), State, Measure
  (`events|deaths|injuries|damage`), Dollars (*2024 dollars* / *as reported*; only shown for damage). Eras may differ
  in length; say so when they do. Reject eras outside the data range or with from > to, with a message: the
  offending inputs get `aria-invalid`, results on screen stay dimmed (`tn-stale`), and the URL keeps the last
  valid eras. A `state` in the URL is matched to the menu ignoring case; an unknown one is dropped with a note.
- **The comparison:** one row per comparable type: per-year average Then → Now, change as `+x%`/`−x%` (or "new"
  if then = 0; a drop to a nonzero value shows at most `−99.9%`; when Then is under one event/death/injury a year
  the change is a per-year difference like `+2.6/yr`; "n/a" for dollars as reported). Averages under 1 show two
  significant digits (0.05), as a paired-dot ("dumbbell") chart with a legend (Then, Now) plus a table view. Categorical slots 1–2
  of the dataviz palette, validated with the dataviz validator.
- **The tornado lens:** weak (F/EF0–1) vs strong (F/EF2+) recorded tornado segments per year in each era, one
  generated sentence with the real numbers (totals instead of a percent when Then is under one a year), a cited
  note from the SPC Tornado FAQ when an era starts before 2007 (F ratings were "largely a judgment call"; strong
  tornadoes show "very little overall change" since the 1950s), and a two-series line chart by year (legend, era
  bands shaded) in categorical slots 3 and 7, so blue/orange keep meaning Then/Now.
- **Can't be compared yet:** the non-comparable types with the year each began being recorded every year.
- **What the record can't tell us:** caveats generated from the data (damage categories, types per era, F vs EF), plus
  static ones (deaths need attribution; no population adjustment; reports depend on observers). Cited claims use
  the same Sources style as posts.
- **Shortcode for posts:** `[[then-now then="1955-1974" now="2005-2024" state="Oklahoma" metric="deaths"]]` renders a compact
  version (comparison chart + summary and tornado sentences + a "Notes:" line with the breaks that apply, from
  `compactNotes()` + "Open in Then & Now" link). `app/content.py` turns it into
  `<figure class="then-now" data-then="1955-1974" data-now="2005-2024" data-state="..." data-metric="...">` and `check()`
  validates it (years in range, from ≤ to, metric name), like `[[storm-chart]]`.

Light and dark mode, 390px mobile, no new external dependencies.
