"""Link previews (docs/SHARING.md): share-image title cards drawn with Pillow, preview descriptions, and
the checks for images in content/images/.

Cards are 1200x630 PNGs in the site's light paper style, set in the fonts vendored in app/fonts/
(Fraunces and Source Sans 3, SIL Open Font License). Same input -> same bytes, so a redeploy never
churns git; a card is only drawn again when its text, the fonts, Pillow or this file change (see Cards).
"""
import hashlib
import html
import io
import json
import re
import unicodedata
from pathlib import Path

import PIL
from PIL import Image, ImageDraw, ImageFont, features

FONTS = Path(__file__).resolve().parent / "fonts"
SERIF = FONTS / "fraunces" / "Fraunces[SOFT,WONK,opsz,wght].ttf"
SANS = FONTS / "sourcesans3" / "SourceSans3[wght].ttf"
IMAGES = Path(__file__).resolve().parent.parent / "content" / "images"

W, H = 1200, 630
PAPER, INK, INK_2, INK_3, RULE, ACCENT = "#f7f5f0", "#0b0b0b", "#52514e", "#7a7974", "#dddbd4", "#c2410c"
MARGIN = 80
LAYOUT = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC

# Share images people can put in content/images/ (what Discord, Bluesky, X, Facebook and iMessage all show).
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # X refuses share images over 5 MB; Facebook over 8 MB
MIN_IMAGE_SIDE = 200  # Facebook ignores images smaller than 200x200
# '/images/x.png' (or 'images/x.png') in a Markdown body: an image the post uses.
BODY_IMAGE = re.compile(r"""(?:^|[\s("'=<])/images/([^\s)"'<>?#]+)""")
YOUTUBE_ID = re.compile(r"^[\w-]{6,}$")


# ---------------------------------------------------------------- text

def describe(text, limit=200, is_html=False):
    """Plain text for og:description: whitespace collapsed and cut at a word boundary with an ellipsis
    so it's at most `limit` characters. Summaries, blurbs and the tagline are plain text already (Jinja
    escapes them), so "<video>" stays as written; only is_html=True strips tags and decodes entities."""
    text = text or ""
    if is_html:
        text = html.unescape(re.sub(r"<[^>]*>", " ", text))
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.—–-") + "…"


def youtube_id(url):
    """The video id of a YouTube watch / youtu.be / shorts / live / embed URL, else None."""
    from urllib.parse import parse_qs, urlparse
    u = urlparse(url or "")
    host = u.netloc.lower().removeprefix("www.").removeprefix("m.")
    vid = None
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if u.path.startswith(("/shorts/", "/embed/", "/live/")):
            vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else None
        elif v := parse_qs(u.query).get("v"):
            vid = v[0]
    return vid if vid and YOUTUBE_ID.match(vid) else None


# ---------------------------------------------------------------- content/images

def local_image(name):
    """content/images/<name> for an image: value that isn't a URL; None if it would point outside
    content/images/ (an absolute path or '..')."""
    name = (name or "").strip().removeprefix("/").removeprefix("images/")
    if not name or name.startswith(("http://", "https://", "//")):
        return None
    path = (IMAGES / name).resolve()
    return path if path.is_relative_to(IMAGES.resolve()) else None


def referenced_images(image, body_md):
    """Paths relative to content/images/ that a post or tool uses: its image: and /images/... in its body."""
    names = []
    if image and not image.startswith(("http://", "https://")) and local_image(image):
        names.append(local_image(image).relative_to(IMAGES.resolve()).as_posix())
    for m in BODY_IMAGE.finditer(body_md or ""):
        p = local_image(m.group(1))
        if p:
            names.append(p.relative_to(IMAGES.resolve()).as_posix())
    return list(dict.fromkeys(names))


def image_size(path):
    try:
        with Image.open(path) as im:  # as displayed: EXIF orientations 5-8 turn it on its side
            w, h = im.size
            return (h, w) if im.getexif().get(0x0112) in (5, 6, 7, 8) else (w, h)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def check_image(image, body_md=""):
    """Warnings about an image: value and /images/ links in a body (missing, wrong type, too big)."""
    warn = []
    image = (image or "").strip()
    if image.startswith("http://"):
        warn.append("image: should be an https:// address (link previews skip plain http images)")
    elif image and not image.startswith("https://"):
        path = local_image(image)
        if path is None:
            warn.append(f"image: {image!r} must be a file name in content/images/ (e.g. image: grid-map.png) "
                        "or a full https:// address")
        elif path.suffix.lower() not in IMAGE_TYPES:
            warn.append(f"image: {image!r} is a {path.suffix or 'file without an extension'}; link previews "
                        f"need one of: {', '.join(IMAGE_TYPES)} (so the share card is used instead)")
        elif not path.is_file():
            warn.append(f"image: there's no content/images/{path.name}" + _near(path)
                        + " (so the share card is used instead)")
        else:
            size = path.stat().st_size
            dims = image_size(path)
            if size > MAX_IMAGE_BYTES:
                warn.append(f"image: content/images/{path.name} is {size / 1048576:.1f} MB; keep share images "
                            f"under {MAX_IMAGE_BYTES // 1048576} MB (X and others skip bigger ones). "
                            "1200x630 as a JPEG is ideal")
            if dims is None:
                warn.append(f"image: content/images/{path.name} isn't an image file Pillow can read")
            elif min(dims) < MIN_IMAGE_SIDE:
                warn.append(f"image: content/images/{path.name} is only {dims[0]}x{dims[1]}; previews need at "
                            f"least {MIN_IMAGE_SIDE}x{MIN_IMAGE_SIDE} (1200x630 is ideal)")
    for m in BODY_IMAGE.finditer(body_md or ""):
        path = local_image(m.group(1))
        if path is None or not path.is_file():
            warn.append(f"/images/{m.group(1)} is linked in the text, but there's no content/images/{m.group(1)}")
    return warn


def _near(path):
    import difflib
    names = [p.name for p in IMAGES.glob("*") if p.is_file()] if IMAGES.is_dir() else []
    close = difflib.get_close_matches(path.name, names, 1, 0.6)
    return f" (did you mean {close[0]!r}?)" if close else ""


# ---------------------------------------------------------------- fonts

_fonts = {}


def _font(kind, size, weight):
    key = (kind, size, weight)
    if key not in _fonts:
        f = ImageFont.truetype(str(SERIF if kind == "serif" else SANS), size, layout_engine=LAYOUT)
        if kind == "serif":  # axes: optical size, weight, softness, wonky (the site's Google Fonts defaults)
            f.set_variation_by_axes([max(9, min(144, size)), weight, 0, 1])
        else:
            f.set_variation_by_axes([weight])
        _fonts[key] = f
    return _fonts[key]


_glyphs = {}


def _has_glyph(kind, ch):
    """Whether a font draws `ch` itself (not its empty-box .notdef glyph)."""
    key = (kind, ch)
    if key not in _glyphs:
        f = _font(kind, 48, 700)

        def ink(c):
            im = Image.new("L", (160, 120))
            ImageDraw.Draw(im).text((20, 10), c, font=f, fill=255)
            return im.tobytes()
        _glyphs.setdefault((kind, None), ink("\U0010FFFD"))  # a private-use char no font has: .notdef
        _glyphs[key] = ch.isspace() or ink(ch) != _glyphs[(kind, None)]
    return _glyphs[key]


def clean(text):
    """A title as the card can set it: NFC, no control/format characters, no emoji (or other symbols
    neither font has; their spaces are collapsed), straight quotes turned typographic."""
    out = []
    for ch in unicodedata.normalize("NFC", text or ""):
        cat = unicodedata.category(ch)
        o = ord(ch)
        if cat in ("Zs", "Zl", "Zp") or ch in "\t\n\r":
            out.append(" ")
        elif cat[0] == "C" or 0xFE00 <= o <= 0xFE0F or 0x1F3FB <= o <= 0x1F3FF or 0xE0000 <= o <= 0xE007F:
            continue  # controls, zero-width joiners, variation selectors, skin tones, tag characters
        elif _has_glyph("serif", ch) or _has_glyph("sans", ch):
            out.append(ch)
    text = " ".join("".join(out).split())
    text = re.sub(r"(^|[\s(\[{—–-])\"", "\\1“", text).replace('"', "”")
    text = re.sub(r"(^|[\s(\[{—–-])'", "\\1‘", text).replace("'", "’")
    return text.replace("...", "…")


# ---------------------------------------------------------------- layout

class _Text:
    """Words set in one font (`kind`), falling back to the other for characters only it has."""

    def __init__(self, size, weight, kind="serif"):
        self.size, self.weight, self.kind = size, weight, kind
        self.other = "sans" if kind == "serif" else "serif"
        self.space = _font(kind, size, weight).getlength(" ")

    def runs(self, word):
        runs = []
        for ch in word:
            kind = self.kind if _has_glyph(self.kind, ch) else self.other
            if runs and runs[-1][0] == kind:
                runs[-1][1] += ch
            else:
                runs.append([kind, ch])
        return runs

    def width(self, word):
        return sum(_font(k, self.size, self.weight).getlength(t) for k, t in self.runs(word))

    def draw(self, draw, xy, line, fill):
        x, y = xy
        for i, word in enumerate(line):
            if i:
                x += self.space
            for kind, t in self.runs(word):
                f = _font(kind, self.size, self.weight)
                draw.text((x, y), t, font=f, fill=fill, anchor="ls")
                x += f.getlength(t)


def _split_long(words, text, maxw):
    """Words wider than a line are broken between characters, with a hyphen."""
    out = []
    for w in words:
        while text.width(w) > maxw and len(w) > 1:
            n = len(w) - 1
            while n > 1 and text.width(w[:n] + "-") > maxw:
                n -= 1
            out.append(w[:n] + "-")
            w = w[n:]
        out.append(w)
    return out


def _wrap(words, text, maxw):
    lines, cur, curw = [], [], 0.0
    for w in words:
        ww = text.width(w)
        if cur and curw + text.space + ww > maxw:
            lines.append(cur)
            cur, curw = [], 0.0
        curw = ww if not cur else curw + text.space + ww
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _balanced(words, text, maxw):
    """Greedy wrapping, then the narrowest width that keeps the same number of lines, so the last line
    isn't a lone word (like CSS text-wrap: balance)."""
    lines = _wrap(words, text, maxw)
    if len(lines) < 2:
        return lines
    lo, hi = maxw * 0.4, maxw
    while hi - lo > 2:
        mid = (lo + hi) / 2
        if len(_wrap(words, text, mid)) == len(lines) and all(text.width(w) <= mid for w in words):
            hi = mid
        else:
            lo = mid
    return _wrap(words, text, hi)


def fit(title, box_w, box_h, max_size=96, min_size=40, weight=700, leading=1.1, kind="serif"):
    """-> (_Text, lines, line_height): the largest size (stepping down) whose wrapped title fits the
    box; at the smallest size a title that still doesn't fit is cut with an ellipsis."""
    words = title.split()
    for size in range(max_size, min_size - 1, -2):
        text = _Text(size, weight, kind)
        lh = round(size * leading)
        max_lines = max(1, int((box_h - size) // lh) + 1)
        parts = _split_long(words, text, box_w)
        lines = _wrap(parts, text, box_w)
        if len(lines) <= max_lines:
            return text, _balanced(parts, text, box_w), lh
    lines = lines[:max_lines]
    last = lines[-1]
    while last and text.width(" ".join(last) + "…") > box_w:
        if len(last) > 1:
            last = last[:-1]
        else:
            last = [last[0][:-1]] if len(last[0]) > 1 else []
    lines[-1] = (last[:-1] + [last[-1].rstrip(" ,;:.—–-") + "…"]) if last else ["…"]
    return text, lines, lh


def _tracked(draw, xy, text, font, fill, tracking):
    """Uppercase label with letter-spacing (like the site's .kicker: letter-spacing .1em)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + tracking
    return x - tracking


def _wordmark(draw, xy, size, anchor="ls"):
    """'What Works' in ink with the accent '?', as in the masthead."""
    f = _font("serif", size, 900)
    x, y = xy
    if anchor == "ms":
        x -= f.getlength("What Works?") / 2
    draw.text((x, y), "What Works", font=f, fill=INK, anchor="ls")
    draw.text((x + f.getlength("What Works"), y), "?", font=f, fill=ACCENT, anchor="ls")


def _footer(draw, host):
    draw.line([(MARGIN, 532), (W - MARGIN, 532)], fill=INK, width=2)
    _wordmark(draw, (MARGIN, 586), 40)
    f = _font("sans", 24, 600)
    draw.text((W - MARGIN, 584), host, font=f, fill=INK_3, anchor="rs")


def _canvas():
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=ACCENT)
    return im, d


DEK_SIZE, DEK_LEADING, DEK_GAP = 32, 42, 34


def draw_title_card(title, kicker, host, dek=""):
    """A post's or tool's card: accent kicker, the headline in Fraunces Bold (wrapped, shrunk to fit),
    its summary below when there's room for at least two lines of it, and the wordmark.
    -> PIL image, or None if no character of the title can be set."""
    title = clean(title)
    if not title:
        return None
    im, d = _canvas()
    top, bottom = 70, 500  # the space above the footer rule
    kick_size, gap = 26, 30
    box_h = bottom - top - kick_size - gap
    text, lines, lh = fit(title, W - 2 * MARGIN, box_h)
    block = kick_size + gap + text.size + (len(lines) - 1) * lh
    dek_lines, dek_text = [], None
    room = box_h - (text.size + (len(lines) - 1) * lh) - DEK_GAP  # below the headline
    if clean(dek) and len(lines) <= 2 and room >= DEK_SIZE + DEK_LEADING:
        dek_text, dek_lines, _ = fit(clean(dek), W - 2 * MARGIN - 80, min(room, DEK_SIZE + 2 * DEK_LEADING),
                                     max_size=DEK_SIZE, min_size=DEK_SIZE, weight=400,
                                     leading=DEK_LEADING / DEK_SIZE, kind="sans")
        block += DEK_GAP + DEK_SIZE * 0.2 + len(dek_lines) * DEK_LEADING
    y0 = top + max(0, (bottom - top - block) * 0.45)  # centred, a touch high
    _tracked(d, (MARGIN, y0 + kick_size), clean(kicker).upper(), _font("sans", kick_size, 700), ACCENT,
             kick_size * 0.12)
    base = y0 + kick_size + gap + text.size * 0.82  # baseline of the first line (cap height ~ .7 em)
    for i, line in enumerate(lines):
        text.draw(d, (MARGIN, base + i * lh), line, INK)
    dek_base = base + (len(lines) - 1) * lh + DEK_GAP + DEK_SIZE * 1.1
    for i, line in enumerate(dek_lines):
        dek_text.draw(d, (MARGIN, dek_base + i * DEK_LEADING), line, INK_2)
    _footer(d, host)
    return im


def draw_site_card(tagline, host):
    """The default card: the wordmark big, a double rule, and the tagline."""
    im, d = _canvas()
    _wordmark(d, (W / 2, 300), 132, anchor="ms")
    d.line([(W / 2 - 260, 352), (W / 2 + 260, 352)], fill=INK, width=2)
    d.line([(W / 2 - 260, 358), (W / 2 + 260, 358)], fill=INK, width=2)
    text, lines, lh = fit(clean(tagline), 880, 110, max_size=38, min_size=26, weight=500, leading=1.3)
    for i, line in enumerate(lines):
        w = sum(text.width(x) for x in line) + text.space * (len(line) - 1)
        text.draw(d, ((W - w) / 2, 414 + i * lh), line, INK_2)
    f = _font("sans", 24, 600)
    d.text((W / 2, 584), host, font=f, fill=INK_3, anchor="ms")
    return im


# ---------------------------------------------------------------- cards (cached)

def _fingerprint():
    h = hashlib.sha256()
    for p in (SERIF, SANS, Path(__file__)):
        h.update(p.read_bytes())
    h.update(f"{PIL.__version__} {LAYOUT}".encode())
    return h.hexdigest()


class Cards:
    """Draws cards into a cache folder keyed by everything that affects their pixels (the text, the
    fonts, this file, Pillow's version), so an unchanged card is copied, not drawn again."""

    def __init__(self, cache_dir):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.salt = _fingerprint()
        self.used, self.drawn = set(), 0

    def _get(self, spec, draw):
        key = hashlib.sha256((self.salt + json.dumps(spec, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
        path = self.cache / f"{key[:32]}.png"
        self.used.add(path.name)
        if path.exists():
            path.touch()  # recently used (see prune)
        else:
            im = draw()
            if im is None:
                return None
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)  # Pillow writes no timestamp: same pixels, same bytes
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(buf.getvalue())
            tmp.replace(path)
            self.drawn += 1
        return path

    def title(self, title, kicker, host, dek=""):
        """Path of the cached PNG, or None if the title has nothing a font can draw (use the site card)."""
        if not clean(title):
            return None
        return self._get({"card": "title", "title": title, "kicker": kicker, "host": host, "dek": dek},
                         lambda: draw_title_card(title, kicker, host, dek))

    def site(self, tagline, host):
        return self._get({"card": "site", "tagline": tagline, "host": host},
                         lambda: draw_site_card(tagline, host))

    def prune(self, keep=200):
        """Forget cards no build has used lately: keep this build's plus the newest `keep` others."""
        old = sorted((p for p in self.cache.glob("*.png") if p.name not in self.used),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        for p in old[keep:]:
            p.unlink(missing_ok=True)
