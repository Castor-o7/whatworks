"""Posts live in content/posts/*.md with a small front-matter block:

---
title: Headline
date: 2026-10-08
section: storms
summary: One-sentence dek shown on cards.
video: https://www.youtube.com/watch?v=...   (optional; YouTube or Twitch video/clip URL)
image: grid-map.png  (optional; the link-preview image: a file in content/images/ or an https:// URL)
tags: tornadoes, oklahoma
draft: true        (optional; a draft is only rendered by a local --drafts preview)
---
The block opens and closes with lines that are exactly '---'. Values may be quoted and may end in
'  # a comment'. Drafts fail closed: any draft value other than a clear false (false/no/off/0), or a
file whose front matter can't be read, is never published.

Markdown body. Drop a live chart from the storm database with:
[[storm-chart event_type="Tornado" state="Oklahoma"]]
or a compact Then & Now comparison of two eras (docs/THEN_AND_NOW.md) with:
[[then-now then="1955-1974" now="2005-2024" state="Oklahoma" metric="deaths"]]

Root-relative links in the body (/storms, /post/other-slug) are written as if the site lived at
the domain root; html() rewrites them onto the base path the site is actually served under.

Citations are Markdown footnotes (Claim.[^1] ... [^1]: Source, URL); html() renders them as a
"Sources" list. HTML comments (<!-- writing prompts -->) are stripped so they never get published.
See docs/WRITING.md.
"""
import difflib
import html
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import markdown

POSTS = Path(__file__).resolve().parent.parent / "content" / "posts"
TEMPLATE = POSTS.parent / "POST_TEMPLATE.md"
SHORTCODE = re.compile(r"\[\[storm-chart([^\]]*)\]\]")
# name="value"; also 'value' and the curly “value” that smart-quote editors (TextEdit) type.
ATTR = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|“([^”]*)”|'([^']*)')""")
# What a [[storm-chart]] accepts (app/static/charts.js draws it).
CHART_OPTIONS = {"chart", "metric", "event_type", "state", "year_from", "year_to", "title", "sub", "limit"}
CHARTS = ("years", "types", "states", "months")
METRICS = ("events", "deaths", "injuries", "damage")
# [[then-now ...]]: a compact Then & Now comparison (app/static/charts.js draws it in posts).
THEN_NOW = re.compile(r"\[\[then-now([^\]]*)\]\]")
THEN_NOW_OPTIONS = {"then", "now", "state", "metric", "dollars"}
THEN_NOW_DEFAULTS = {"then": "1955-1974", "now": "2005-2024", "metric": "events"}  # the page's default view
ERA = re.compile(r"\s*(\d{4})\s*(?:[-–—]|to)\s*(\d{4})\s*|\s*(\d{4})\s*")  # "1955-1974", "1955–1974", "2024"
# href="/..." or src="/..." (but not protocol-relative "//host/...").
ROOT_LINK = re.compile(r'\b(href|src)="/(?!/)([^"]*)"')
OLD_EVENT = re.compile(r"^storms/event/(\d+)/?$")
COMMENT = re.compile(r"<!--.*?-->\n?", re.S)
# Footnote definitions ([^1]: ...) and their indented continuation lines get their bare URLs wrapped
# in <...> so Markdown links them. A URL may hold balanced parentheses (Wikipedia's Mercury_(planet));
# one already inside <...>, a [text](url) link or an attribute="..." is left alone.
FOOTNOTE_DEF = re.compile(r"^\[\^[^\]]+\]:", re.M)
BARE_URL = re.compile(r"""(?<!<)(?<!\]\()(?<!=")(?<!=')\bhttps?://(?:[^\s<>()\[\]"']|\([^\s<>()]*\))+""")
FOOTNOTE_REF = re.compile(r"\[\^([^\]]+)\](?!:)")
# Python-Markdown's footnote block; it always comes last in the output.
FOOTNOTES = re.compile(r'<div class="footnote">\s*<hr ?/?>\s*(<ol>.*</ol>)\s*</div>\s*$', re.S)
# Front matter: values may be "quoted", and end in an optional "  # comment".
TRUE, FALSE = ("true", "yes", "on", "1"), ("false", "no", "off", "0")
KEYS = ("title", "date", "section", "summary", "video", "image", "tags", "tool", "draft")
VALUE_COMMENT = re.compile(r"(?:^|\s+)#(?:\s.*)?$")
# Used only when a file can't be parsed: any draft line that isn't clearly false means a draft.
DRAFT_KEY = re.compile(r"^\W*draft\w*\W*:(.*)$", re.I | re.M)


class PostError(ValueError):
    """A post file that can't be read. draft=True means it is (or may be) a draft: it's skipped with
    a warning. Otherwise it's a post meant to be live, and scripts/publish.py stops until it's fixed."""

    def __init__(self, where, message, draft):
        super().__init__(f"{where}: {message}")
        self.draft = draft


def _fence(text):
    """-> (lines, end): text's lines (byte-order mark and leading blank lines dropped) and the index of
    the front matter's closing line. The block opens and closes with lines that are exactly '---', so
    a '---' inside a title or summary (an em dash, thanks to smarty) can't end it early."""
    lines = text.lstrip("﻿").lstrip().splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        raise ValueError("it must start with the front-matter block: a line that is just ---")
    for end in range(1, len(lines)):
        if lines[end].rstrip() == "---":
            return lines, end
    raise ValueError("the front matter at the top has no closing --- line")


def value(raw):
    """'"Heat: why"' -> 'Heat: why'; 'true   # note' -> 'true'; '#1 reason' stays as-is."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        rest = raw[end + 1:].strip() if end > 0 else "x"
        if not rest or rest.startswith("#"):
            return raw[1:end]
    return VALUE_COMMENT.sub("", raw)


def front_matter(text, keys=KEYS):
    """-> (meta, body, notes). keys: the known keys (posts by default; app/tools.py passes its own).
    Raises ValueError when the block can't be read."""
    lines, end = _fence(text)
    meta, drafts, notes = {}, [], []
    for n, line in enumerate(lines[1:end], 2):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"line {n} of the front matter isn't 'key: value': {line!r}")
        k, v = line.split(":", 1)
        k = k.strip().strip("\"'").lower()
        if "draft" in k:  # 'draft', 'Draft', 'drafts', ... all count
            drafts.append(value(v))
        elif k in keys:
            meta[k] = value(v)
        else:
            notes.append(f"unknown front-matter key '{k}' (ignored); the keys are: {', '.join(keys)}")
    draft = False
    for v in drafts:  # fail closed: anything but a clear "false" keeps it a draft
        if v.lower() in TRUE:
            draft = True
        elif v.lower() not in FALSE:
            draft = True
            notes.append(f"draft: {v!r} isn't true or false, so it stays a draft (delete the line to publish)"
                         if v else "'draft:' has no value, so it stays a draft (delete the line to publish)")
    meta["draft"] = draft
    return meta, "".join(lines[end + 1:]), notes


def set_fields(text, fields):
    """Rewrite front-matter keys in place (other lines, and the body, are kept as-is)."""
    lines, end = _fence(text)
    for i in range(1, end):
        key = lines[i].split(":", 1)[0].strip().lower()
        if ":" in lines[i] and key in fields:
            lines[i] = f"{key}: {fields[key]}".rstrip() + "\n"
    return "".join(lines)

def rebase(path: str, base: str) -> str:
    """'storms?x=1' -> '<base>/storms/?x=1'. Page URLs get the trailing slash Pages serves them at,
    and the old server's /storms/event/<id> becomes the static /storms/event/?id=<id>."""
    path, tail = re.match(r"([^?#]*)(.*)", path, re.S).groups()  # tail = ?query#fragment
    if m := OLD_EVENT.match(path):
        path, tail = "storms/event/", f"?id={m.group(1)}" + ("&" + tail[1:] if tail.startswith("?") else tail)
    elif path and not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return f"{base}/{path}{tail}"


def chart_options(text):
    """'state="Oklahoma" chart=“types”' -> {'state': 'Oklahoma', 'chart': 'types'}"""
    return {m[0]: "".join(m[1:]) for m in ATTR.findall(text)}


def era(text):
    """'1955-1974' (or an en dash, or a single year) -> (1955, 1974); None if it isn't one."""
    m = ERA.fullmatch(text or "")
    if not m:
        return None
    a, b, one = m.groups()
    return (int(one), int(one)) if one else (int(a), int(b))


def then_now_attrs(opts):
    """A [[then-now]]'s options with defaults filled in and eras written as 'YYYY-YYYY'."""
    attrs = {**THEN_NOW_DEFAULTS, **{k: v.strip() for k, v in chart_options(opts).items()}}
    for k in ("then", "now"):
        if span := era(attrs[k]):
            attrs[k] = f"{span[0]}-{span[1]}"
    return attrs


def link_footnote_urls(body):
    """Wrap bare URLs in footnote definitions (and their indented continuation lines) in <...>."""
    def wrap(m):
        url = m.group(0).rstrip(".,;:!?")  # a sentence's closing punctuation isn't part of the URL
        return f"<{url}>{m.group(0)[len(url):]}"

    out, inside = [], False
    for line in body.split("\n"):
        if FOOTNOTE_DEF.match(line):
            inside = True
        elif line.strip() and not line[:1].isspace():
            inside = False
        out.append(BARE_URL.sub(wrap, line) if inside else line)
    return "\n".join(out)


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
    tool: str = ""  # slug of a tool in content/tools/ this story was built with (see app/tools.py)
    image: str = ""  # link-preview image: a file in content/images/ or an https:// URL (docs/SHARING.md)
    notes: list = field(default_factory=list, repr=False)  # front-matter warnings from parse()

    def html(self, base: str = ""):
        return render(self.body_md, base)


def render(body_md, base=""):
    """Markdown body -> HTML: storm charts, citations as a Sources list, links rebased onto `base`.
    Shared by posts and tool pages."""
    def chart(m):
        attrs = " ".join(
            f'data-{k.replace("_", "-")}="{html.escape(v)}"' for k, v in chart_options(m.group(1)).items()
        )
        return f'<figure class="storm-chart" {attrs}></figure>'

    def then_now(m):
        attrs = " ".join(f'data-{k.replace("_", "-")}="{html.escape(v)}"'
                         for k, v in then_now_attrs(m.group(1)).items() if v)
        return f'<figure class="then-now" {attrs}></figure>'

    def link(m):
        path = m.group(2)
        if base and (f"/{path}" + "/").startswith(base + "/"):
            return m.group(0)  # already on the base path
        return f'{m.group(1)}="{rebase(path, base)}"'

    body = link_footnote_urls(COMMENT.sub("", body_md))
    body = SHORTCODE.sub(chart, body)
    body = THEN_NOW.sub(then_now, body)
    # Number footnotes in the order they're cited, wherever their definitions are written.
    out = markdown.markdown(body, extensions=["extra", "smarty"],
                            extension_configs={"extra": {"footnotes": {"USE_DEFINITION_ORDER": False}}})
    out = FOOTNOTES.sub(lambda m: '<section class="sources" aria-labelledby="sources">'
                                  f'<h2 id="sources">Sources</h2>{m.group(1)}</section>', out)
    return ROOT_LINK.sub(link, out)


def _where(path):
    try:
        return str(path.relative_to(POSTS.parent.parent))
    except ValueError:
        return str(path)


def parse_text(text, slug, where):
    """A post from its text. Raises PostError (naming `where`) when it can't be read."""
    try:
        meta, body, notes = front_matter(text)
    except ValueError as e:  # fail closed: a draft line that isn't clearly "false" keeps it a draft
        draft = any(value(v).lower() not in FALSE for v in DRAFT_KEY.findall(text))
        raise PostError(where, str(e), draft) from None
    if not meta.get("date"):
        notes.append("no date: line, so it sorts as 1970-01-01")
    try:
        when = date.fromisoformat(meta.get("date") or "1970-01-01")
    except ValueError:
        raise PostError(where, f"date must look like 2026-10-08 (it says {meta['date']!r})",
                        meta["draft"]) from None
    return Post(
        slug=slug,
        title=meta.get("title") or slug.replace("-", " ").title(),
        date=when,
        section=meta.get("section") or "channel",
        summary=meta.get("summary", ""),
        video=meta.get("video", ""),
        tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        tool=meta.get("tool", ""),
        image=meta.get("image", ""),
        body_md=body.strip(),
        draft=meta["draft"],
        notes=notes,
    )


def loose_text(raw: bytes) -> str:
    """Best-effort text of a file that may not be UTF-8 (UTF-16/32 from TextEdit or Windows editors),
    used only to look for a draft line so such a file still fails closed."""
    for bom, enc in ((b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
                     (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                break
    return raw.decode("utf-8", "replace").replace("\0", "")


def parse(path: Path) -> Post:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        if "\0" in text:  # UTF-16 without a byte-order mark decodes as "UTF-8" full of NULs
            raise UnicodeDecodeError("utf-8", raw, 0, 1, "NUL byte")
    except UnicodeDecodeError:
        raise PostError(_where(path), "isn't plain UTF-8 text; save it as UTF-8",
                        bool(DRAFT_KEY.search(loose_text(raw)))) from None
    return parse_text(text, path.stem, _where(path))


def is_draft(text, where="post"):
    """True for a draft, and for a broken file that may be one (see PostError)."""
    try:
        return parse_text(text, "post", where).draft
    except PostError as e:
        return e.draft


def load_posts():
    """-> (posts, errors): every post file, drafts included, and a PostError for each that can't be read."""
    posts, errors = [], []
    for p in sorted(POSTS.glob("*.md")):
        if p.name.startswith("."):  # editor scratch files, never posts
            continue
        try:
            posts.append(parse(p))
        except PostError as e:
            errors.append(e)
    return posts, errors


def all_posts(drafts=False):
    """Every published post, newest first. drafts=True also includes drafts (local preview only).
    Files that can't be read are left out; load_posts() reports them."""
    posts, _ = load_posts()
    return sorted((p for p in posts if drafts or not p.draft), key=lambda p: p.date, reverse=True)


@lru_cache(maxsize=1)
def _template():
    try:
        return parse(TEMPLATE)
    except (OSError, PostError):
        return None


def _suggest(v, choices):
    close = [c for c in choices if c.lower() == v.lower()] or difflib.get_close_matches(v, choices, 1, 0.6)
    return f" (did you mean {close[0]!r}?)" if close else ""


def check_chart(code, opts, meta=None):
    """Warnings for one [[storm-chart ...]]; meta (_site/data/meta.json.gz) adds state/type checks."""
    code = " ".join(code.split())
    attrs = chart_options(opts)
    warn = []
    if ATTR.sub("", opts).strip():
        warn.append(f'{code}: couldn\'t read all of its options; write each as name="value"')
    for k in sorted(attrs.keys() - CHART_OPTIONS):
        warn.append(f"{code}: unknown option '{k}'{_suggest(k, sorted(CHART_OPTIONS))}")
    if attrs.get("chart", "years") not in CHARTS:
        warn.append(f"{code}: chart must be one of {', '.join(CHARTS)}{_suggest(attrs['chart'], CHARTS)}")
    if attrs.get("metric", "events") not in METRICS:
        warn.append(f"{code}: metric must be one of {', '.join(METRICS)}{_suggest(attrs['metric'], METRICS)}")
    for k in ("year_from", "year_to", "limit"):
        if k in attrs and not attrs[k].strip().isdigit():
            warn.append(f"{code}: {k} must be a number")
    if meta:
        states = [s for s in meta.get("states", []) if s]
        if attrs.get("state") and attrs["state"] not in states:
            warn.append(f"{code}: no state named {attrs['state']!r} in the storm data{_suggest(attrs['state'], states)}."
                        " Use full names, spelled as in the Storm Desk's State menu (e.g. Oklahoma)")
        for t in (t.strip() for t in attrs.get("event_type", "").split(",")):
            if t and t not in meta.get("types", []):
                warn.append(f"{code}: no event type {t!r} in the storm data{_suggest(t, meta['types'])}."
                            " Use NOAA's labels, spelled as in the Storm Desk's Event type menu")
    return warn


def check_then_now(code, opts, meta=None):
    """Warnings for one [[then-now ...]]; meta (_site/data/meta.json.gz) adds year-range and state checks."""
    code = " ".join(code.split())
    raw = chart_options(opts)
    attrs = then_now_attrs(opts)
    warn = []
    if ATTR.sub("", opts).strip():
        warn.append(f'{code}: couldn\'t read all of its options; write each as name="value"')
    for k in sorted(raw.keys() - THEN_NOW_OPTIONS):
        warn.append(f"{code}: unknown option '{k}'{_suggest(k, sorted(THEN_NOW_OPTIONS))}")
    if attrs["metric"] not in METRICS:
        warn.append(f"{code}: metric must be one of {', '.join(METRICS)}{_suggest(attrs['metric'], METRICS)}")
    if raw.get("dollars") and raw["dollars"].strip() not in ("real", "nominal"):
        warn.append(f"{code}: dollars must be real (inflation-adjusted, the default) or nominal (as reported)"
                    f"{_suggest(raw['dollars'].strip(), ['real', 'nominal'])}")
    first, last = (meta or {}).get("first_year"), (meta or {}).get("last_year")
    for k in ("then", "now"):
        span = era(attrs[k])
        if not span:
            warn.append(f'{code}: {k} must be a range of years like {k}="{THEN_NOW_DEFAULTS[k]}"')
        elif span[0] > span[1]:
            warn.append(f"{code}: {k} starts after it ends ({span[0]} > {span[1]}); write the earlier year first")
        elif first and last and (span[0] < first or span[1] > last):
            warn.append(f"{code}: {k}={attrs[k]!r} is outside the storm data, which covers {first}–{last}")
    if meta and attrs.get("state"):
        states = [s for s in meta.get("states", []) if s]
        if attrs["state"] not in states:
            warn.append(f"{code}: no state named {attrs['state']!r} in the storm data{_suggest(attrs['state'], states)}."
                        " Use full names, spelled as in the Storm Desk's State menu (e.g. Oklahoma)")
    return warn


def check_body(body_md, meta=None, image=""):
    """Warnings about a Markdown body (posts and tool pages): unclosed comments, storm charts, citations,
    and the share image (the image: key, and /images/ files linked in the text)."""
    from . import share  # Pillow; only needed for checking
    warn = []
    body = COMMENT.sub("", body_md)
    warn += share.check_image(image, body)
    if "<!--" in body:
        warn.append("a <!-- comment is never closed with -->, so everything after it is hidden")
    for m in SHORTCODE.finditer(body):
        warn += check_chart(m.group(0), m.group(1), meta)
    for m in THEN_NOW.finditer(body):
        warn += check_then_now(m.group(0), m.group(1), meta)
    defined = set(re.findall(r"^\[\^([^\]]+)\]:", body, re.M))
    for ref in sorted(set(FOOTNOTE_REF.findall(body)) - defined):
        warn.append(f"[^{ref}] is cited but has no source line ('[^{ref}]: ...'), so it shows as plain text")
    return warn


def check(post, sections=None, meta=None, tools=None):
    """Mistakes worth a warning, as messages. sections: the valid section slugs; meta: storm-data
    metadata for checking charts; tools: the slugs of published tools. Posts that aren't drafts are
    also checked for template leftovers."""
    warn = list(post.notes)
    if sections is not None and post.section not in sections:
        warn.append(f"section '{post.section}' isn't one of: {', '.join(sections)} (its section link would 404)")
    if post.tool and tools is not None and post.tool not in tools:
        warn.append(f"tool: '{post.tool}' isn't a published tool" + _suggest(post.tool, sorted(tools))
                    + (f" (tools: {', '.join(sorted(tools))})" if tools else " (there are no tools yet)"))
    warn += check_body(post.body_md, meta, post.image)
    body = COMMENT.sub("", post.body_md)
    if post.draft:
        return warn
    tpl = _template()
    if tpl and post.title == tpl.title:
        warn.append("the title is still the template's")
    if not post.summary or (tpl and post.summary == tpl.summary):
        warn.append("the summary is " + ("empty" if not post.summary else "still the template's placeholder"))
    lines = body.splitlines()
    heads = [i for i, line in enumerate(lines) if re.match(r"#{1,2}\s", line)] + [len(lines)]
    for i, nxt in zip(heads, heads[1:]):
        if lines[i].startswith("## ") and not any(
                line.strip() and not FOOTNOTE_DEF.match(line) for line in lines[i + 1:nxt]):
            warn.append(f"the section '{lines[i].strip()}' is empty (write it, or delete the heading)")
    if not body.strip():
        warn.append("the post has no text")
    return warn

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
