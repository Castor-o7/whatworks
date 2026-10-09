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
  the template), tool files, and images in `content/images/` that a published post or tool uses. An
  image only a draft uses stays on this computer (and off the live site) until that post is published.
  Anything else under `content/`, such as editor backups or a `content/drafts/` folder, is listed as
  "not backing up" and stays on this computer.
- If you commit with git, GitHub Desktop or your editor yourself, the **draft guard** (a git hook in
  `scripts/git-hooks/`, switched on the first time you run any of the three commands) refuses any
  commit that includes a draft. Unstage the draft (`git restore --staged <file>`) and commit again.
  It also refuses a `.md` file that isn't saved as UTF-8 (TextEdit and some Windows editors can save
  UTF-16), since it can't tell whether that's a draft: re-save it as UTF-8 and stage it again.
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
- **Then & Now inside a post:** one line puts a compact version of the
  Then & Now page (`/storms/then-and-now`) in your story: the era comparison chart, one sentence about weak vs
  strong tornadoes, and an "Open in Then & Now" link to the full page with the same settings.

  ```md
  [[then-now then="1955-1974" now="2005-2024" state="Oklahoma" metric="deaths"]]
  [[then-now then="1996-2005" now="2015-2024"]]
  ```

  Options: `then` and `now` are year ranges (`1955-1974`; an en dash or a single year like `2024` works too;
  defaults `1955-1974` and `2005-2024`); `metric` = `events` (default) · `deaths` · `injuries` · `damage`
  (damage is in 2024 dollars, adjusted for inflation; add `dollars="nominal"` to show the dollars as reported);
  `state` (optional) is a full name, as for storm charts.
  The eras can be different lengths: the numbers are yearly averages. Only event types NOAA recorded in every
  year of both eras are compared, so an era before 1993 compares just tornadoes, thunderstorm wind and hail.
  The figure adds a short "Notes:" line on the breaks that apply (damage categories before 1993, eras of
  different lengths, F-scale ratings). With `dollars="nominal"` it shows no percent change, since the dollars
  are from different years.
  The build warns about years outside the data (1950–2024), a range written backwards, an unknown `metric`
  or state, and options it doesn't know.

## Sharing: link previews and the feed

Paste a post's link into Discord, Bluesky, X, Facebook, iMessage, Slack or a YouTube description and it
unfurls into a card: the headline, the summary (cut to 200 characters, so make the first sentence
count), and a picture. The picture is, first match wins:

1. **Your own image**, if you set `image:` in the front matter. Put the file in `content/images/` and
   write just its name (`image: grid-map.png`), or give a full `https://` address. Use a PNG, JPEG, GIF
   or WebP, ideally 1200x630 (wide, about 1.9 to 1), under 5 MB; keep the important part in the middle,
   since some apps crop the edges.
2. **The video's thumbnail**, if the post has a YouTube `video:`.
3. **A title card** made for you: your headline in the site's type on the paper background, with the
   section in orange above it and the What Works? wordmark at the bottom (plus the summary when the
   headline is short enough to leave room). Long headlines shrink and wrap to fit; emoji are left off
   the card (they stay in the headline everywhere else).

Tools work the same way (`image:` in the tool's file, or a title card). Every other page uses the site
card: the wordmark and the tagline. The build warns if an `image:` file is missing, isn't a picture
type previews accept, or is too big or too small; the post then falls back to the next choice.

You can also use images inside a post: put the file in `content/images/` and write
`![What the picture shows](/images/grid-map.png)`. The build copies the images posts use to the site.

**Check a preview before you share widely.** After publishing (give it a minute), paste the link into a
Discord DM to yourself, or into a preview checker such as <https://www.opengraph.xyz/>. Apps cache a link's
preview for a while, so a fix may take time to show where the link was already shared; Facebook's Sharing
Debugger (<https://developers.facebook.com/tools/debug/>) can refresh it. Locally, `preview.py` shows the
card itself at `/whatworks/static/og/<post-name>.png` (or `post-<post-name>.png` for a post named `site`
or starting with `tool-` or `post-`, so it can't take a tool's card name).

**The feed.** Readers can follow new posts in any feed reader at
<https://castor-o7.github.io/whatworks/feed.xml> (linked as "Subscribe (RSS)" in every page's footer and on
About). It holds the 20 newest published posts, in full. Charts are drawn in the browser, so in the feed
each one becomes a link back to the post ("Interactive chart: ... view it on What Works?"); give your
storm charts a `title` and that's what the link says. Drafts are never in the feed. Search engines get
a sitemap at `/whatworks/sitemap.xml` with every published page.

## Front matter reference

```yaml
---
title: The headline
date: 2026-10-08
section: science
summary: One sentence under the headline and on cards.
video:
image: grid-map.png
tags: heat, grid
tool: storm-desk
draft: true
---
```

- The block starts and ends with lines that are exactly `---`, so a `---` inside a title or summary
  is safe. (It shows as typed there; type `—` itself for an em dash. In the body, `---` becomes one.)
- `date` sorts the site, newest first. Write it as `2026-10-08`, and update it on the day you publish.
- `section` is one of the sections listed above. `video`, `image`, `tags` and `tool` are optional; leave them empty.
- `image` picks the picture shown when the post's link is shared (see Sharing below).
- `tool` links the story to one of your tools (the file name in `content/tools/`, e.g. `storm-desk`). The
  post then shows "Built with Storm Desk · try it yourself", and the tool's page lists the story.
- `draft: true` keeps the post private. Delete the line to publish.
- Quotes around a value are optional (`title: "Heat: why it kills"` works). A `#` with a space before
  and after it starts a comment, so to use one in a title, put the title in quotes.

## Tools: your software on the site

`/tools/` presents the software you build so readers can use it. Each tool is one Markdown file in
`content/tools/` (the file name becomes its address: `content/tools/storm-desk.md` → `/tools/storm-desk/`).
It gets a card on `/tools/`, its own page, a spot in the home page sidebar, and a list of the stories
that name it with `tool:`.

```yaml
---
title: Storm Desk
summary: One sentence for its card on /tools/.
status: live            # live, beta, or coming-soon
url: /storms            # where it runs: a page on this site, or a full https:// address
source: https://github.com/Castor-o7/whatworks   # optional: its source code
audience: Anyone curious how today's storms compare with the past
order: 1                # optional: lower numbers come first
image: storm-map.png    # optional: its link-preview picture (see Sharing)
---
```

The body is ordinary Markdown, with citations and storm charts like a post. A good shape: **How to use
it**, **Reading it honestly** (its limits), **How it's built**. Software that lives somewhere else
(another repo, an app store) works too: point `url` at it. `draft: true` works the same as for posts,
`preview.py` shows tool drafts, and `publish.py` checks and backs up tool files alongside posts.
