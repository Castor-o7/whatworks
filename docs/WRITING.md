# Writing for What Works?

You can write in two places and publish from either. Your writing lives in a **private** GitHub repo,
[Castor-o7/whatworks-studio](https://github.com/Castor-o7/whatworks-studio), drafts included, so it's backed
up and reachable from any computer. Every time something is saved there, GitHub builds the site without
drafts and publishes it (how that works, and why drafts can't get out: [STUDIO.md](STUDIO.md)).

- **In the browser**, nothing to install: see [Writing in the browser](#writing-in-the-browser). GitHub
  compiles your LaTeX for you, so this is the easy way to write papers.
- **On your computer**, with three commands run from the project folder:

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
   draft until you change it), then run `publish.py`. It checks the post, builds the site as a last
   look, and saves everything in `content/` (drafts too) to the studio repo. GitHub then checks again,
   builds and deploys: live a few minutes later. Try `publish.py --dry-run` first to see what will happen.
   If you also write in the browser, run `git pull --rebase --autostash` before you start on this
   computer. If you forget, `publish.py` notices that GitHub has commits you don't (from the browser),
   stops before committing, and tells you to run that command and then `publish.py` again.

**What stops a publish.** GitHub runs these checks before every deploy, and `publish.py` runs the same ones
first so you hear sooner. Nothing is deployed when:

- a post, tool or paper that isn't a draft can't be read (a bad `date:`, say);
- a published paper LaTeX can't compile;
- a post, tool or paper you're publishing or changed still has template leftovers (the placeholder
  summary, an empty `##` heading, a `[^ref]` with no source) or a storm chart it can't make sense of.
  Only this last kind can be overridden: `publish.py --force`, or, in the browser, a line `[force]` in the
  commit message (or Actions > Publish > Run workflow with "force" ticked).

Drafts never stop a publish. A post going live for the first time is listed with its date, and
`publish.py` offers to change the date to today.

**Drafts are private.** The studio repo is private, so drafts are saved there like everything else. Only
what GitHub builds without drafts reaches the public:

- The live site (the `gh-pages` branch of the public repo `Castor-o7/whatworks`) is built without drafts.
  Before it's deployed, every page, feed and script is searched for any draft's address, share card, PDF
  or title, relative links included (`../draft-name/`); if one turns up (say, a published post links to
  a draft), nothing is deployed and the run says where.
- The public repo also gets a copy of the code, without `content/`, under a generic commit message
  ("Sync code from studio <id>"), so a draft's title can't leak through a commit message either. That
  code is searched the same way, so a draft preview committed by mistake stops the deploy (and
  `_preview/`, the one in-project folder a preview may be built into, is in `.gitignore`).
- Your computer never pushes to the public repo: after setup the `public` remote can't be pushed to,
  and a git hook refuses a push to the public repo's address.
- Draft previews are a download in the private repo's Actions tab, kept 7 days.
- Anything other than a plain "no" keeps a post a draft: `draft: true`, `yes`, `True`, an empty
  `draft:`, a typo. To publish, delete the line (or write `draft: false`). If a file's front matter
  can't be read at all, it's never published; the build names the file and says why.
- A git hook in `scripts/git-hooks/` (switched on the first time you run any of the three commands)
  refuses a `.md` file that isn't saved as UTF-8 (TextEdit and some Windows editors can save UTF-16),
  since nothing can tell whether that's a draft: re-save it as UTF-8 and stage it again.

## Writing in the browser

Open **<https://github.dev/Castor-o7/whatworks-studio>** (or open the repo on github.com and press `.`).
It's VS Code running in the browser on the studio repo, signed in as you; nothing to install.

1. **Start a draft.** In the Explorer on the left, right-click `content/posts` > New File, and name it like
   the address you want: `heat-and-the-grid.md` (lowercase, dashes). Paste in the text of
   `content/POST_TEMPLATE.md` and fill in the front matter; keep `draft: true`. For a paper, make a folder
   `content/papers/<name>/` and in it a `paper.md` and a `main.tex` with the text of the files in
   `content/PAPER_TEMPLATE/` (plus `references.bib` if you cite; upload figures by dragging them onto the
   folder). Then fill in what `new_paper.py` would have: in `main.tex`, replace `TITLE` and `AUTHOR` in
   `\title{TITLE}` and `\author{AUTHOR}`; in `paper.md`, the `title:`, `date:` and `summary:`. (A
   published paper that still has any of these placeholders stops the publish, like other template
   leftovers.) The "Papers" section below has the details.
2. **Write.** `Ctrl+Shift+V` (`⇧⌘V` on a Mac) previews Markdown beside the text (plain styling; charts
   appear only on the site). LaTeX gets syntax colors, but nothing compiles in the browser: GitHub compiles
   it when you commit, and the draft preview has the PDF.
3. **Save to GitHub.** Open Source Control (the branch icon in the left bar, or `Ctrl+Shift+G`), type a
   short message, and click **Commit & Push**. That commits to `main`, which is what publishes. Until you
   commit, edits are kept only in this browser, so commit when you stop for the day (drafts are fine
   to commit).
4. **Watch it build.** Each commit starts a "Publish" run at
   <https://github.com/Castor-o7/whatworks-studio/actions>, a few minutes long (the first run takes longer
   while it installs TeX Live). A green check means the site is up to date; anything published that
   changed is live a minute or two later. A red X means something stopped it: click the run, and its
   summary page says what (the file, the line, the LaTeX error). Fix it and commit again. A newer commit
   cancels a run that's still going, so commit as often as you like.
5. **Read your drafts.** The run's summary page lists the drafts and, for each draft paper, its page
   count or its LaTeX error. At the bottom, under Artifacts, **draft-preview** is a zip (kept 7 days) with:
   - `pdfs/`: every paper that compiled, drafts included; open them directly;
   - `problems.txt`: every warning, drafts included;
   - `site/`: the whole site with drafts. To browse it on a computer that has this project, run
     `.venv/bin/python scripts/serve.py --dir ~/Downloads/draft-preview/site` and open
     <http://localhost:8000/whatworks/>. The preview has no storm data of its own (it's too big): the
     Storm Desk and storm charts use that computer's `_site/data/` if it has one (after
     `scripts/build_data.py` or `scripts/ci_publish.py fetch-data`), and are empty otherwise.
6. **Publish.** Delete `draft: true` in the front matter (a paper's is in its `paper.md`), set `date:` to
   today, and commit. That's all.

GitHub's free plan gives a private repo 2,000 minutes of Actions a month; a run takes a few, so that's
hundreds of commits.

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
or starting with `tool-`, `paper-` or `post-`, so it can't take a tool's or paper's card name).

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
`preview.py` shows tool drafts, and `publish.py` checks tool files alongside posts.

## Papers: LaTeX, published as PDFs

`/papers/` holds longer, formal work written in LaTeX. Each paper is a folder in `content/papers/`; the
folder name becomes its address (`content/papers/heat-and-the-grid/` → `/papers/heat-and-the-grid/`, with the
PDF at `/papers/heat-and-the-grid/heat-and-the-grid.pdf`).

```sh
scripts/new_paper.py "Heat and the grid"                     # 1. start a draft (pdflatex)
scripts/new_paper.py "Heat and the grid" --engine xelatex    #    or pick the engine (xelatex, lualatex)
scripts/preview.py                                           # 2. compiles it and shows its page
scripts/publish.py                                           # 3. delete "draft: true" in paper.md first
```

`new_paper.py` makes the folder from `content/PAPER_TEMPLATE/` and test-compiles it:

```
content/papers/heat-and-the-grid/
  paper.md         the front matter (below) and an optional Markdown note shown above the PDF
  main.tex         the paper: article class, amsmath/amssymb, graphicx, hyperref, a bibliography
  references.bib   its sources; \cite{key} in main.tex, and the References list builds itself (biber)
```

Put figures and any other files the paper needs in the same folder (subfolders are fine). Already have a
`.tex` file? Make the folder yourself: copy your `.tex`, `.bib` and figures in, and add a `paper.md`
(copy the template's) with `main:` set to your file's name.

```yaml
---
title: Heat and the grid
date: 2026-10-10
summary: One paragraph: the abstract. Shown on the paper's page, on /papers/, in the feed and in link previews.
tags: heat, grid
section: science      # optional: also list it on that section's page
tool: storm-desk      # optional: "Built with" a tool in content/tools/
main: main.tex        # optional: the file to compile (default main.tex)
engine: pdflatex      # optional: pdflatex (default), xelatex or lualatex
draft: true
---
Optional Markdown shown on the paper's page above the PDF (citations and links work as in posts).
```

**What readers get.** The paper's page has the title, date, the abstract, your Markdown note, a **Download
PDF** button with its page count and size, the PDF itself in the page (phones get a "Read the PDF" button
instead, since most phone browsers can't show a PDF inside a page), and a **Cite this paper** box with a
ready-made citation and BibTeX (author from `site.toml`) with a Copy button. Papers are listed newest first
on `/papers/` ("Papers" in the menu), appear in the feed and sitemap, and get a share card with "Paper" above
the title.

**Compiling.** The build runs `latexmk` with the paper's engine, so bibliographies (biber or bibtex),
cross-references and tables of contents just work. It compiles a fresh copy of the folder, so `.aux` and
`.log` files lying around in it don't matter (and git ignores them). An unchanged paper isn't compiled
again (results are kept in `.cache/papers/`), so builds stay fast. `\today` prints the paper's `date:`,
so the date on the PDF matches the site. To see errors without building the site:

```sh
scripts/build_papers.py              # published papers
scripts/build_papers.py my-paper     # one paper, draft or not
scripts/build_papers.py --drafts     # everything
```

**When LaTeX fails.** You get the file, the line, TeX's message and the line it stopped at, for example:

```
main.tex, line 42: Undefined control sequence.
  at: The sum is $\fracc <-- here {1}{2}$
```

A draft that fails just gets a warning, and its preview page shows the error in place of the PDF (in the
browser: the run's summary page and the draft preview's `problems.txt`). A published paper that fails stops
the publish (on GitHub and in `publish.py`), whatever else changed, and nothing is deployed until it compiles.
The publish also stops on a published paper that still has the template's placeholder text, summary,
title (`Untitled paper`) or date, or `\title{TITLE}` / `\author{AUTHOR}` in `main.tex`, cites a source the
`.bib` doesn't have, or has an empty summary.

Messages are made readable where TeX's aren't: a character pdflatex can't print (`≥`, `Ω`) names the line it's
on and suggests `engine: xelatex` (`new_paper.py` picks xelatex by itself for a title with such characters);
a missing `\end{document}` or an unclosed `{` says so, with the start of the unclosed text; a `.bib` mistake
names the `.bib` file and line. A missing package (`File 'x.sty' not found`) is never cached: install it
and build again. Other failures are reused only while the TeX installation is unchanged. It warns when a PDF is over 20 MB: shrink
the figures (PDF for drawings, compressed JPEG for photos).

**Limits.** LaTeX runs without shell escape, so packages that run programs (`minted`, `\write18`,
`epstopdf` on the fly, `gnuplottex`) don't work: use `listings` instead of `minted`, and convert figures to
PDF or PNG yourself. A paper gets 5 minutes to compile. `latexmkrc` files in a paper's folder are ignored.

**Drafts are private.** As with posts, a paper is never compiled into the live site while its `paper.md`
says `draft: true` (or can't be read). Its folder is saved in the private studio repo like everything else,
and its PDF appears only in the draft preview. Delete the line and set `date:` to today to publish.
