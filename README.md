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

The source, drafts included, lives in the **private** repo `Castor-o7/whatworks-studio`. GitHub Actions
publishes from it to the public `Castor-o7/whatworks`; nothing is deployed from a laptop
([docs/STUDIO.md](docs/STUDIO.md)).

| Public branch | What | Written by |
|---|---|---|
| `gh-pages` | The built site, which Pages serves (Settings > Pages: "Deploy from a branch", `gh-pages`, `/ (root)`) | CI |
| `site-data` | The storm data tree (`_site/data/`), one orphan commit | `scripts/publish_data.sh` |
| `main` | The code, without `content/`, under generic commit messages | CI |

On every push to the studio's `main` (and from Actions > Publish > Run workflow),
`.github/workflows/publish.yml` runs `scripts/ci_publish.py`: the same checks `publish.py` runs, a build
without drafts, a search of the build for any trace of a draft, then a push of `_site/` (pages + data) to
`gh-pages` and of the code to `main`. A published post, tool or paper that fails the checks stops it with
nothing deployed; drafts never do. Each run also uploads a **draft-preview** artifact (the site with
drafts, every paper PDF, and a list of problems; private, kept 7 days).

```sh
scripts/publish.py            # writing: check, build, commit content/ (drafts too), push to the studio
scripts/publish_data.sh       # after build_data.py: storm data -> public site-data, then start a deploy
scripts/ci_publish.py --help  # what CI runs; works locally against any git remotes (--public, --push-url)
```

### One-time setup

```sh
scripts/setup_studio.sh --dry-run   # print the plan; changes nothing, contacts nothing
scripts/setup_studio.sh             # do it, asking before each step
```

It needs the GitHub CLI (`gh auth login`), the studio code committed on `main`, and `_site/data/`. It
creates the private studio repo; generates an ed25519 deploy key in a temporary folder, adds its public
half as a **write** deploy key on the public repo only, stores the private half as the studio secret
`PUBLIC_DEPLOY_KEY`, and deletes the key files; pushes the storm data to `site-data`; pushes `main` to the
studio (which starts the first deploy); and points `origin` at the studio, with the public repo as the
remote `public`. Every step is skipped when it's already done, so it's safe to run again. Until it has
run, `publish.py` and the git hook refuse to commit drafts (origin is still the public repo).

After setup this checkout never pushes to the public repo, since it holds every draft (only CI writes
there): the remote `public` is fetch-only (its push URL is set to `NO_PUSH_public_is_written_by_CI_only`,
so `git push public` fails; `publish_data.sh` reads its fetch URL and pushes from its own repo in
`.cache/`), and the `scripts/git-hooks/pre-push` hook refuses any push to the public repo's URL.

The TeX Live step (`TeX-Live/setup-texlive-action@v4`, which replaced the deleted
`teatimeguest/setup-texlive-action`) can only be proven by the first real run on GitHub. If it fails
there, look at that step's log: a package missing from its `packages:` list is the usual cause.
Compile failures are cached in `.cache/papers/` only together with the TeX installation they ran
on, so once the package list is fixed the next run compiles again.

A deploy key added with `gh` is tied to the GitHub CLI's access to your account: if that access is ever
revoked, the key disappears and deploys fail with "Permission denied (publickey)". Run
`scripts/setup_studio.sh` again; it makes a new key.

## Write a post

```sh
scripts/new_post.py "Your headline" --section science   # start a private draft
scripts/preview.py                                       # preview, drafts included
scripts/publish.py                                       # delete "draft: true" first; checks, then pushes to the studio
```

Or write in the browser at <https://github.dev/Castor-o7/whatworks-studio> and commit: GitHub builds and
publishes the same way. Drafts are saved in the private studio repo and never reach the public site or
repo. Writing in both places? Run `git pull --rebase --autostash` before you start on your computer
(`publish.py` stops and says so if you forget). A publish stops on template leftovers in a post being published (`--force`, or `[force]` in a commit
message, overrides that) and on an unreadable post or a paper that doesn't compile (nothing overrides those).
Citations are footnotes (`[^1]`) that become a Sources list. Everything a writer needs, including
videos, links, storm charts, images and how a shared link previews, is in **[docs/WRITING.md](docs/WRITING.md)**.

## Papers (LaTeX → PDF)

```sh
scripts/new_paper.py "Your title" [--engine xelatex]   # content/papers/<slug>/: paper.md + main.tex + references.bib
scripts/build_papers.py [--drafts] [slug ...]           # compile only, to see LaTeX errors (build_site.py runs it too)
```

Each paper is a folder in `content/papers/` published at `/papers/<slug>/` (abstract, Download PDF with page
count and size, an embedded viewer, a Cite box with BibTeX) with the PDF at `/papers/<slug>/<slug>.pdf`.
`build_papers.py` compiles with `latexmk` (pdflatex, xelatex or lualatex per paper; shell escape off; latexmkrc
ignored; 5-minute limit) in a clean copy of the folder, caching results in `.cache/papers/` by a hash of the
sources, so only changed papers take LaTeX time. Needs a TeX distribution with `latexmk` and `biber` (MacTeX
locally; CI installs TeX Live). Drafts are compiled only with `--drafts`; a published paper that fails to compile
stops the publish. Write papers in the browser too: GitHub compiles them, and the draft preview has the PDFs.
Details: [docs/WRITING.md](docs/WRITING.md), "Papers".

## Sharing

Every page carries link-preview tags (Open Graph + Twitter card, absolute URLs from `site_url` +
`base_url` in `site.toml`), so a pasted link unfurls in Discord, Bluesky, X, Facebook, iMessage and Slack.
Posts and tools get a share image: their `image:` (from `content/images/`), a YouTube thumbnail, or a
1200x630 title card that `build_site.py` draws with Pillow from the fonts in `app/fonts/` (cached in
`.cache/og/`, byte-identical on every build). The build also writes an Atom feed (`/feed.xml`, the 20
newest published posts) and `/sitemap.xml`. The contract is [docs/SHARING.md](docs/SHARING.md).

## Layout

| Path | What it is |
|---|---|
| `site.toml` | Site name, tagline, `site_url` + `base_url`, channel links, map tiles, sections |
| `content/posts/` | Markdown posts |
| `content/tools/` | One Markdown file per tool on `/tools/` (Josh's software, starting with the Storm Desk) |
| `content/papers/<slug>/` | One folder per LaTeX paper: `paper.md` (front matter + note) and `main.tex` (+ `.bib`, figures) |
| `content/PAPER_TEMPLATE/` | What `new_paper.py` copies for a new paper |
| `content/images/` | Share images and in-post pictures; the ones published posts use are copied to `_site/images/` |
| `app/content.py` | Post loading, Markdown, base-path link rewriting, video-embed URLs |
| `app/tools.py` | Tool loading and checks (reuses content.py's front-matter reader) |
| `app/papers.py` | Paper loading and checks (same front-matter reader; drafts fail closed) |
| `app/share.py` | Link previews: title cards (Pillow), preview descriptions, image checks |
| `app/fonts/` | Fraunces and Source Sans 3 for the title cards (SIL Open Font License; each folder has its `OFL.txt`) |
| `app/templates/` | Page templates (Jinja) |
| `app/static/` | CSS, the browser data layer (`data.js`), charts, explorer, map and event-page JS |
| `app/static/vendor/` | Leaflet, topojson-client, US state shapes (served locally) |
| `scripts/build_storm_db.py` | Builds SQLite from `stormdata/*.csv.gz` |
| `data_sources/cpi-u-annual.csv` | CPI-U annual averages (BLS, via FRED series CPIAUCNS) with a provenance header; committed so data builds work offline |
| `scripts/fetch_cpi.py` | Downloads CPIAUCNS from FRED and rewrites `data_sources/cpi-u-annual.csv` (complete years only) |
| `scripts/build_data.py` | Precomputes `_site/data/` (summaries, map grids, tiles, event records) from SQLite |
| `scripts/build_site.py` | Renders the pages, share cards, `feed.xml` and `sitemap.xml`, copies `app/static/` and paper PDFs into `_site/` |
| `scripts/build_papers.py`, `scripts/new_paper.py` | Compile papers (latexmk, cached in `.cache/papers/`); start a new one |
| `scripts/serve.py` | Local preview (`--dir` serves another build, such as a downloaded draft preview) |
| `scripts/publish.py`, `scripts/checks.py` | Check and push your writing to the studio repo; the checks GitHub runs too |
| `scripts/ci_publish.py`, `.github/workflows/publish.yml` | CI: build without drafts, leak check, deploy to the public repo |
| `scripts/publish_data.sh`, `scripts/setup_studio.sh` | Storm data -> public `site-data`; one-time studio setup |

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
