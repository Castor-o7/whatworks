"""Posts live in content/posts/*.md with a small front-matter block:

---
title: Headline
date: 2026-10-08
section: storms
summary: One-sentence dek shown on cards.
video: https://www.youtube.com/watch?v=...   (optional; YouTube or Twitch video/clip URL)
tags: tornadoes, oklahoma
---
Markdown body. Drop a live chart from the storm database with:
[[storm-chart event_type="Tornado" state="Oklahoma"]]

Root-relative links in the body (/storms, /post/other-slug) are written as if the site lived at
the domain root; html() rewrites them onto the base path the site is actually served under.
"""
import html
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import markdown

POSTS = Path(__file__).resolve().parent.parent / "content" / "posts"
SHORTCODE = re.compile(r"\[\[storm-chart([^\]]*)\]\]")
ATTR = re.compile(r'(\w+)="([^"]*)"')
# href="/..." or src="/..." (but not protocol-relative "//host/...").
ROOT_LINK = re.compile(r'\b(href|src)="/(?!/)([^"]*)"')
OLD_EVENT = re.compile(r"^storms/event/(\d+)/?$")


def rebase(path: str, base: str) -> str:
    """'storms?x=1' -> '<base>/storms/?x=1'. Page URLs get the trailing slash Pages serves them at,
    and the old server's /storms/event/<id> becomes the static /storms/event/?id=<id>."""
    path, tail = re.match(r"([^?#]*)(.*)", path, re.S).groups()  # tail = ?query#fragment
    if m := OLD_EVENT.match(path):
        path, tail = "storms/event/", f"?id={m.group(1)}" + ("&" + tail[1:] if tail.startswith("?") else tail)
    elif path and not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return f"{base}/{path}{tail}"


@dataclass
class Post:
    slug: str
    title: str
    date: date
    section: str
    summary: str = ""
    video: str = ""
    tags: list = field(default_factory=list)
    body_md: str = ""
    draft: bool = False

    def html(self, base: str = ""):
        def chart(m):
            attrs = " ".join(
                f'data-{k.replace("_", "-")}="{html.escape(v)}"' for k, v in ATTR.findall(m.group(1))
            )
            return f'<figure class="storm-chart" {attrs}></figure>'

        def link(m):
            path = m.group(2)
            if base and (f"/{path}" + "/").startswith(base + "/"):
                return m.group(0)  # already on the base path
            return f'{m.group(1)}="{rebase(path, base)}"'

        body = SHORTCODE.sub(chart, self.body_md)
        return ROOT_LINK.sub(link, markdown.markdown(body, extensions=["extra", "smarty"]))


def parse(path: Path) -> Post:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        for line in head.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
    return Post(
        slug=path.stem,
        title=meta.get("title", path.stem.replace("-", " ").title()),
        date=date.fromisoformat(meta.get("date", "1970-01-01")),
        section=meta.get("section", "channel"),
        summary=meta.get("summary", ""),
        video=meta.get("video", ""),
        tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        body_md=body.strip(),
        draft=meta.get("draft", "").lower() == "true",
    )


def all_posts():
    """Every published post, newest first (drafts are skipped)."""
    posts = [parse(p) for p in POSTS.glob("*.md")]
    return sorted((p for p in posts if not p.draft), key=lambda p: p.date, reverse=True)


def embed_url(url: str, twitch_parents) -> str | None:
    """Turn a YouTube/Twitch watch or clip URL into an iframe src."""
    if not url:
        return None
    u = urlparse(url)
    host = u.netloc.lower().removeprefix("www.").removeprefix("m.")
    parents = "".join(f"&parent={p}" for p in twitch_parents)
    if host == "youtu.be":
        return f"https://www.youtube-nocookie.com/embed/{u.path.lstrip('/')}"
    if host == "youtube.com":
        if u.path.startswith(("/shorts/", "/embed/", "/live/")):
            return f"https://www.youtube-nocookie.com/embed/{u.path.split('/')[2]}"
        if v := parse_qs(u.query).get("v"):
            return f"https://www.youtube-nocookie.com/embed/{v[0]}"
    if host == "clips.twitch.tv":
        return f"https://clips.twitch.tv/embed?clip={u.path.strip('/')}{parents}"
    if host == "twitch.tv":
        parts = u.path.strip("/").split("/")
        if len(parts) >= 3 and parts[1] == "clip":
            return f"https://clips.twitch.tv/embed?clip={parts[2]}{parents}"
        if len(parts) >= 2 and parts[0] == "videos":
            return f"https://player.twitch.tv/?video={parts[1]}{parents}"
        if len(parts) == 1 and parts[0]:
            return f"https://player.twitch.tv/?channel={parts[0]}{parents}"
    return None
