#!/usr/bin/env python3
"""Start a new paper: a draft folder in content/papers/ made from content/PAPER_TEMPLATE/.

    scripts/new_paper.py "Symmetry in everyday cryptography"
    scripts/new_paper.py "Heat and the grid" --engine xelatex --section science --tags "heat, grid"

It creates content/papers/<title-as-url>/ with paper.md (the front matter: title, date, abstract,
draft: true), main.tex (a clean article that compiles as-is, with amsmath, graphicx, hyperref and a
bibliography) and references.bib. Then it compiles the new paper once to prove it builds.
Guide: docs/WRITING.md, "Papers".
"""
import argparse
import os
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
if (VENV / "bin" / "python").exists() and Path(sys.prefix).resolve() != VENV.resolve():
    os.execv(VENV / "bin" / "python", [str(VENV / "bin" / "python"), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import content, papers as paperkit  # noqa: E402
import build_papers  # noqa: E402
import build_site  # noqa: E402
from new_post import quoted, slugify  # noqa: E402

def main():
    ap = argparse.ArgumentParser(description="Start a new draft paper (LaTeX, published as a PDF).")
    ap.add_argument("title", help="the paper's title, in quotes")
    ap.add_argument("--engine", choices=paperkit.ENGINES,
                    help="the LaTeX engine (default pdflatex, or xelatex when the title has characters "
                         "pdflatex can't print; xelatex or lualatex for system fonts / lots of Unicode)")
    ap.add_argument("--section", choices=list(build_site.SECTIONS), help="optional: also list it in this section")
    ap.add_argument("--tags", default="", help="optional comma-separated tags")
    ap.add_argument("--no-compile", action="store_true", help="don't test-compile it")
    args = ap.parse_args()

    title = " ".join(args.title.split())
    if not title:
        raise SystemExit("error: the title is empty")
    # pdflatex prints Latin-1 letters (é, ü) but not most other Unicode (≥, Ω), and the title goes into
    # main.tex, so such a title would fail to compile.
    wide = sorted({ch for ch in title + build_site.SITE.get("author", "") if ord(ch) > 0xFF})
    if args.engine is None:
        args.engine = "xelatex" if wide else "pdflatex"
        if wide:
            print(f"Using xelatex: the title has {' '.join(wide)}, which pdflatex can't print.")
    elif args.engine == "pdflatex" and wide:
        print(f"Note: pdflatex can't print {' '.join(wide)} from the title; if the test compile fails, "
              "use --engine xelatex (or write them as LaTeX commands in main.tex).")
    base = slugify(title).removesuffix("-pdf") or "paper"
    folder, n = paperkit.PAPERS / base, 2
    while folder.exists():  # never overwrite another paper
        folder, n = paperkit.PAPERS / f"{base}-{n}", n + 1

    tpl = paperkit.TEMPLATE_DIR
    if not (tpl / "paper.md").is_file():
        raise SystemExit(f"error: the template {tpl.relative_to(ROOT)}/ is missing")
    shutil.copytree(tpl, folder, ignore=shutil.ignore_patterns(".*", "*~", "*.aux", "*.log"))
    md = folder / "paper.md"
    md.write_text(content.set_fields(md.read_text(encoding="utf-8"), {
        "title": quoted(title), "date": date.today().isoformat(), "engine": args.engine,
        "section": args.section or "", "tags": args.tags.strip(), "draft": "true",
    }), encoding="utf-8")
    tex = folder / "main.tex"
    author = paperkit.tex_escape(build_site.SITE.get("author", ""))
    tex.write_text(tex.read_text(encoding="utf-8")
                   .replace(r"\title{TITLE}", r"\title{" + paperkit.tex_escape(title) + "}", 1)
                   .replace(r"\author{AUTHOR}", r"\author{" + author + "}", 1),
                   encoding="utf-8")
    # Read it back the way the build will: it must be a draft, with the title as typed.
    paper = paperkit.parse(folder)
    if not paper.draft or paper.title != title:
        shutil.rmtree(folder)
        raise SystemExit(f"error: couldn't write a draft for that title (it read back as {paper.title!r}, "
                         f"draft={paper.draft}); nothing was created. Try a simpler title and edit it in the file.")

    rel = folder.relative_to(ROOT)
    print(f"Created {rel}/ (a private draft):")
    print(f"  {rel}/paper.md        title, date, abstract (summary:), draft: true")
    print(f"  {rel}/main.tex        the paper ({args.engine})")
    print(f"  {rel}/references.bib  its sources")
    if not args.no_compile:
        result = build_papers.compile_paper(paper)
        if result.ok:
            print(f"\nTest compile: ok ({result.pages_label}, {result.size_label}).")
        else:
            print("\nTest compile FAILED (the paper was still created):\n"
                  + "\n".join("  " + line for line in result.error.splitlines()))
    print("\nNext:")
    print(f"  1. Write it:   {rel}/main.tex, and the abstract in summary: in paper.md")
    print("  2. Preview:    scripts/preview.py")
    print(f"                 -> http://localhost:8000{build_site.BASE}/papers/{folder.name}/")
    print("  3. Publish:    delete 'draft: true' in paper.md, set date: to the day you publish,")
    print("                 then run scripts/publish.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
