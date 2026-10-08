"""Render the pages of the static site into _site/ (see docs/STATIC_SITE.md).

    .venv/bin/python scripts/build_site.py

Fast (about a second): renders templates + posts and copies app/static. It never touches
_site/data/, which scripts/build_data.py writes once from data/storms.db. Run it after
build_data.py so the Storm Desk stat tiles and dropdowns come from _site/data/meta.json.gz.
"""
import gzip
import json
import shutil
import sys
import tomllib
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import content  # noqa: E402

OUT = ROOT / "_site"
SITE = tomllib.loads((ROOT / "site.toml").read_text())
BASE = ("/" + SITE.get("base_url", "").strip("/")).rstrip("/")  # "/whatworks", or "" at a domain root
SECTIONS = {s["slug"]: s for s in SITE["sections"]}
# Everything this script writes at the top of _site/. Nothing else there is ever deleted.
OWNED = ("index.html", "404.html", ".nojekyll", "section", "post", "storms", "about", "static")


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


def build():
    env = environment()
    posts = content.all_posts()
    meta = load_meta()
    pages = {}  # output path under _site -> (template, context)

    # Page URLs end in "/", so each is a directory with an index.html (Pages serves those as-is).
    pages["index.html"] = ("home.html", dict(lead=posts[0] if posts else None, recent=posts[1:7],
                                             videos=[p for p in posts if p.video][:3]))
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
    print(f"built {len(pages)} pages + static into {OUT.relative_to(ROOT)}/ (base {BASE or '/'})")


if __name__ == "__main__":
    build()
