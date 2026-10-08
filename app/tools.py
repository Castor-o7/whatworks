"""Tools live in content/tools/*.md: software Josh builds, presented on /tools/ and /tools/<slug>/.

---
title: Storm Desk
summary: One sentence for the card on /tools/.
status: live                 (live | beta | coming-soon)
url: /storms                 (where it runs: a page on this site, or a full https:// URL)
source: https://github.com/...   (optional; its source code)
audience: Who it's for, in a phrase.
order: 1                     (optional; lower comes first)
---
Markdown body: how to use it, what's inside, caveats. Same syntax as posts (citations, storm charts).

A post links itself to a tool with `tool: <slug>` in its front matter; the tool page lists those
stories. Front matter is read by app/content.py, so drafts fail closed exactly as posts do.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import content

TOOLS = content.POSTS.parent / "tools"
KEYS = ("title", "summary", "status", "url", "source", "audience", "order", "draft")
STATUSES = {"live": "Live", "beta": "Beta", "coming-soon": "Coming soon"}


@dataclass
class Tool:
    slug: str
    title: str
    summary: str = ""
    status: str = "live"
    url: str = ""
    source: str = ""
    audience: str = ""
    order: int = 100
    body_md: str = ""
    draft: bool = False
    notes: list = field(default_factory=list, repr=False)

    @property
    def status_label(self):
        return STATUSES.get(self.status, self.status.title())

    def href(self, base=""):
        """Where 'Open' goes: a site path rebased onto `base`, a full URL as-is, or None."""
        if not self.url:
            return None
        if self.url.startswith("/") and not self.url.startswith("//"):
            return content.rebase(self.url.lstrip("/"), base)
        return self.url

    def html(self, base=""):
        return content.render(self.body_md, base)


def parse_text(text, slug, where):
    try:
        meta, body, notes = content.front_matter(text, KEYS)
    except ValueError as e:  # fail closed, like posts
        draft = any(content.value(v).lower() not in content.FALSE for v in content.DRAFT_KEY.findall(text))
        raise content.PostError(where, str(e), draft) from None
    order = meta.get("order", "")
    whole = re.fullmatch(r"-?[0-9]+", order)
    if order and not whole:
        notes.append(f"order: {order!r} isn't a whole number, so it sorts last")
    return Tool(
        slug=slug,
        title=meta.get("title") or slug.replace("-", " ").title(),
        summary=meta.get("summary", ""),
        status=(meta.get("status") or "live").lower(),
        url=meta.get("url", ""),
        source=meta.get("source", ""),
        audience=meta.get("audience", ""),
        order=int(order) if whole else 100,
        body_md=body.strip(),
        draft=meta["draft"],
        notes=notes,
    )


def parse(path: Path) -> Tool:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        if "\0" in text:  # UTF-16 without a byte-order mark (see content.parse)
            raise UnicodeDecodeError("utf-8", raw, 0, 1, "NUL byte")
    except UnicodeDecodeError:
        raise content.PostError(content._where(path), "isn't plain UTF-8 text; save it as UTF-8",
                                bool(content.DRAFT_KEY.search(content.loose_text(raw)))) from None
    return parse_text(text, path.stem, content._where(path))


def load_tools():
    """-> (tools, errors): every tool file, drafts included, plus a PostError for each unreadable one."""
    tools, errors = [], []
    for p in sorted(TOOLS.glob("*.md")):
        if p.name.startswith("."):
            continue
        try:
            tools.append(parse(p))
        except content.PostError as e:
            errors.append(e)
    return tools, errors


def ordered(tools):
    return sorted(tools, key=lambda t: (t.order, t.title.lower()))


def check(tool, meta=None):
    """Mistakes worth a warning, as messages."""
    warn = list(tool.notes)
    if tool.status not in STATUSES:
        warn.append(f"status: '{tool.status}' isn't one of: {', '.join(STATUSES)}")
    if not tool.summary:
        warn.append("the summary is empty (it's the one line shown on /tools/)")
    if tool.status != "coming-soon" and not tool.url:
        warn.append("no url: line, so there's no 'Open' button (use status: coming-soon if it isn't out yet)")
    for key in ("url", "source"):
        v = getattr(tool, key)
        if v and not (v.startswith(("https://", "http://")) or (key == "url" and v.startswith("/"))):
            warn.append(f"{key}: should be a full https:// address" + (" or a site path like /storms" if key == "url" else ""))
    warn += content.check_body(tool.body_md, meta)
    return warn
