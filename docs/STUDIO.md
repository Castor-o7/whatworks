# Studio: write in the browser, publish LaTeX papers — contract

Josh writes in the browser (github.dev — VS Code in the browser) and publishes by saving. He also publishes full LaTeX
papers as PDFs. Drafts must stay private, so the source moves to a **private** repo.

## Repositories and branches

| Where | What | Written by |
|---|---|---|
| `Castor-o7/whatworks-studio` (private) `main` | Everything: code + `content/` (drafts included). Source of truth. | Josh (github.dev or local git) |
| `Castor-o7/whatworks` (public) `gh-pages` | The built site (served at https://castor-o7.github.io/whatworks/). | CI only |
| `Castor-o7/whatworks` (public) `site-data` | Orphan branch holding the storm data tree (`_site/data`, ~207 MB gzipped). | `scripts/publish_data.sh` (local, after `build_data.py`) |
| `Castor-o7/whatworks` (public) `main` | Open-source mirror of the **code** only: everything except `content/` (and anything gitignored). Commit message is generic (`Sync code from studio <short-sha>`), never copied from studio commits, so no draft title can leak. | CI only |

CI pushes to the public repo with an SSH **deploy key** (write access on `whatworks` only), stored in the studio repo as
the secret `PUBLIC_DEPLOY_KEY`. Setting up the repos, key and secret is done once by `scripts/setup_studio.sh` (run by a
human; the build must not run it).

## CI (`.github/workflows/publish.yml` in the studio repo; logic in testable scripts)

On push to `main` (and manual `workflow_dispatch`), with `concurrency: publish` (newer runs cancel older ones):

1. Check out the studio repo; set up Python from `requirements.txt`; install LaTeX (same engine family as local: TeX Live
   via `latexmk`; cache it so runs stay fast).
2. Fetch the public `site-data` branch into `_site/data/`.
3. `scripts/ci_publish.py` (runnable locally against fake remotes for testing):
   a. Run the same checks `publish.py` runs. A **published** post, tool or paper with a blocking warning (template
      leftovers, unreadable front matter, LaTeX that fails to compile) fails the run with a clear message and **nothing
      is deployed**. Drafts never block.
   b. Build papers (published only) and the site **without drafts**; verify no draft slug appears in `_site`
      (belt and braces).
   c. Push `_site` (pages + data) to public `gh-pages`.
   d. Push the code mirror to public `main` (exclude `content/`; generic message).
4. Build a **draft preview**: the site with `--drafts` (+ draft paper PDFs) uploaded as a workflow artifact
   (`draft-preview`, retention 7 days) — private to the studio repo, never pushed anywhere public.

## Local workflow (changes)

- `scripts/publish.py`: runs checks + a local build as a sanity check, then commits **all** of `content/` (drafts are fine
  now — the repo is private) and pushes to studio `main`. CI deploys. Remove local deploying of pages (two writers to
  `gh-pages` would race). Keep `--dry-run`.
- `scripts/deploy.sh` is replaced by `scripts/publish_data.sh` (data only → public `site-data`, then asks CI to redeploy).
- Pre-commit hook: drafts are now allowed (private repo); keep the UTF-8 check.
- The local `origin` becomes the studio repo.

## Papers

```
content/papers/<slug>/
  paper.md        front matter: title, date, summary (one-paragraph abstract), tags, section (optional), tool (optional),
                  draft, main (default main.tex), engine (pdflatex | xelatex | lualatex; default pdflatex)
                  body: optional Markdown shown on the landing page above the PDF
  main.tex        the paper (plus .bib, figures, etc. in the same folder)
```

- `scripts/new_paper.py "Title"` scaffolds a draft with a clean `main.tex` template (article class, amsmath/amssymb, graphicx,
  hyperref, a working bibliography via `references.bib`) that compiles out of the box.
- `scripts/build_papers.py` compiles with `latexmk` (engine per paper) into a cache keyed by a hash of the paper folder +
  engine (unchanged papers aren't recompiled), reports failures with the relevant `.log` lines, and is used by
  `build_site.py` (`--drafts` compiles drafts too).
- Pages: `/papers/` (list, newest first) and `/papers/<slug>/` (title, date, abstract, Markdown body, **Download PDF**
  with page count and size, an embedded viewer with a link fallback, and a **Cite** box with generated BibTeX:
  author from `site.toml`, title, year, url). PDF at `/papers/<slug>/<slug>.pdf`. "Papers" in the nav; papers appear in
  the feed (summary + link), sitemap, share cards (kicker "Paper"), and `check()` validation.
- Safety: drafts never compiled into the published site; warn on PDFs > 20 MB; LaTeX runs without `-shell-escape`.

## Docs

`docs/WRITING.md` gains "Writing in the browser" (open https://github.dev/Castor-o7/whatworks-studio or press `.` on the repo
page; edit; Source Control → commit to `main`; the site updates in a few minutes; watch the Actions tab; download the
`draft-preview` artifact to see drafts) and "Papers". README and STATIC_SITE.md are updated.
