#!/usr/bin/env python3
"""Start a new post: a dated draft in content/posts/, made from content/POST_TEMPLATE.md.

    scripts/new_post.py "Why the power grid hates heat waves" --section science
    scripts/new_post.py "Clip: storm chasing math" --section channel --video https://youtu.be/ID

The post starts as a draft (draft: true), so it stays private until you delete that line and run
scripts/publish.py. Preview drafts with scripts/preview.py. Guide: docs/WRITING.md
"""
import argparse
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Run with the project's virtualenv (it has jinja2 + markdown) even when started as scripts/<name>.py.
VENV = ROOT / ".venv"
if (VENV / "bin" / "python").exists() and Path(sys.prefix).resolve() != VENV.resolve():
    os.execv(VENV / "bin" / "python", [str(VENV / "bin" / "python"), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import content  # noqa: E402
import build_site  # noqa: E402

POSTS = content.POSTS
TEMPLATE = content.TEMPLATE
SITE = build_site.SITE
SECTIONS = list(build_site.SECTIONS)


def slugify(title, max_len=60):
    """'Why the Grid Hates Heat Waves!' -> 'why-the-grid-hates-heat-waves' (cut at a word boundary)."""
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug or "post"


def quoted(text):
    """Quote a front-matter value if it would otherwise be read back differently ('A # B', '"x" y"')."""
    if content.value(text) == text:
        return text
    return f'"{text}"' if '"' not in text else f"'{text}'"


def fill(template, fields):
    """Set front-matter keys in the template; everything else (the body prompts) is kept as-is."""
    return content.set_fields(template, fields)


def main():
    ap = argparse.ArgumentParser(description="Start a new draft post.")
    ap.add_argument("title", help="the headline, in quotes")
    ap.add_argument("--section", required=True, choices=SECTIONS, help="which section it belongs to")
    ap.add_argument("--video", default="", help="optional YouTube or Twitch video/clip URL to embed at the top")
    ap.add_argument("--tags", default="", help="optional comma-separated tags, e.g. 'heat, grid'")
    args = ap.parse_args()

    title = " ".join(args.title.split())
    if not title:
        raise SystemExit("error: the title is empty")
    base = slugify(title)
    path, n = POSTS / f"{base}.md", 2
    while path.exists():  # never overwrite: another post already has this slug
        path, n = POSTS / f"{base}-{n}.md", n + 1

    POSTS.mkdir(parents=True, exist_ok=True)
    path.write_text(fill(TEMPLATE.read_text(encoding="utf-8"), {
        "title": quoted(title), "date": date.today().isoformat(), "section": args.section,
        "video": args.video.strip(), "tags": args.tags.strip(), "draft": "true",
    }), encoding="utf-8")
    # Read it back the way the build will: it must be a draft, with the title as typed.
    post = content.parse(path)
    if not post.draft or post.title != title:
        path.unlink()
        raise SystemExit(f"error: couldn't write a draft for that title (it read back as {post.title!r}, "
                         f"draft={post.draft}); nothing was created. Try a simpler title and edit it in the file.")

    rel = path.relative_to(ROOT)
    print(f"Created {rel} (a private draft)\n")
    print("Next:")
    print(f"  1. Write it:   open {rel} in your editor (keep the --- block at the top)")
    print("  2. Preview:    scripts/preview.py")
    print(f"                 -> http://localhost:8000{SITE.get('base_url', '')}/post/{path.stem}/")
    print("  3. Publish:    delete the line 'draft: true', set date: to the day you publish,")
    print("                 then run scripts/publish.py")
    build_site.install_draft_guard()
    return 0


if __name__ == "__main__":
    sys.exit(main())
