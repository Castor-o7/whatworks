# Writing for What Works?

Three commands cover the whole loop. Run them from the project folder.

```sh
scripts/new_post.py "Your headline" --section science   # 1. start a draft
scripts/preview.py                                       # 2. see it (drafts included)
scripts/publish.py                                       # 3. make it live
```

1. **Start.** `new_post.py` creates `content/posts/<headline-as-url>.md` as a private draft, already shaped
   by the template below. Sections: `politics`, `economics`, `tech`, `science`, `storms`, `channel`.
   Add `--video <url>` to embed a YouTube or Twitch video at the top, and `--tags "a, b"` for tags.
2. **Write and preview.** Open the file in a code editor such as VS Code. Don't use TextEdit: it turns
   `"` into curly quotes even in plain-text files (if you must, first turn off Edit > Substitutions >
   Smart Quotes). `preview.py` builds the site with drafts, serves it at
   <http://localhost:8000/whatworks/> and opens the draft you saved most recently. Drafts show a
   "Draft preview" banner. After edits, stop the preview with Ctrl+C and re-run `preview.py` (or leave
   it running, run `scripts/build_site.py --drafts` in another terminal, and refresh). The build prints
   a `warning:` line for anything it can't make sense of, such as a mistyped storm chart.
3. **Publish.** Delete the `draft: true` line and set `date:` to today (it's the day you started the
   draft until you change it), then run `publish.py`. It checks the post, rebuilds without drafts,
   deploys, and backs your published posts up to GitHub. Try `publish.py --dry-run` first to see what
   will happen. Live about a minute later.

**What publish.py checks.** It stops, changing nothing, if a post that isn't a draft can't be read (a
bad `date:`, say). It also stops if a post you're publishing or changing still has template leftovers
(the placeholder summary, an empty `##` heading, a `[^ref]` with no source) or a storm chart it can't
make sense of. Fix it, or run `publish.py --force` to publish anyway. A post going live for the
first time is listed with its date, and you're offered to change the date to today.

**Drafts are private.** The GitHub repo is public, so drafts are never committed or deployed; they live
only on this computer until you publish. (Back up the `content/posts` folder yourself if a draft matters
to you before it's published.) Some details:

- `publish.py` backs up only `content/posts/<name>.md` files that aren't drafts (plus deleted posts and
  the template). Anything else under `content/`, such as editor backups or a `content/drafts/` folder,
  is listed as "not backing up" and stays on this computer.
- If you commit with git, GitHub Desktop or your editor yourself, the **draft guard** (a git hook in
  `scripts/git-hooks/`, switched on the first time you run any of the three commands) refuses any
  commit that includes a draft. Unstage the draft (`git restore --staged <file>`) and commit again.
- Anything other than a plain "no" keeps a post a draft: `draft: true`, `yes`, `True`, an empty
  `draft:`, a typo. To publish, delete the line (or write `draft: false`). If a file's front matter
  can't be read at all, it's never published; the build names the file and says why.

## The shape of a take

Every new draft starts with this, as prompts in comments (comments are never published):

- **What happened.** The development in plain words: who, what, when, where.
- **Why it matters.** Why a busy person should care: everyday life, or the bigger horizon it points at.
- **What works.** Your take: what actually helps, what the evidence says, what you'd do.
- **Sources.** Built automatically from your citations.

Delete any part that doesn't fit; the shape is a starting point, not a rule.

## Citations

Put `[^1]` right after a claim, and the source anywhere below (the bottom is tidiest):

```md
Heat has killed more Americans than tornadoes since 1996.[^noaa]

[^noaa]: NOAA Storm Events Database, 1996–2024. https://www.ncdc.noaa.gov/stormevents/
```

Footnotes are numbered in the order they're first cited in the text (not the order you list the
sources) and gathered into a **Sources** list at the end of the post, each with a link back to where
it was cited. Labels can be words (`[^noaa]`) or numbers. Plain URLs in a source become links on their
own, including ones with parentheses (Wikipedia's `.../Mercury_(planet)`) or in parentheses
(`NOAA (https://www.noaa.gov/heat)`). A long source can continue on the next line if you indent it.
Every `[^label]` you cite needs a matching `[^label]: ...` line; the build warns you if one is missing.

## Videos, links and charts

- **Video at the top:** `video: <url>` in the front matter. Works with YouTube videos, Shorts, live,
  youtu.be links, Twitch VODs (`twitch.tv/videos/123`) and Twitch clips.
- **Links to the site:** write them from the site root, e.g. `[Storm Desk](/storms)` or
  `[that story](/post/heat-is-the-deadliest-storm)`. The build adds the `/whatworks` part for you.
  Any Storm Desk view (filters, map area) can be linked by copying the address bar.
- **Storm charts inside a post:** one line, drawn live in the reader's browser.

  ```md
  [[storm-chart event_type="Tornado" state="Oklahoma"]]
  [[storm-chart chart="types" metric="damage" state="Texas" year_from="2000"]]
  ```

  Options: `chart` = `years` (default) · `types` · `states` · `months`; `metric` = `events` · `deaths` ·
  `injuries` · `damage`; also `event_type` (comma-separate several), `state`, `year_from`, `year_to`,
  `title`, `sub`, `limit`.

  `state` is a full name (`Oklahoma`, not `OK`) and `event_type` is NOAA's exact label (`Tornado`,
  `Excessive Heat`, `Thunderstorm Wind`), both spelled and capitalized as in the Storm Desk's **State**
  and **Event type** menus. The build warns about anything it doesn't recognize and suggests the
  closest match; check for `warning:` lines after `preview.py` or `publish.py`.

## Front matter reference

```yaml
---
title: The headline
date: 2026-10-08
section: science
summary: One sentence under the headline and on cards.
video:
tags: heat, grid
draft: true
---
```

- The block starts and ends with lines that are exactly `---`, so a `---` inside a title or summary
  is safe. (It shows as typed there; type `—` itself for an em dash. In the body, `---` becomes one.)
- `date` sorts the site, newest first. Write it as `2026-10-08`, and update it on the day you publish.
- `section` is one of the sections listed above. `video` and `tags` are optional; leave them empty.
- `draft: true` keeps the post private. Delete the line to publish.
- Quotes around a value are optional (`title: "Heat: why it kills"` works). A `#` with a space before
  and after it starts a comment, so to use one in a title, put the title in quotes.
