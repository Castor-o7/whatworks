"""Papers live in content/papers/<slug>/: a LaTeX paper published as a PDF with a landing page.

content/papers/<slug>/
  paper.md     front matter + an optional Markdown body shown above the PDF:
      ---
      title: The paper's title
      date: 2026-10-10
      summary: One-paragraph abstract (the landing page, /papers/, the feed and link previews show it).
      tags: group theory, cryptography
      section: science          (optional; the paper is also listed on that section's page)
      tool: storm-desk          (optional; a tool in content/tools/ the paper was built with)
      main: main.tex            (optional; the file LaTeX compiles, default main.tex)
      engine: pdflatex          (optional; pdflatex | xelatex | lualatex, default pdflatex)
      draft: true
      ---
  main.tex     the paper, plus its .bib, figures and so on in the same folder.

scripts/new_paper.py scaffolds one from content/PAPER_TEMPLATE/; scripts/build_papers.py compiles it.
Front matter is read by app/content.py, so drafts fail closed exactly as posts do. A folder without a
readable paper.md is never published.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath

from . import content

PAPERS = content.POSTS.parent / "papers"
TEMPLATE_DIR = content.POSTS.parent / "PAPER_TEMPLATE"
KEYS = ("title", "date", "summary", "tags", "section", "tool", "main", "engine", "draft")
ENGINES = ("pdflatex", "xelatex", "lualatex")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_PDF_BYTES = 20 * 1024 * 1024  # a reader on a phone shouldn't have to download more than this
# The placeholder paragraph in content/PAPER_TEMPLATE/main.tex; a published paper that still has it
# was published by mistake.
TEMPLATE_MARK = "Replace this paragraph"
LATEX_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                 "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def tex_escape(text):
    """Plain text -> LaTeX that prints it as written (for titles in main.tex and BibTeX)."""
    return "".join(LATEX_SPECIAL.get(ch, ch) for ch in text)


@dataclass
class Paper:
    slug: str
    title: str
    date: date
    summary: str = ""
    tags: list = field(default_factory=list)
    section: str = ""
    tool: str = ""
    main: str = "main.tex"
    engine: str = "pdflatex"
    body_md: str = ""
    draft: bool = False
    folder: Path = None
    image: str = ""  # papers have no image: key; share_image() falls back to a title card
    notes: list = field(default_factory=list, repr=False)
    pdf: object = None  # build_papers.Result, set by the build

    def html(self, base=""):
        return content.render(self.body_md, base)

    @property
    def pdf_name(self):
        return f"{self.slug}.pdf"

    def main_path(self):
        """The main .tex file, or None if main: points outside the paper's folder."""
        rel = PurePosixPath(self.main)
        if rel.is_absolute() or ".." in rel.parts or not self.main:
            return None
        return self.folder / rel


def where(folder):
    return content._where(folder / "paper.md")


def parse_text(text, slug, where_, folder=None):
    """A paper from its paper.md text. Raises content.PostError (naming `where_`) when it can't be read."""
    try:
        meta, body, notes = content.front_matter(text, KEYS)
    except ValueError as e:  # fail closed: a draft line that isn't clearly "false" keeps it a draft
        draft = any(content.value(v).lower() not in content.FALSE for v in content.DRAFT_KEY.findall(text))
        raise content.PostError(where_, str(e), draft) from None
    if not meta.get("date"):
        notes.append("no date: line, so it sorts as 1970-01-01")
    try:
        when = date.fromisoformat(meta.get("date") or "1970-01-01")
    except ValueError:
        raise content.PostError(where_, f"date must look like 2026-10-08 (it says {meta['date']!r})",
                                meta["draft"]) from None
    return Paper(
        slug=slug,
        title=meta.get("title") or slug.replace("-", " ").title(),
        date=when,
        summary=meta.get("summary", ""),
        tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        section=meta.get("section", ""),
        tool=meta.get("tool", ""),
        main=meta.get("main") or "main.tex",
        engine=(meta.get("engine") or "pdflatex").lower(),
        body_md=body.strip(),
        draft=meta["draft"],
        folder=folder,
        notes=notes,
    )


def parse(folder: Path) -> Paper:
    """The paper in `folder` (content/papers/<slug>/). A folder with no paper.md can't be published:
    it's reported as a draft that can't be read, so it's skipped with a warning and never goes live."""
    md = folder / "paper.md"
    if not md.is_file():
        raise content.PostError(content._where(folder), "has no paper.md (the front matter that names the "
                                 "paper), so it's skipped; scripts/new_paper.py makes one", True)
    raw = md.read_bytes()
    try:
        text = raw.decode("utf-8")
        if "\0" in text:  # UTF-16 without a byte-order mark (see content.parse)
            raise UnicodeDecodeError("utf-8", raw, 0, 1, "NUL byte")
    except UnicodeDecodeError:
        raise content.PostError(where(folder), "isn't plain UTF-8 text; save it as UTF-8",
                                bool(content.DRAFT_KEY.search(content.loose_text(raw)))) from None
    return parse_text(text, folder.name, where(folder), folder)


def is_draft_text(text, where_="paper.md"):
    """True for a draft paper.md, and for a broken one that may be one (see content.PostError)."""
    try:
        return parse_text(text, "paper", where_).draft
    except content.PostError as e:
        return e.draft


def folders(root=None):
    """Every paper folder under content/papers/ (hidden and _underscore folders are skipped)."""
    root = PAPERS if root is None else root
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def load_papers():
    """-> (papers, errors): every paper, drafts included, plus a PostError for each unreadable one."""
    papers, errors = [], []
    for folder in folders():
        try:
            papers.append(parse(folder))
        except content.PostError as e:
            errors.append(e)
    return papers, errors


def newest_first(papers):
    return sorted(papers, key=lambda p: (p.date, p.title.lower()), reverse=True)


def _template():
    try:
        return parse(TEMPLATE_DIR)
    except (OSError, content.PostError):
        return None


def check(paper, sections=None, tools=None, meta=None):
    """Mistakes worth a warning, as messages. sections: valid section slugs; tools: published tool slugs.
    paper.pdf (a build_papers.Result, when the build compiled it) adds LaTeX failures and size. A paper
    that isn't a draft is also checked for template leftovers."""
    warn = list(paper.notes)
    if not SLUG.fullmatch(paper.slug):
        warn.append(f"the folder name {paper.slug!r} becomes the paper's address: use lowercase letters, "
                    "digits and dashes only (e.g. content/papers/heat-and-the-grid/)")
    if paper.engine not in ENGINES:
        warn.append(f"engine: '{paper.engine}' isn't one of: {', '.join(ENGINES)}"
                    + content._suggest(paper.engine, list(ENGINES)))
    main = paper.main_path()
    if main is None:
        warn.append(f"main: {paper.main!r} must be a file inside the paper's folder (like main.tex)")
    elif not paper.main.endswith(".tex"):
        warn.append(f"main: {paper.main!r} should be the .tex file LaTeX compiles")
    elif paper.folder is not None and not main.is_file():
        found = sorted(p.name for p in paper.folder.glob("*.tex"))
        warn.append(f"main: {paper.main} isn't in the folder" + (f" (it has: {', '.join(found)})" if found
                                                                  else " (there's no .tex file in it)"))
    if paper.section and sections is not None and paper.section not in sections:
        warn.append(f"section '{paper.section}' isn't one of: {', '.join(sections)}"
                    + content._suggest(paper.section, list(sections)))
    if paper.tool and tools is not None and paper.tool not in tools:
        warn.append(f"tool: '{paper.tool}' isn't a published tool" + content._suggest(paper.tool, sorted(tools)))
    if result := paper.pdf:
        if not result.ok:
            warn.append("LaTeX couldn't compile it, so it can't be published until it does:\n"
                        + "\n".join("      " + line for line in result.error.splitlines()))
        else:
            warn += [f"{paper.main}: {w}" for w in result.warnings]  # undefined citations and references
        if result.ok and result.size > MAX_PDF_BYTES:
            warn.append(f"the PDF is {result.size / 1e6:.1f} MB (over {MAX_PDF_BYTES // 2**20} MB); shrink its "
                        "images (export figures as PDF or compressed JPEG) so readers on phones can open it")
    warn += content.check_body(paper.body_md, meta)
    if paper.draft:
        return warn
    template = _template()
    if not paper.summary:
        warn.append("the summary (the abstract shown on /papers/ and in link previews) is empty")
    elif template and paper.summary == template.summary:
        warn.append("the summary is still the template's placeholder")
    if template and paper.title == template.title:
        warn.append(f"the title is still the template's ('{template.title}'): set title: in paper.md")
    if template and paper.date == template.date:
        warn.append(f"the date is still the template's ({template.date}): set date: in paper.md to the day "
                    "you publish")
    if main is not None and main.is_file():
        try:
            tex = main.read_text(encoding="utf-8", errors="replace")
        except OSError:
            tex = ""
        if TEMPLATE_MARK in tex:
            warn.append(f"{paper.main} still has the template's placeholder text ('{TEMPLATE_MARK} ...')")
        for command, word in (("title", "TITLE"), ("author", "AUTHOR")):
            if re.search(rf"\\{command}\s*\{{\s*{word}\s*\}}", tex):
                warn.append(f"{paper.main} still has \\{command}{{{word}}} from the template, so the PDF says "
                            f"'{word}': put the paper's {command} there")
    return warn
