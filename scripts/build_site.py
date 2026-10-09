"""Render the pages of the static site into _site/ (see docs/STATIC_SITE.md).

    .venv/bin/python scripts/build_site.py            # what gets published
    .venv/bin/python scripts/build_site.py --drafts   # also render drafts, for local preview only

Fast (about a second): renders templates + posts and copies app/static. It never touches
_site/data/, which scripts/build_data.py writes once from data/storms.db. Run it after
build_data.py so the Storm Desk stat tiles and dropdowns come from _site/data/meta.json.gz.
"""
import argparse
import gzip
import json
import shutil
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import content, tools as toolkit  # noqa: E402

OUT = ROOT / "_site"
SITE = tomllib.loads((ROOT / "site.toml").read_text())
BASE = ("/" + SITE.get("base_url", "").strip("/")).rstrip("/")  # "/whatworks", or "" at a domain root
SECTIONS = {s["slug"]: s for s in SITE["sections"]}
# Everything this script writes at the top of _site/. Nothing else there is ever deleted.
DRAFTS_MARKER = ".drafts"  # present only in a --drafts preview build; deploy.sh refuses to publish it
OWNED = ("index.html", "404.html", ".nojekyll", DRAFTS_MARKER, "section", "post", "storms", "tools", "about",
         "static")


def environment():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"), autoescape=True)
    today = date.today()
    env.globals.update(site=SITE, sections=SITE["sections"], section_map=SECTIONS, base=BASE,
                       today_label=f"{today:%A, %B} {today.day}, {today.year}")
    env.filters["embed"] = lambda url: content.embed_url(url, SITE["channels"]["twitch_parents"])
    env.filters["nicedate"] = lambda d: f"{d:%B} {d.day}, {d.year}"
    return env


def load_meta():
    path = OUT / "data" / "meta.json.gz"
    if not path.exists():
        print(f"warning: {path.relative_to(ROOT)} is missing; the Storm Desk renders without stats or "
              "filters. Run scripts/build_data.py, then build the site again.", file=sys.stderr)
        return None
    return json.loads(gzip.decompress(path.read_bytes()))


def cpi_base_year(meta):
    """The year Then & Now states real dollars in: cpi.json's base_year (docs/THEN_AND_NOW.md), else the
    last year of storm data. Only labels depend on it; then-now.js does the arithmetic from cpi.json."""
    path = OUT / "data" / "cpi.json.gz"
    try:
        return json.loads(gzip.decompress(path.read_bytes()))["base_year"]
    except (OSError, ValueError, KeyError):
        return meta and meta.get("last_year")


def problems(posts, errors, meta, tools=()):
    """Every warning about the posts and tools, as 'content/<kind>/x.md: message' lines."""
    out = [f"{e} (skipped)" for e in errors]
    slugs = {t.slug for t in tools}
    for p in posts:
        out += [f"content/posts/{p.slug}.md: {w}" for w in content.check(p, list(SECTIONS), meta, slugs)]
    for t in tools:
        out += [f"content/tools/{t.slug}.md: {w}" for w in toolkit.check(t, meta)]
    return out


def visible_tools(drafts=False):
    """-> (tools, errors): tools to render, in display order; drafts only for a preview build."""
    found, errors = toolkit.load_tools()
    return toolkit.ordered(t for t in found if drafts or not t.draft), errors


def build(drafts=False, report=True):
    """Render the site; report=False leaves printing post warnings to the caller (publish.py)."""
    env = environment()
    found, errors = content.load_posts()
    posts = sorted((p for p in found if drafts or not p.draft), key=lambda p: p.date, reverse=True)
    tools, tool_errors = visible_tools(drafts)
    meta = load_meta()
    if report:
        for line in problems(posts, errors + tool_errors, meta, tools):
            print(f"warning: {line}", file=sys.stderr)
    env.globals["tool_map"] = {t.slug: t for t in tools}  # for "Built with" links on posts
    pages = {}  # output path under _site -> (template, context)

    # Page URLs end in "/", so each is a directory with an index.html (Pages serves those as-is).
    pages["index.html"] = ("home.html", dict(lead=posts[0] if posts else None, recent=posts[1:7],
                                             videos=[p for p in posts if p.video][:3], tools=tools))
    for slug, s in SECTIONS.items():
        if slug != "storms":  # that section is the Storm Desk at /storms/
            pages[f"section/{slug}/index.html"] = ("section.html", dict(
                section=s, posts=[p for p in posts if p.section == slug]))
    for p in posts:
        related = [x for x in posts if x.section == p.section and x.slug != p.slug][:3]
        pages[f"post/{p.slug}/index.html"] = ("post.html", dict(post=p, related=related))
    pages["storms/index.html"] = ("storms.html", dict(
        posts=[p for p in posts if p.section == "storms"], storm_ok=meta is not None, meta=meta))
    pages["storms/event/index.html"] = ("event.html", {})
    pages["storms/then-and-now/index.html"] = ("thenandnow.html", dict(
        storm_ok=meta is not None, meta=meta, base_year=cpi_base_year(meta)))
    pages["tools/index.html"] = ("tools.html", dict(tools=tools))
    for t in tools:
        pages[f"tools/{t.slug}/index.html"] = ("tool.html", dict(
            tool=t, stories=[p for p in posts if p.tool == t.slug]))
    pages["about/index.html"] = ("about.html", {})
    pages["404.html"] = ("404.html", {})

    # Clear what an earlier build rendered (pages for renamed or deleted posts). Only the paths this
    # script owns: data/ (and build_data.py's scratch dirs beside it) and the deploy repo in .git/
    # are left alone.
    OUT.mkdir(exist_ok=True)
    for name in OWNED:
        child = OUT / name
        if child.is_dir():
            shutil.rmtree(child)
        elif child.exists():
            child.unlink()

    for rel, (template, ctx) in pages.items():
        out = OUT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(env.get_template(template).render(**ctx), encoding="utf-8")

    shutil.copytree(ROOT / "app" / "static", OUT / "static",
                    ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"))
    (OUT / ".nojekyll").write_text("")  # serve files as-is; no Jekyll processing
    shown = [p for p in posts if p.draft] + [t for t in tools if t.draft]
    if shown:
        # deploy.sh refuses to publish while this marker exists, so drafts never go live by accident.
        (OUT / DRAFTS_MARKER).write_text("".join(f"{p.slug}\n" for p in shown))
    print(f"built {len(pages)} pages + static into {OUT.relative_to(ROOT)}/ (base {BASE or '/'})"
          + (f" — including {len(shown)} draft(s); preview only, rebuild without --drafts to publish"
             if shown else ""))
    return posts


def install_draft_guard():
    """Point git at scripts/git-hooks, whose pre-commit hook refuses to commit a draft whatever does the
    committing (git, GitHub Desktop, an editor). The repo is public, so this backs up publish.py."""
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    try:
        if git("rev-parse", "--show-toplevel").stdout.strip() != str(ROOT.resolve()):
            return  # not a git checkout of this project
        current = git("config", "--get", "core.hooksPath").stdout.strip()
        if current == "scripts/git-hooks":
            return
        if current:
            print(f"note: git's core.hooksPath is already {current!r}, so the draft guard "
                  "(scripts/git-hooks/pre-commit) isn't installed.", file=sys.stderr)
            return
        if git("config", "core.hooksPath", "scripts/git-hooks").returncode == 0:
            print("Installed the draft guard: git will now refuse to commit a draft.")
    except OSError:
        pass  # no git on this machine


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render the site's pages into _site/.")
    ap.add_argument("--drafts", action="store_true", help="also render drafts (local preview; can't be deployed)")
    build(drafts=ap.parse_args().drafts)
