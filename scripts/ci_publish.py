#!/usr/bin/env python3
"""Publish the site from the private studio repo to the public one (docs/STUDIO.md). GitHub Actions runs
this (.github/workflows/publish.yml) on every push to the studio's main branch; it runs the same way on
your computer against any git remotes, which is how it's tested.

    scripts/ci_publish.py fetch-data            # public site-data branch -> _site/data/
    scripts/ci_publish.py build [--preview DIR] # checks, then the site WITHOUT drafts, then a leak check;
                                                # --preview also builds the draft preview into DIR
    scripts/ci_publish.py deploy                # _site/ -> public gh-pages; code (no content/) -> public main

`build` and `deploy` are separate steps so that LaTeX (which can read any file the runner can) has
finished before the deploy key exists on the machine: the workflow writes the key only for `deploy`,
which runs no LaTeX.

build: stops (exit 1, and then nothing is deployed) on a post, tool or paper meant to be live that
  can't be read, a published paper LaTeX can't compile, or a warning about a published item changed
  since the last deploy (template leftovers and such; see scripts/checks.py). --force, or a line
  "[force]" in the studio commit's message, gets past those warnings, never past the first two. Drafts
  never stop it. After building it checks that no draft's address, share card, PDF or title appears
  anywhere in _site/ (outside data/, relative links resolved) or in the code outside content/ (the
  public main's copy), and records the studio commit it built in .cache/ci/built.json.
deploy: refuses unless `build` succeeded for the commit that's checked out. Commits _site/ (pages and
  data) to gh-pages with the message "Deploy from studio <sha>" (the next build reads it to know what
  changed), then the code without content/ to main as "Sync code from studio <short-sha>". The messages
  never come from studio commits, so no draft title can leak through them.

Remotes: --public (read; default https://github.com/<repos.public>.git from site.toml) and --push-url
(write; default git@github.com:<repos.public>.git, used with the deploy key). Pass local paths or
file:// URLs to try it against bare repos.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
# Run with the project's virtualenv when there is one (on GitHub there isn't; pip installs globally).
VENV = ROOT / ".venv"
if (VENV / "bin" / "python").exists() and Path(sys.prefix).resolve() != VENV.resolve():
    os.execv(VENV / "bin" / "python", [str(VENV / "bin" / "python"), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import content, papers as paperkit, tools as toolkit  # noqa: E402
import build_site  # noqa: E402
import checks  # noqa: E402

SITE = build_site.OUT  # _site/
WORK = ROOT / ".cache" / "ci"
GIT_DIR = WORK / "public.git"  # a bare repo holding what we fetched from (and push to) the public repo
STAMP = WORK / "built.json"
PUBLIC = build_site.SITE.get("repos", {}).get("public", "Castor-o7/whatworks")
DEPLOY_MSG = "Deploy from studio "
SYNC_MSG = "Sync code from studio "
BOT = {"GIT_AUTHOR_NAME": "github-actions[bot]",
       "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
BOT.update(GIT_COMMITTER_NAME=BOT["GIT_AUTHOR_NAME"], GIT_COMMITTER_EMAIL=BOT["GIT_AUTHOR_EMAIL"])
# Never published, even if they show up in _site/: build_data.py's scratch, Finder litter, the preview marker.
EXCLUDE = ["/data.tmp/", "/data.old/", "/data.fetch/", ".DS_Store", "/" + build_site.DRAFTS_MARKER]
TEXT = {".html", ".xml", ".js", ".mjs", ".css", ".txt", ".json", ".svg", ".md", ".webmanifest", ".map"}
SHA = re.compile(r"\b[0-9a-f]{40}\b")
LINK = re.compile(r"""\b(?:href|src|action|poster)\s*=\s*["']([^"'<>]*)["']""", re.I)


class Stop(Exception):
    """A clear, expected reason to stop (printed without a traceback)."""


def run(cmd, *, cwd=None, env=None, input=None, check=True, quiet_err=False):
    full_env = None if env is None else {**os.environ, **env}
    p = subprocess.run(cmd, cwd=cwd, env=full_env, input=input, capture_output=True)
    if check and p.returncode:
        err = p.stderr.decode(errors="replace").strip()
        raise Stop(f"{' '.join(map(str, cmd[:4]))}... failed:\n{err}")
    if p.returncode and not quiet_err and p.stderr:
        print(p.stderr.decode(errors="replace").strip(), file=sys.stderr)
    return p


def wgit(*args, env=None, **kw):
    """git on the work repo (.cache/ci/public.git); global excludes are ignored so the result is the same
    on every machine."""
    return run(["git", "--git-dir", str(GIT_DIR), "-c", "core.excludesFile=", "-c", "core.autocrlf=false",
                *args], env=env, **kw)


def sgit(*args, **kw):
    """git on the studio checkout."""
    return run(["git", "-C", str(ROOT), *args], **kw)


def out(p):
    return p.stdout.decode().strip()


def init_work():
    if not (GIT_DIR / "HEAD").exists():
        GIT_DIR.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "--quiet", "--bare", str(GIT_DIR)])
    (GIT_DIR / "info").mkdir(exist_ok=True)
    (GIT_DIR / "info" / "exclude").write_text("\n".join(EXCLUDE) + "\n")


def rev(ref):
    p = wgit("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False)
    return out(p) if p.returncode == 0 else None


def fetch_tip(url, branch, required=False):
    """Fetch just the tip of `branch` from `url` into refs/public/<branch>. -> its sha, or None when the
    branch doesn't exist there (then the local ref is dropped too, so it can't go stale)."""
    local = f"refs/public/{branch}"
    listed = out(run(["git", "ls-remote", "--heads", url, f"refs/heads/{branch}"]))
    if not listed:
        if required:
            raise Stop(f"the public repo ({url}) has no '{branch}' branch.")
        wgit("update-ref", "-d", local, check=False)
        return None
    wgit("fetch", "--quiet", "--no-tags", "--depth", "1", url, f"+refs/heads/{branch}:{local}")
    return rev(local)


# ---------------------------------------------------------------------------------------------- fetch-data

def cmd_fetch_data(args):
    """The public site-data branch (the storm data tree) -> _site/data/. Also fetches the tips of gh-pages
    and main, so `build` knows the last deployed commit and `deploy` uploads only what changed."""
    init_work()
    print(f"Fetching site-data from {args.public} ...", flush=True)
    fetch_tip(args.public, "site-data", required=True)
    for branch in ("gh-pages", "main"):
        fetch_tip(args.public, branch)
    dest = SITE / "data"
    if dest.exists() and not args.replace:
        raise Stop(f"{dest.relative_to(ROOT)} already exists; pass --replace to swap it for the site-data branch.")
    tmp = SITE / "data.fetch"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    archive = subprocess.Popen(["git", "--git-dir", str(GIT_DIR), "archive", "--format=tar", "refs/public/site-data"],
                               stdout=subprocess.PIPE)
    untar = subprocess.run(["tar", "-x", "-f", "-", "-C", str(tmp)], stdin=archive.stdout)
    archive.stdout.close()
    if archive.wait() or untar.returncode:
        shutil.rmtree(tmp, ignore_errors=True)
        raise Stop("couldn't unpack the site-data branch.")
    if not (tmp / "meta.json.gz").is_file():
        shutil.rmtree(tmp, ignore_errors=True)
        raise Stop("the site-data branch has no meta.json.gz at its top; publish it with scripts/publish_data.sh.")
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    files = sum(1 for p in dest.rglob("*") if p.is_file())
    print(f"_site/data/: {files} files from site-data {rev('refs/public/site-data')[:12]}")
    return 0


# ---------------------------------------------------------------------------------------------- build

def last_deployed():
    """The studio commit the public gh-pages was last built from (its commit message names it), or None."""
    if not (GIT_DIR / "HEAD").exists() or not rev("refs/public/gh-pages"):
        return None
    msg = out(wgit("log", "-1", "--format=%B", "refs/public/gh-pages"))
    if not msg.startswith(DEPLOY_MSG):
        return None
    m = SHA.search(msg)
    return m.group(0) if m else None


def changed_since(base):
    """Paths under content/ that differ between `base` and HEAD (both sides of a rename), or None when
    `base` is unknown (then everything published is checked as if new)."""
    if not base or sgit("cat-file", "-e", base + "^{commit}", check=False).returncode:
        return None
    names = out(sgit("diff", "--name-only", "-z", "--no-renames", base, "HEAD", "--", "content"))
    return {n for n in names.split("\0") if n}


def draft_items():
    """Everything under content/ that isn't live: [(kind, slug, title or None)]. "Not live" is decided
    from the files on disk minus what's published, so an unreadable draft is covered too."""
    items = []
    published = {p.slug for p in content.all_posts()}
    posts = {p.slug: p for p in content.load_posts()[0]}
    for f in sorted(content.POSTS.glob("*.md")):
        if not f.name.startswith(".") and f.stem not in published:
            items.append(("post", f.stem, getattr(posts.get(f.stem), "title", None)))
    found = toolkit.load_tools()[0]
    published = {t.slug for t in found if not t.draft}
    tools = {t.slug: t for t in found}
    for f in sorted(toolkit.TOOLS.glob("*.md")) if toolkit.TOOLS.is_dir() else []:
        if not f.name.startswith(".") and f.stem not in published:
            items.append(("tool", f.stem, getattr(tools.get(f.stem), "title", None)))
    found = paperkit.load_papers()[0]
    published = {p.slug for p in found if not p.draft}
    papers = {p.slug: p for p in found}
    for folder in paperkit.folders():
        if folder.name not in published:
            items.append(("paper", folder.name, getattr(papers.get(folder.name), "title", None)))
    return items


def leak_patterns(items, live_titles):
    """-> (paths, texts): exact paths under _site/ and regexes over its text files that would mean a
    draft got out."""
    paths, texts = {}, []
    for kind, slug, title in items:
        s = re.escape(slug)
        end = r"(?=[/\"'<>\s#?)]|$)"
        if kind == "post":
            paths[f"post/{slug}"] = (kind, slug)
            card = build_site.post_card(slug)
            texts.append((re.compile(rf"/post/{s}{end}"), kind, slug))
        elif kind == "tool":
            paths[f"tools/{slug}"] = (kind, slug)
            card = f"tool-{slug}.png"
            texts.append((re.compile(rf"/tools/{s}{end}"), kind, slug))
        else:
            paths[f"papers/{slug}"] = (kind, slug)
            card = f"paper-{slug}.png"
            texts.append((re.compile(rf"/papers/{s}{end}"), kind, slug))
            texts.append((re.compile(rf"(?<![\w.-]){s}\.pdf\b"), kind, slug))
        paths[f"static/og/{card}"] = (kind, slug)
        texts.append((re.compile(rf"/og/{re.escape(card)}\b"), kind, slug))
        title = (title or "").strip()
        # A short title ("Notes") could be ordinary words on a live page; the address checks cover those.
        if len(title) >= 12 and title not in live_titles:
            forms = {title, html.escape(title), html.escape(title, quote=False), json.dumps(title)[1:-1]}
            texts.append((re.compile("|".join(re.escape(f) for f in sorted(forms))), kind, slug))
    return paths, texts


def find_leaks(site=SITE):
    """Every sign of a draft in `site` (outside data/, which is storm data, not built from content/)."""
    items = draft_items()
    live_titles = ({p.title for p in content.all_posts()} | {t.title for t in build_site.visible_tools()[0]}
                   | {p.title for p in build_site.visible_papers()[0]})
    paths, texts = leak_patterns(items, live_titles)
    leaks = []
    if (site / build_site.DRAFTS_MARKER).exists():
        leaks.append(f"{build_site.DRAFTS_MARKER}: this is a --drafts build")
    for f in sorted(site.rglob("*")):
        rel = f.relative_to(site)
        if rel.parts[0] in ("data", ".git", "data.tmp", "data.old", "data.fetch") or not f.is_file():
            continue
        key = rel.as_posix()
        for prefix, (kind, slug) in paths.items():
            if key == prefix or key.startswith(prefix + "/"):
                leaks.append(f"{key}: the {kind} draft '{slug}' has a page or file here")
        if f.suffix.lower() in TEXT:
            text = f.read_text(encoding="utf-8", errors="replace")
            # A relative link (href="../draft-slug/") names a draft's address only once it's resolved
            # against this page's own URL, so search the resolved URLs too.
            page = f"{build_site.ABS}/{key}"
            text += "\n" + "\n".join(urljoin(page, html.unescape(m.group(1).strip())) for m in LINK.finditer(text))
            for rx, kind, slug in texts:
                if m := rx.search(text):
                    leaks.append(f"{key}: mentions the {kind} draft '{slug}' ({m.group(0)!r})")
    return leaks


def code_leaks(commit):
    """Every sign of a draft in the code mirror (the studio commit's files outside content/), which
    deploy pushes to the public main: a path or a file's text that matches the same patterns as
    find_leaks (e.g. a draft preview committed by mistake)."""
    items = draft_items()
    live_titles = ({p.title for p in content.all_posts()} | {t.title for t in build_site.visible_tools()[0]}
                   | {p.title for p in build_site.visible_papers()[0]})
    paths, texts = leak_patterns(items, live_titles)
    entries = []
    for e in sgit("ls-tree", "-r", "-z", "--long", commit).stdout.split(b"\0"):
        if not e:
            continue
        info, name = e.split(b"\t", 1)
        mode, kind, sha, size = info.split()
        name = name.decode("utf-8", "replace")
        if name.split("/", 1)[0] != "content" and kind == b"blob":
            entries.append((name, sha.decode(), int(size) if size.isdigit() else 0))
    leaks = []
    for name, _, _ in entries:
        hit = next((f"{name}: the {kind} draft '{slug}' has a page or file here"
                    for prefix, (kind, slug) in paths.items()
                    if f"/{prefix}/" in f"/{name}" or f"/{name}".endswith(f"/{prefix}")), None)
        hit = hit or next((f"{name}: its path names the {kind} draft '{slug}' ({m.group(0)!r})"
                           for rx, kind, slug in texts if (m := rx.search("/" + name))), None)
        if hit:
            leaks.append(hit)
    small = [(n, sha) for n, sha, size in entries if size <= 5 * 1024 * 1024]
    if small:
        batch = sgit("cat-file", "--batch", input="".join(f"{sha}\n" for _, sha in small).encode()).stdout
        pos = 0
        for name, _ in small:
            header_end = batch.index(b"\n", pos)
            size = int(batch[pos:header_end].split()[2])
            text = batch[header_end + 1:header_end + 1 + size].decode("utf-8", "replace")
            pos = header_end + 1 + size + 1
            for rx, kind, slug in texts:
                if m := rx.search(text):
                    leaks.append(f"{name}: mentions the {kind} draft '{slug}' ({m.group(0)!r})")
    leaks = list(dict.fromkeys(leaks))
    return leaks if len(leaks) <= 25 else leaks[:25] + [f"... and {len(leaks) - 25} more"]


def head():
    return out(sgit("rev-parse", "HEAD"))


def report_checks(r, force):
    for e in r.draft_errors:
        print(f"warning: {e} (draft skipped)")
    if r.older:
        print("\nNotes on things already live (fix when you can):\n  " + "\n  ".join(r.older))
    if r.hard():
        print("\nThese stop the publish (fix them; nothing gets past these):\n  " + "\n  ".join(r.hard()))
    if r.blocking:
        verdict = "publishing anyway (forced)" if force else "these stop the publish"
        print(f"\nCheck these ({verdict}):\n  " + "\n  ".join(r.blocking))
        if not force:
            print("  Fix them and commit again, or put a line [force] in the commit message to publish anyway.")


def build_preview(dest):
    """The site WITH drafts, for the private draft-preview artifact: dest/site/ (pages; no storm data),
    dest/pdfs/<slug>.pdf (every paper that compiled, drafts included), dest/problems.txt, README.txt.
    -> (drafts, papers) for the run summary."""
    dest = Path(dest).resolve()
    # Inside the project only in folders .gitignore keeps out of git: a committed preview would be copied
    # to the public main with the code (code_leaks would then stop the deploy).
    if dest == ROOT or ROOT in dest.parents and dest.parts[len(ROOT.parts)] not in (".cache", "_preview"):
        raise Stop(f"--preview {dest}: use a folder outside the project (or under .cache/ or _preview/)")
    shutil.rmtree(dest, ignore_errors=True)
    site = dest / "site"
    site.mkdir(parents=True)
    link = site / "data"
    if (SITE / "data").is_dir():  # only for the Storm Desk totals; never copied into the preview
        link.symlink_to((SITE / "data").resolve())
    saved = build_site.OUT
    build_site.OUT = site
    try:
        build_site.build(drafts=True, report=False)
    finally:
        build_site.OUT = saved
        if link.is_symlink():
            link.unlink()
    papers = build_site.visible_papers(drafts=True)[0]
    build_site.compile_papers(papers, quiet=True)  # cached by the build above: instant
    (dest / "pdfs").mkdir()
    for p in papers:
        if p.pdf.ok:
            shutil.copyfile(p.pdf.pdf, dest / "pdfs" / p.pdf_name)
    posts, errors = content.load_posts()
    tools, tool_errors = build_site.visible_tools(drafts=True)
    lines = build_site.problems([p for p in posts], errors + tool_errors + paperkit.load_papers()[1],
                                build_site.load_meta(), tools, papers)
    (dest / "problems.txt").write_text(("\n".join(lines) or "No problems found.") + "\n", encoding="utf-8")
    drafts = draft_items()
    (dest / "README.txt").write_text(
        "Draft preview of What Works? (private: built from the studio repo, never published)\n\n"
        "pdfs/      every paper that compiled, drafts included: open them directly.\n"
        "problems.txt  every warning, drafts included (LaTeX errors with the line they stopped at).\n"
        "site/      the whole site with drafts. To browse it, from the project folder run:\n"
        "             .venv/bin/python scripts/serve.py --dir <this folder>/site\n"
        "           and open http://localhost:8000/whatworks/. It has no storm data of its own: the Storm Desk\n"
        "           and storm charts use that project's _site/data/ if it has one, and are empty otherwise.\n\n"
        "Drafts in this preview:\n" + "".join(f"  {k}: {s}  {t or ''}\n" for k, s, t in drafts),
        encoding="utf-8")
    return drafts, papers


def summary(lines):
    """Append Markdown to the GitHub Actions run page (no-op elsewhere)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def fenced(text):
    return "```\n" + text.replace("```", "'''") + "\n```"


def cmd_build(args):
    STAMP.unlink(missing_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    sha = head()
    dirty = out(sgit("status", "--porcelain", "--untracked-files=all"))
    if dirty and not args.allow_dirty:
        raise Stop("the checkout has uncommitted changes, so the site wouldn't match the commit:\n"
                   + dirty + "\n(Commit them, or pass --allow-dirty to try anyway.)")
    message = out(sgit("log", "-1", "--format=%B", "HEAD"))
    force = args.force or any(line.strip().lower() == "[force]" for line in message.splitlines())
    base = last_deployed()
    changed = changed_since(base)
    print(f"Studio commit {sha[:12]}; " + (f"last deploy was built from {base[:12]}, {len(changed)} content "
                                           "file(s) changed since" if changed is not None else
                                           "no earlier deploy found, so everything published is checked as new"))
    if not (SITE / "data" / "meta.json.gz").is_file():
        print("warning: _site/data/ is missing (run 'scripts/ci_publish.py fetch-data' first); the Storm Desk "
              "would have no totals, and deploy will refuse.", file=sys.stderr)
    r = checks.run(changed, quiet=False)
    report_checks(r, force)
    ok = r.ok(force)
    leaks = []
    if ok:
        posts = build_site.build(drafts=False, report=False)
        leaks = find_leaks()
        code = code_leaks(sha)
        if leaks:
            ok = False
            print("\nA draft showed up in the published build, so nothing will be deployed:\n  "
                  + "\n  ".join(leaks), file=sys.stderr)
        if code:
            ok = False
            print("\nA draft showed up in the code outside content/ (it would be copied to the public main), so "
                  "nothing will be deployed:\n  " + "\n  ".join(code)
                  + "\n  Remove it from the repo (git rm -r --cached <path>) and commit again.", file=sys.stderr)
            leaks += code
        if not leaks:
            print(f"Leak check: no draft in _site/ or in the code ({len(draft_items())} draft(s) checked).")
            STAMP.write_text(json.dumps({"sha": sha, "built": datetime.now(timezone.utc).isoformat(),
                                         "posts": len(posts), "papers": len(r.papers)}))
    lines = [f"## {'Ready to deploy' if ok else 'Not deployed'}: studio `{sha[:12]}`", ""]
    if r.hard():
        lines += ["**Stopped by** (nothing gets past these):", "", fenced("\n".join(r.hard())), ""]
    if r.blocking:
        lines += [f"**{'Published anyway ([force])' if force else 'Stopped by'}** (changed since the last deploy):",
                  "", fenced("\n".join(r.blocking)), ""]
        if not force:
            lines += ["Fix them and commit again, or add a line `[force]` to the commit message to publish anyway.", ""]
    if leaks:
        lines += ["**A draft showed up in the published build:**", "", fenced("\n".join(leaks)), ""]
    if r.older:
        lines += ["Notes on things already live:", "", fenced("\n".join(r.older)), ""]

    if args.preview:
        print(f"\nBuilding the draft preview into {args.preview} ...", flush=True)
        try:
            drafts, papers = build_preview(args.preview)
        except Exception as e:  # the preview is a convenience: it never decides whether the site deploys
            print(f"warning: the draft preview couldn't be built: {e}", file=sys.stderr)
            drafts, papers = [], []
            lines += [f"The draft preview couldn't be built: {e}"]
        by_slug = {p.slug: p for p in papers}
        lines += ["### Drafts (download the `draft-preview` artifact below to read them)", ""]
        if not drafts:
            lines.append("No drafts.")
        for kind, slug, title in drafts:
            p = by_slug.get(slug) if kind == "paper" else None
            state = ""
            if p is not None and p.pdf is not None:
                state = (f": compiled, {p.pdf.pages_label}, {p.pdf.size_label}" if p.pdf.ok
                         else ": **LaTeX failed**")
            lines.append(f"- {kind} `{slug}` {html.escape(title or '(unreadable)')}{state}")
            if p is not None and p.pdf is not None and not p.pdf.ok:
                lines += ["", fenced(p.pdf.error), ""]
        lines.append("")
    summary(lines)
    print("\nBuild OK: ready to deploy." if ok else "\nNot deployable: see above.")
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------- deploy

def site_tree():
    """Stage _site/ (pages + data) into a scratch index of the work repo -> tree sha."""
    index = WORK / "pages.index"
    index.unlink(missing_ok=True)
    env = {"GIT_INDEX_FILE": str(index), "GIT_WORK_TREE": str(SITE)}
    wgit("add", "--all", "--", ".", env=env)
    tree = out(wgit("write-tree", env=env))
    index.unlink(missing_ok=True)
    return tree


def code_tree(studio_ref):
    """The studio commit's tree minus content/ (the code mirror) -> tree sha."""
    listing = wgit("ls-tree", "-z", studio_ref).stdout.split(b"\0")
    kept = [e for e in listing if e and e.split(b"\t", 1)[1] != b"content"]
    return out(wgit("mktree", "-z", input=b"\0".join(kept) + b"\0"))


def tree_of(commit):
    return out(wgit("rev-parse", commit + "^{tree}")) if commit else None


def commit_and_push(url, branch, tree, parent, message):
    """Commit `tree` on top of `parent` and push it to `branch`, only if it changed. The lease makes the
    push fail rather than overwrite something that landed there since we fetched."""
    if parent and tree_of(parent) == tree:
        print(f"{branch}: unchanged, nothing to push.")
        return None
    when = f"{int(time.time())} +0000"
    env = {**BOT, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    commit = out(wgit("commit-tree", tree, *(["-p", parent] if parent else []), "-m", message, env=env))
    wgit("push", "--quiet", f"--force-with-lease=refs/heads/{branch}:{parent or ''}", url,
         f"{commit}:refs/heads/{branch}")
    print(f"{branch}: pushed {commit[:12]} ({message}).")
    return commit


def cmd_deploy(args):
    sha = head()
    try:
        stamp = json.loads(STAMP.read_text())
    except (OSError, ValueError):
        raise Stop("no successful build to deploy: run 'scripts/ci_publish.py build' first.") from None
    if stamp.get("sha") != sha:
        raise Stop(f"the last build was of {stamp.get('sha', '?')[:12]}, but {sha[:12]} is checked out; build again.")
    for need, why in ((SITE / "index.html", "no pages"), (SITE / ".nojekyll", "no .nojekyll"),
                      (SITE / "data" / "meta.json.gz", "no storm data (run fetch-data)")):
        if not need.is_file():
            raise Stop(f"_site/ has {why}; nothing deployed.")
    for d in ("data.tmp", "data.old", "data.fetch"):
        if (SITE / d).exists():
            raise Stop(f"_site/{d} exists (an unfinished data build or fetch); nothing deployed.")
    leaks = find_leaks()  # again, in case anything touched _site/ since the build
    if leaks:
        raise Stop("a draft is in _site/, nothing deployed:\n  " + "\n  ".join(leaks))
    leaks = code_leaks(sha)
    if leaks:
        raise Stop("a draft is in the code outside content/, nothing deployed:\n  " + "\n  ".join(leaks))
    init_work()
    url = args.push_url
    print(f"Deploying studio {sha[:12]} to {url} ...", flush=True)
    pages_parent = fetch_tip(url, "gh-pages")
    main_parent = fetch_tip(url, "main")
    if not rev("refs/public/site-data"):
        print("note: site-data wasn't fetched, so the storm data may be uploaded in full.", file=sys.stderr)
    pages = commit_and_push(url, "gh-pages", site_tree(), pages_parent, DEPLOY_MSG + sha)
    wgit("fetch", "--quiet", "--no-tags", str(ROOT), "+HEAD:refs/studio/head")
    if rev("refs/studio/head") != sha:
        raise Stop("the studio checkout moved while deploying; run again.")
    code = commit_and_push(url, "main", code_tree("refs/studio/head"), main_parent, SYNC_MSG + sha[:12])
    wgit("update-ref", "-d", "refs/studio/head", check=False)
    summary([f"Deployed studio `{sha[:12]}`: the site (gh-pages) " + ("updated" if pages else "was already current")
             + "; the code mirror (main) " + ("updated." if code else "was already current.")])
    print("Done. GitHub Pages serves the new build in a minute or two.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Publish from the studio repo to the public site (docs/STUDIO.md).")
    ap.add_argument("--public", default=os.environ.get("WW_PUBLIC_URL") or f"https://github.com/{PUBLIC}.git",
                    help="URL to read the public repo from (default: %(default)s)")
    ap.add_argument("--push-url", default=os.environ.get("WW_PUBLIC_PUSH_URL") or f"git@github.com:{PUBLIC}.git",
                    help="URL to push to (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch-data", help="public site-data branch -> _site/data/")
    f.add_argument("--replace", action="store_true", help="replace an existing _site/data/")
    b = sub.add_parser("build", help="checks, build without drafts, leak check (+ draft preview)")
    b.add_argument("--preview", metavar="DIR", help="also build the draft preview into DIR")
    b.add_argument("--force", action="store_true", help="publish despite warnings (never past unreadable "
                   "files or LaTeX failures)")
    b.add_argument("--allow-dirty", action="store_true", help="build even with uncommitted changes")
    sub.add_parser("deploy", help="push _site/ to gh-pages and the code mirror to main")
    args = ap.parse_args()
    try:
        return {"fetch-data": cmd_fetch_data, "build": cmd_build, "deploy": cmd_deploy}[args.cmd](args)
    except Stop as e:
        print(f"error: {e}", file=sys.stderr)
        summary([f"**Error:** {e}"])
        return 1


if __name__ == "__main__":
    sys.exit(main())
