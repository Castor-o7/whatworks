"""Render the pages of the static site into _site/ (see docs/STATIC_SITE.md).

    .venv/bin/python scripts/build_site.py            # what gets published
    .venv/bin/python scripts/build_site.py --drafts   # also render drafts, for local preview only

Fast (about a second): renders templates + posts and copies app/static. It never touches
_site/data/, which scripts/build_data.py writes once from data/storms.db. Run it after
build_data.py so the Storm Desk stat tiles and dropdowns come from _site/data/meta.json.gz.

It also writes what lets the site travel (docs/SHARING.md): link-preview tags in every page's head, a
share card per post, tool and paper (_site/static/og/, drawn with Pillow and cached in .cache/og/), the
Atom feed (feed.xml) and the sitemap (sitemap.xml), and copies the images posts use from content/images/.

Papers (content/papers/<slug>/, docs/WRITING.md "Papers") are compiled by scripts/build_papers.py
(cached in .cache/papers/, so only a changed paper takes LaTeX time) and published at
/papers/<slug>/<slug>.pdf. Drafts are compiled only with --drafts. A paper LaTeX can't compile is left
out of a published build (with a warning; publish.py stops on it) and shown with its error in a preview.
"""
import argparse
import gzip
import html
import json
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin
from xml.sax.saxutils import escape as xml_escape, quoteattr

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import content, papers as paperkit, share as sharing, tools as toolkit  # noqa: E402
import build_papers  # noqa: E402

OUT = ROOT / "_site"
SITE = tomllib.loads((ROOT / "site.toml").read_text())
BASE = ("/" + SITE.get("base_url", "").strip("/")).rstrip("/")  # "/whatworks", or "" at a domain root
SECTIONS = {s["slug"]: s for s in SITE["sections"]}
# Absolute URLs (link previews, feed, sitemap) are site_url + base_url + path.
SITE_URL = SITE.get("site_url", "").strip().rstrip("/")
ABS = SITE_URL + BASE  # "https://castor-o7.github.io/whatworks"
HOST = ABS.split("://", 1)[-1]  # shown on share cards
CARD_CACHE = ROOT / ".cache" / "og"  # drawn cards, kept between builds (gitignored)
FEED_SIZE = 20
# Everything this script writes at the top of _site/. Nothing else there is ever deleted.
DRAFTS_MARKER = ".drafts"  # present only in a --drafts preview build; ci_publish.py refuses to publish it
OWNED = ("index.html", "404.html", ".nojekyll", DRAFTS_MARKER, "section", "post", "storms", "tools", "papers",
         "about", "static", "images", "feed.xml", "sitemap.xml")


def environment():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"), autoescape=True)
    today = date.today()
    env.globals.update(site=SITE, sections=SITE["sections"], section_map=SECTIONS, base=BASE, abs_base=ABS,
                       today_label=f"{today:%A, %B} {today.day}, {today.year}")
    env.filters["embed"] = lambda url: content.embed_url(url, SITE["channels"]["twitch_parents"])
    env.filters["nicedate"] = lambda d: f"{d:%B} {d.day}, {d.year}"
    return env


def display_path(path):
    """A path for messages: relative to the project when it's inside it (OUT can be elsewhere: the draft
    preview that scripts/ci_publish.py builds)."""
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def load_meta():
    path = OUT / "data" / "meta.json.gz"
    if not path.exists():
        print(f"warning: {display_path(path)} is missing; the Storm Desk renders without stats or "
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


def problems(posts, errors, meta, tools=(), papers=()):
    """Every warning about the posts, tools and papers, as 'content/<kind>/x.md: message' lines (a
    paper's are 'content/papers/<slug>/paper.md: message'). Papers are checked with their compile
    result (paper.pdf) when they've been compiled."""
    out = [f"{e} (skipped)" for e in errors]
    slugs = {t.slug for t in tools}
    for p in posts:
        out += [f"content/posts/{p.slug}.md: {w}" for w in content.check(p, list(SECTIONS), meta, slugs)]
    for t in tools:
        out += [f"content/tools/{t.slug}.md: {w}" for w in toolkit.check(t, meta)]
    for p in papers:
        out += [f"{paperkit.where(p.folder)}: {w}" for w in paperkit.check(p, list(SECTIONS), slugs, meta)]
    return out


def visible_papers(drafts=False):
    """-> (papers, errors): papers to render, newest first; drafts only for a preview build."""
    found, errors = paperkit.load_papers()
    return paperkit.newest_first(p for p in found if drafts or not p.draft), errors


def compile_papers(papers, quiet=False):
    """Compile `papers` (scripts/build_papers.py; cached) and set each one's .pdf result."""
    return build_papers.build(papers, quiet=quiet)


def visible_tools(drafts=False):
    """-> (tools, errors): tools to render, in display order; drafts only for a preview build."""
    found, errors = toolkit.load_tools()
    return toolkit.ordered(t for t in found if drafts or not t.draft), errors


def section_href(slug):
    """Path of a section's page: the storms section is the Storm Desk."""
    return "/storms/" if slug == "storms" else f"/section/{slug}/"


def section_label(slug):
    return SECTIONS[slug]["label"] if slug in SECTIONS else slug


# ---------------------------------------------------------------- link previews (docs/SHARING.md)

def site_image():
    return dict(url=f"{ABS}/static/og/site.png", width=1200, height=630,
                alt=f"{SITE['name']} {SITE['tagline']}")


def share_image(item, kicker, card, cards, out_cards):
    """og:image for a post or tool, first match wins: its image: (content/images/ or https://), its
    YouTube video's thumbnail, a title card (drawn into out_cards[card]), else the site card."""
    if item.image.startswith("https://"):
        return dict(url=item.image, alt=item.title)
    path = sharing.local_image(item.image) if item.image else None
    if path and path.is_file() and path.suffix.lower() in sharing.IMAGE_TYPES and (dims := sharing.image_size(path)):
        rel = path.relative_to(sharing.IMAGES.resolve()).as_posix()
        return dict(url=f"{ABS}/images/{quote(rel)}", width=dims[0], height=dims[1], alt=item.title)
    if vid := sharing.youtube_id(getattr(item, "video", "")):
        return dict(url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", width=480, height=360,
                    alt=f"Video: {item.title}")
    png = cards.title(item.title, kicker, HOST, item.summary)
    if png is None:  # nothing in the title a font can draw (all emoji, say)
        return site_image()
    assert card not in out_cards, f"two share cards named {card}"
    out_cards[card] = png
    return dict(url=f"{ABS}/static/og/{card}", width=1200, height=630, alt=item.title)


def post_card(slug):
    """A post's title-card file name in static/og. Tools own tool-*.png, papers paper-*.png and the site
    owns site.png, so a post whose own name would start with tool-, paper- or post-, or be site, gets
    post-<slug>.png instead."""
    if slug == "site" or slug.startswith(("tool-", "paper-", "post-")):
        return f"post-{slug}.png"
    return f"{slug}.png"


def page_share(path, title, description, image=None, kind="website", published=None, section=None,
               canonical=True):
    """Everything base.html puts in a page's head for link previews. path: the page's path under base,
    or None for a page with no URL of its own (no og:url, so scrapers keep the URL they fetched)."""
    return dict(url=ABS + path if path is not None else None, canonical=canonical, title=title, description=sharing.describe(description),
                image=image or site_image(), type=kind, published=published, section=section)


# ---------------------------------------------------------------- feed + sitemap

CHART_SIZES = {"years": "per year", "types": "by event type", "states": "by state", "months": "by month"}
METRIC_NAMES = {"events": "storm events", "deaths": "deaths", "injuries": "injuries", "damage": "damage"}
FIGURE = re.compile(r'(?:<p>\s*)?<figure class="(storm-chart|then-now)"([^>]*)>\s*</figure>(?:\s*</p>)?')
DATA_ATTR = re.compile(r'data-([\w-]+)="([^"]*)"')
LINK_ATTR = re.compile(r'\b(href|src)="([^"]*)"')
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
NOT_XML = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def figure_label(kind, attrs):
    """What a chart shows, in words, for readers who can't run it (feed readers)."""
    if kind == "storm-chart":
        if attrs.get("title"):
            return attrs["title"]
        metric = METRIC_NAMES.get(attrs.get("metric", "events"), attrs.get("metric", "events"))
        text = f"{metric[0].upper()}{metric[1:]} {CHART_SIZES.get(attrs.get('chart', 'years'), '')}".strip()
        if attrs.get("event-type"):
            text += " for " + ", ".join(t.strip() for t in attrs["event-type"].split(","))
        if attrs.get("state"):
            text += f" in {attrs['state']}"
        a, b = attrs.get("year-from"), attrs.get("year-to")
        if a or b:
            text += f", {a}–{b}" if a and b else f", from {a}" if a else f", through {b}"
        return text
    metric = METRIC_NAMES.get(attrs.get("metric", "events"), attrs.get("metric", "events"))
    era = lambda v: (v or "").replace("-", "–")  # noqa: E731
    return (f"Then & Now, {metric} per year, {era(attrs.get('then'))} vs {era(attrs.get('now'))}"
            + (f", {attrs['state']}" if attrs.get("state") else ""))


def feed_html(post):
    """A post's HTML as a feed reader should get it: every link and image absolute, the charts (drawn
    by JavaScript, so empty there) as a link to the post, and its video as a link at the top."""
    permalink = f"{ABS}/post/{post.slug}/"

    def absolute(m):
        url = html.unescape(m.group(2))
        if not SCHEME.match(url):
            url = urljoin(permalink, url)
        return f'{m.group(1)}="{html.escape(url)}"'

    def figure(m):
        attrs = {k: html.unescape(v) for k, v in DATA_ATTR.findall(m.group(2))}
        label = html.escape(figure_label(m.group(1), attrs))
        return (f'<p><a href="{permalink}">Interactive chart: {label} — view it on '
                f'{html.escape(SITE["name"])} →</a></p>')

    body = LINK_ATTR.sub(absolute, post.html(BASE))
    body = FIGURE.sub(figure, body)
    if post.video:
        body = f'<p><a href="{html.escape(post.video)}">Watch the video →</a></p>\n' + body
    return body


def _x(text):
    return xml_escape(NOT_XML.sub("", str(text)))


def paper_feed_html(paper):
    """A paper in the feed: its abstract, its Markdown body (if any), and a link to the PDF."""
    page = f"{ABS}/papers/{paper.slug}/"

    def absolute(m):
        url = html.unescape(m.group(2))
        if not SCHEME.match(url):
            url = urljoin(page, url)
        return f'{m.group(1)}="{html.escape(url)}"'

    body = f"<p>{html.escape(paper.summary)}</p>\n" if paper.summary else ""
    if paper.body_md:
        chart = f'<p><a href="{page}">Interactive chart — view it on {html.escape(SITE["name"])} →</a></p>'
        body += FIGURE.sub(lambda m: chart, LINK_ATTR.sub(absolute, paper.html(BASE)))
    size = f" ({paper.pdf.pages_label}, {paper.pdf.size_label})" if paper.pdf and paper.pdf.ok else ""
    body += (f'\n<p><a href="{page}{quote(paper.pdf_name)}">Read the paper (PDF){size}</a> · '
             f'<a href="{page}">About this paper →</a></p>')
    return body


def feed_xml(posts, papers=()):
    """Atom 1.0: the newest published posts and papers (drafts never, even in a --drafts build)."""
    entries = [p for p in posts if not p.draft] + [p for p in papers if not p.draft and p.pdf and p.pdf.ok]
    entries = sorted(entries, key=lambda e: e.date, reverse=True)[:FEED_SIZE]
    stamp = lambda d: f"{d.isoformat()}T00:00:00Z"  # noqa: E731
    updated = stamp(max(p.date for p in entries)) if entries else "1970-01-01T00:00:00Z"
    author = f"<author><name>{_x(SITE.get('author', SITE['name']))}</name></author>"
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
           f"  <title>{_x(SITE['name'])}</title>",
           f"  <subtitle>{_x(SITE['tagline'])}</subtitle>",
           f"  <id>{_x(ABS)}/</id>",
           f'  <link rel="alternate" type="text/html" href={quoteattr(ABS + "/")}/>',
           f'  <link rel="self" type="application/atom+xml" href={quoteattr(ABS + "/feed.xml")}/>',
           f"  <updated>{updated}</updated>",
           f"  {author}",
           f"  <icon>{_x(ABS)}/static/favicon.svg</icon>"]
    for p in entries:
        is_paper = isinstance(p, paperkit.Paper)
        link = f"{ABS}/papers/{p.slug}/" if is_paper else f"{ABS}/post/{p.slug}/"
        category = ('<category term="paper" label="Paper"/>' if is_paper else
                    f"<category term={quoteattr(p.section)} label={quoteattr(section_label(p.section))}/>")
        out += ["  <entry>",
                f'    <title type="text">{_x(p.title)}</title>',
                f"    <id>{_x(link)}</id>",
                f'    <link rel="alternate" type="text/html" href={quoteattr(link)}/>',
                f"    <published>{stamp(p.date)}</published>",
                f"    <updated>{stamp(p.date)}</updated>",
                f"    {author}",
                f"    {category}"]
        if p.summary:
            out.append(f'    <summary type="text">{_x(p.summary)}</summary>')
        out += [f'    <content type="html">{_x(paper_feed_html(p) if is_paper else feed_html(p))}</content>',
                "  </entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


def sitemap_xml(posts, tools, papers=()):
    """Every published page (no drafts, no event-page shell, no 404), with the post date where known."""
    posts = [p for p in posts if not p.draft]
    papers = [p for p in papers if not p.draft and p.pdf and p.pdf.ok]
    newest = lambda ps: max((p.date for p in ps), default=None)  # noqa: E731
    urls = [("/", newest(posts))]
    urls += [(section_href(slug), newest([p for p in posts if p.section == slug])) for slug in SECTIONS]
    urls += [(f"/post/{p.slug}/", p.date) for p in posts]
    urls += [("/storms/then-and-now/", None), ("/tools/", None)]
    urls += [(f"/tools/{t.slug}/", None) for t in tools if not t.draft]
    urls += [("/papers/", max((p.date for p in papers), default=None))]
    urls += [(f"/papers/{p.slug}/", p.date) for p in papers]
    urls += [("/about/", None)]
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, when in dict.fromkeys(urls):
        out.append(f"  <url><loc>{_x(ABS + path)}</loc>" + (f"<lastmod>{when}</lastmod>" if when else "")
                   + "</url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def bibtex(paper):
    """A BibTeX entry for citing a paper: author (site.toml), title, year, month, url."""
    def esc(text):
        return paperkit.tex_escape(" ".join(text.split()))

    author = SITE.get("author") or SITE["name"]
    word = next((w for w in re.findall(r"[a-z0-9]+", paper.title.lower())
                 if w not in ("a", "an", "the", "on", "of", "in", "and", "for", "to")), "paper")
    surname = re.sub(r"[^a-z0-9]", "", author.split()[-1].lower()) or "whatworks"
    url = f"{ABS}/papers/{paper.slug}/"
    fields = [("author", "{" + esc(author) + "}"), ("title", "{{" + esc(paper.title) + "}}"),
              ("year", f"{{{paper.date.year}}}"), ("month", MONTHS[paper.date.month - 1]),
              ("howpublished", "{" + esc(SITE["name"]) + "}"), ("url", "{" + url + "}")]
    width = max(len(k) for k, _ in fields)
    return (f"@misc{{{surname}{paper.date.year}{word},\n"
            + ",\n".join(f"  {k.ljust(width)} = {v}" for k, v in fields) + "\n}")


def build(drafts=False, report=True):
    """Render the site; report=False leaves printing post warnings to the caller (publish.py)."""
    env = environment()
    found, errors = content.load_posts()
    posts = sorted((p for p in found if drafts or not p.draft), key=lambda p: p.date, reverse=True)
    tools, tool_errors = visible_tools(drafts)
    papers, paper_errors = visible_papers(drafts)
    compile_papers(papers, quiet=not report)
    meta = load_meta()
    if report:
        for line in problems(posts, errors + tool_errors + paper_errors, meta, tools, papers):
            print(f"warning: {line}", file=sys.stderr)
    # A paper LaTeX couldn't compile has no PDF: a published build leaves it out (publish.py stops on
    # it before that matters); a preview shows its page with the error, so it can be fixed there.
    papers = [p for p in papers if p.pdf.ok or drafts]
    if not SITE_URL.startswith(("https://", "http://")):
        sys.exit('error: site.toml needs site_url, the address the site is served from, e.g. '
                 'site_url = "https://castor-o7.github.io" (link previews and the feed need full URLs)')
    env.globals["tool_map"] = {t.slug: t for t in tools}  # for "Built with" links on posts and papers
    pages = {}  # output path under _site -> (template, context)
    cards, out_cards = sharing.Cards(CARD_CACHE), {}  # share cards: file name in static/og -> cached PNG
    out_cards["site.png"] = cards.site(SITE["tagline"], HOST)
    name, tagline = SITE["name"], SITE["tagline"]

    # Page URLs end in "/", so each is a directory with an index.html (Pages serves those as-is).
    pages["index.html"] = ("home.html", dict(
        lead=posts[0] if posts else None, recent=posts[1:7], videos=[p for p in posts if p.video][:3],
        tools=tools, papers=papers[:4], share=page_share("/", name, tagline)))
    for slug, s in SECTIONS.items():
        if slug != "storms":  # that section is the Storm Desk at /storms/
            pages[f"section/{slug}/index.html"] = ("section.html", dict(
                section=s, posts=[p for p in posts if p.section == slug],
                papers=[p for p in papers if p.section == slug],
                share=page_share(section_href(slug), f"{s['label']} — {name}", s["blurb"])))
    for p in posts:
        related = [x for x in posts if x.section == p.section and x.slug != p.slug][:3]
        card = post_card(p.slug)
        image = share_image(p, section_label(p.section), card, cards, out_cards)
        pages[f"post/{p.slug}/index.html"] = ("post.html", dict(post=p, related=related, share=page_share(
            f"/post/{p.slug}/", p.title, p.summary or tagline, image, kind="article",
            published=p.date.isoformat(), section=section_label(p.section))))
    pages["storms/index.html"] = ("storms.html", dict(
        posts=[p for p in posts if p.section == "storms"], storm_ok=meta is not None, meta=meta,
        share=page_share("/storms/", f"Storm Desk — {name}", SECTIONS.get("storms", {}).get("blurb", tagline))))
    # One shell serves every /storms/event/?id=N and is empty without JavaScript and an id, so it
    # names no canonical URL or og:url (a share keeps its ?id) and isn't indexed.
    pages["storms/event/index.html"] = ("event.html", dict(share=page_share(
        None, f"Storm event — {name}", "One event from NOAA's Storm Events Database, 1950–2024.",
        canonical=False)))
    pages["storms/then-and-now/index.html"] = ("thenandnow.html", dict(
        storm_ok=meta is not None, meta=meta, base_year=cpi_base_year(meta), share=page_share(
            "/storms/then-and-now/", f"Then & Now — {name}",
            "Are storms getting worse, or are we counting more? Compare two eras of NOAA storm records "
            "fairly, and see what the records can't tell us.")))
    pages["tools/index.html"] = ("tools.html", dict(tools=tools, share=page_share(
        "/tools/", f"Tools — {name}", f"Software from {name} that anyone can use.")))
    for t in tools:
        card = f"tool-{t.slug}.png"
        image = share_image(t, "Tools", card, cards, out_cards)
        pages[f"tools/{t.slug}/index.html"] = ("tool.html", dict(
            tool=t, stories=[p for p in posts if p.tool == t.slug], papers=[p for p in papers if p.tool == t.slug],
            share=page_share(f"/tools/{t.slug}/", t.title, t.summary or tagline, image)))
    pages["papers/index.html"] = ("papers.html", dict(papers=papers, share=page_share(
        "/papers/", f"Papers — {name}", f"Research papers from {name}, free to read and download as PDFs.")))
    for p in papers:
        image = share_image(p, "Paper", f"paper-{p.slug}.png", cards, out_cards)
        pages[f"papers/{p.slug}/index.html"] = ("paper.html", dict(
            paper=p, bibtex=bibtex(p), share=page_share(
                f"/papers/{p.slug}/", p.title, p.summary or tagline, image, kind="article",
                published=p.date.isoformat(), section="Papers")))
    pages["about/index.html"] = ("about.html", dict(share=page_share("/about/", f"About {name}", tagline)))
    # Served for every missing path, so it names no canonical URL of its own.
    pages["404.html"] = ("404.html", dict(share=page_share("/", f"Page not found — {name}", tagline,
                                                           canonical=False)))

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
    (OUT / "static" / "og").mkdir()
    for card, png in out_cards.items():
        shutil.copyfile(png, OUT / "static" / "og" / card)
    cards.prune()
    # Images from content/images/ that a rendered post or tool uses (its image:, or /images/... in its
    # text). Only those: an image just a draft uses stays off the live site, like the draft.
    for item in [*posts, *tools, *papers]:
        for rel in sharing.referenced_images(item.image, content.COMMENT.sub("", item.body_md)):
            src = sharing.IMAGES / rel
            if src.is_file():
                (OUT / "images" / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, OUT / "images" / rel)
    for p in papers:  # each compiled paper's PDF, from the cache in .cache/papers/
        if p.pdf.ok:
            shutil.copyfile(p.pdf.pdf, OUT / "papers" / p.slug / p.pdf_name)
    (OUT / "feed.xml").write_text(feed_xml(posts, papers), encoding="utf-8")
    (OUT / "sitemap.xml").write_text(sitemap_xml(posts, tools, papers), encoding="utf-8")
    (OUT / ".nojekyll").write_text("")  # serve files as-is; no Jekyll processing
    shown = [p for p in posts if p.draft] + [t for t in tools if t.draft] + [p for p in papers if p.draft]
    if shown:
        # ci_publish.py refuses to publish while this marker exists, so drafts never go live by accident.
        (OUT / DRAFTS_MARKER).write_text("".join(f"{p.slug}\n" for p in shown))
    pdfs = sum(1 for p in papers if p.pdf.ok)
    print(f"built {len(pages)} pages, feed, sitemap + static into {display_path(OUT)}/ (base {BASE or '/'};"
          f" {len(out_cards)} share cards, {cards.drawn} drawn" + (f"; {pdfs} paper PDF(s)" if pdfs else "") + ")"
          + (f" — including {len(shown)} draft(s); preview only, rebuild without --drafts to publish"
             if shown else ""))
    return posts


def install_draft_guard():
    """Point git at scripts/git-hooks, whose pre-commit hook refuses a .md file that isn't UTF-8 (it can't
    be checked for drafts) and, while origin is still the public repo, any draft (docs/STUDIO.md)."""
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    try:
        if git("rev-parse", "--show-toplevel").stdout.strip() != str(ROOT.resolve()):
            return  # not a git checkout of this project
        current = git("config", "--get", "core.hooksPath").stdout.strip()
        if current == "scripts/git-hooks":
            return
        if current:
            print(f"note: git's core.hooksPath is already {current!r}, so the commit guard "
                  "(scripts/git-hooks/pre-commit) isn't installed.", file=sys.stderr)
            return
        if git("config", "core.hooksPath", "scripts/git-hooks").returncode == 0:
            print("Installed the commit guard (scripts/git-hooks/pre-commit).")
    except OSError:
        pass  # no git on this machine


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render the site's pages into _site/.")
    ap.add_argument("--drafts", action="store_true", help="also render drafts (local preview; can't be deployed)")
    build(drafts=ap.parse_args().drafts)
