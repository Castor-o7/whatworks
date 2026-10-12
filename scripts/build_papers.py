#!/usr/bin/env python3
"""Compile the LaTeX papers in content/papers/<slug>/ into PDFs (see docs/WRITING.md, "Papers").

    .venv/bin/python scripts/build_papers.py              # published papers
    .venv/bin/python scripts/build_papers.py --drafts     # drafts too
    .venv/bin/python scripts/build_papers.py my-paper     # just these (draft or not)
    .venv/bin/python scripts/build_papers.py --force      # recompile even if nothing changed

scripts/build_site.py calls this for you; run it on its own to see LaTeX errors quickly. Each paper is
compiled with latexmk and its engine (engine: pdflatex | xelatex | lualatex in paper.md) in a fresh copy
of its folder, so stray .aux files can't confuse a build. The result is cached in .cache/papers/ under
a hash of the folder's files + engine + main + date, so an unchanged paper is never compiled twice. A
failure is reused only while the TeX installation is the same (tex_fingerprint), and a missing
package is never cached, so installing it is enough: the next build compiles again.

Safety: LaTeX runs with shell escape off (no \\write18), may only write inside its build folder, and
never reads a latexmkrc (they can run arbitrary code). Each paper gets a time limit (--timeout).
\\today prints the paper's date: line, and the PDF's timestamps come from it too, so the same source
always gives the same PDF.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__":  # run with the project's virtualenv, like the other scripts
    VENV = ROOT / ".venv"
    if (VENV / "bin" / "python").exists() and Path(sys.prefix).resolve() != VENV.resolve():
        os.execv(VENV / "bin" / "python", [str(VENV / "bin" / "python"), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT))
from app import content, papers as paperkit  # noqa: E402

CACHE = ROOT / ".cache" / "papers"
CACHE_VERSION = "1"  # bump to recompile every paper (e.g. when the latexmk command line changes)
TIMEOUT = 300  # seconds per paper; a thesis with biber takes ~40 s
KEEP = 40  # cached results kept (most recently used first)
ENGINE_FLAG = {"pdflatex": "-pdf", "xelatex": "-pdfxe", "lualatex": "-pdflua"}
ENGINE_OPT = {"pdflatex": "-pdflatex", "xelatex": "-xelatex", "lualatex": "-lualatex"}
# Where MacTeX puts TeX, for a terminal or app whose PATH doesn't include it.
TEX_DIRS = ("/Library/TeX/texbin", "/usr/texbin")
# Not part of the paper: build leftovers, editor backups, Finder litter, and latexmk config (which is
# Perl that latexmk would run). They are neither hashed nor copied into the build.
AUX = re.compile(r"\.(aux|log|fls|fdb_latexmk|synctex(\.gz)?|xdv|bcf|run\.xml|blg|toc|lof|lot|out|nav|snm|"
                 r"vrb|bbl-SAVE-ERROR|bcf-SAVE-ERROR|swp|bak)$|~$", re.I)
RC = re.compile(r"^(\.?latexmkrc|latexmkrc\..*)$", re.I)
OUTPUT = re.compile(r"Output written on .*?\((\d+) pages?(?:, (\d+) bytes)?\)", re.S)
MISSING_PACKAGE = "that package isn't installed here"
FILE_LINE = re.compile(r"^(?:\./)?(.+?\.(?:tex|sty|cls|bbl|cfg|def|ltx)):(\d+): (.*)$")


@dataclass
class Result:
    slug: str
    ok: bool
    pages: int = 0
    size: int = 0
    error: str = ""
    warnings: tuple = ()
    cached: bool = False
    seconds: float = 0.0
    pdf: Path = None  # the cached PDF (ok only)

    @property
    def size_label(self):
        if self.size >= 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        return f"{max(1, round(self.size / 1024))} KB"

    @property
    def pages_label(self):
        return f"{self.pages} page{'s' if self.pages != 1 else ''}" if self.pages else ""


def latexmk():
    """latexmk's path, or None when LaTeX isn't installed."""
    found = shutil.which("latexmk")
    if found:
        return found
    for d in TEX_DIRS:
        if os.access(Path(d) / "latexmk", os.X_OK):
            return str(Path(d) / "latexmk")
    return None


def source_files(folder, main):
    """Paths (relative to folder) of the paper's own files, sorted: everything except paper.md (it
    doesn't change the PDF), hidden files, build leftovers, the main file's old PDF, symlinks and
    latexmkrc files."""
    stem_pdf = Path(main).with_suffix(".pdf").as_posix()
    out = []
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if p.is_symlink() or not p.is_file() or any(part.startswith(".") for part in rel.parts):
            continue
        name = rel.as_posix()
        if name == "paper.md" or name == stem_pdf or AUX.search(name) or RC.match(rel.name):
            continue
        out.append(rel)
    return out


def cache_key(paper, files):
    h = hashlib.sha256()
    for part in (CACHE_VERSION, paper.engine, paper.main, paper.date.isoformat()):
        h.update(part.encode() + b"\0")
    for rel in files:
        h.update(rel.as_posix().encode() + b"\0")
        h.update(hashlib.sha256((paper.folder / rel).read_bytes()).digest())
    return h.hexdigest()[:24]


_FINGERPRINTS = {}
_SESSION = {}  # failures not stored on disk (a missing package), so one run doesn't compile them twice


def tex_fingerprint(tex_bin):
    """A hash of the TeX installation: latexmk's real path and the file-name databases (ls-R) of its
    trees, which change when a package is installed or TeX Live is updated. A cached failure is used
    only while this is unchanged, so installing a missing package (locally, or in the workflow's package
    list) makes the next build try again."""
    if tex_bin not in _FINGERPRINTS:
        h = hashlib.sha256(os.path.realpath(tex_bin).encode() + b"\0")
        kpse = Path(tex_bin).parent / "kpsewhich"
        try:
            listed = subprocess.run([str(kpse) if kpse.exists() else "kpsewhich", "-all", "ls-R"],
                                    capture_output=True, text=True, timeout=30).stdout.split()
        except (OSError, subprocess.SubprocessError):
            listed = []
        for db in sorted(listed):
            try:
                h.update(db.encode() + b"\0" + hashlib.sha256(Path(db).read_bytes()).digest())
            except OSError:
                pass
        _FINGERPRINTS[tex_bin] = h.hexdigest()[:16]
    return _FINGERPRINTS[tex_bin]


def tex_env(paper, tex_bin):
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(tex_bin).parent), env.get("PATH", "")])
    noon = datetime(paper.date.year, paper.date.month, paper.date.day, 12, tzinfo=timezone.utc)
    env.update({
        "SOURCE_DATE_EPOCH": str(int(noon.timestamp())),  # PDF dates, and \today = the paper's date
        "FORCE_SOURCE_DATE": "1",
        "shell_escape": "f",  # kpathsea: no \write18, whatever texmf.cnf says
        "openout_any": "p",  # only write files inside the build folder
        "max_print_line": "1000", "error_line": "254", "half_error_line": "238",  # unwrapped log lines
    })
    for k in ("TEXMFOUTPUT", "TEXINPUTS", "LATEXMKRCSYS"):
        env.pop(k, None)
    return env


def command(paper, tex_bin, main_name):
    eng = paper.engine
    flags = "-no-shell-escape -interaction=nonstopmode -halt-on-error -file-line-error"
    return [tex_bin, "-norc", ENGINE_FLAG[eng], f"{ENGINE_OPT[eng]}={eng} {flags} %O %S", main_name]


def _source_line(src_dir, char):
    """'main.tex, line 20' for the first line of a .tex file in src_dir containing `char`, else ''."""
    if src_dir is None:
        return ""
    for f in sorted(Path(src_dir).rglob("*.tex")):
        try:
            for n, text in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if char in text and not text.lstrip().startswith("%"):
                    return f"{f.relative_to(src_dir).as_posix()}, line {n}"
        except OSError:
            pass
    return ""


def _bib_line(line, source):
    """A biber log line, readable: no '[79] Utils.pm:479> ERROR - BibTeX subsystem:' prefix, and the
    temporary copy biber reads (/tmp/.../biber_tmp_*/<hash>.utf8) named as the .bib file it came from."""
    line = re.sub(r"^\[\d+\]\s+\S+:\d+>\s+(?:ERROR|WARN)\s+-\s+(?:BibTeX subsystem:\s*)?", "", line.strip())
    return re.sub(r"\S*biber_tmp_[^/\s]*/\S+?\.utf8", source or "the .bib file", line)


def excerpt(log_text, blg_texts=(), tool_output="", src_dir=None):
    """The readable part of a failed run: each error's message (with its continuation lines), file and
    line, and the source line TeX stopped at; then bibliography errors; else the end of latexmk's output.
    src_dir (the compiled copy of the paper) lets it say where an unsupported character is."""
    lines = log_text.splitlines()
    found, i = [], 0
    while i < len(lines) and len(found) < 3:
        line = lines[i]
        m = FILE_LINE.match(line)
        if m or line.startswith("! "):
            where = f"{Path(m.group(1)).name}, line {m.group(2)}: " if m else ""
            msg = (m.group(3) if m else line[2:]).strip()
            # LaTeX wraps a long message onto indented lines ("   not set up for use with LaTeX.").
            k = i + 1
            while k < len(lines) and lines[k][:1] in (" ", "\t") and lines[k].strip() and not msg.startswith("=="):
                msg += " " + lines[k].strip()
                k += 1
            context = []
            for j in range(i + 1, min(i + 12, len(lines))):
                if re.match(r"l\.\d+ ", lines[j]):
                    shown = lines[j].split(" ", 1)[1].rstrip()
                    after = lines[j + 1].strip().removesuffix("^^M") if j + 1 < len(lines) else ""
                    context.append(f"  at: {shown} <-- here" + (f" {after}" if after else ""))
                    if not m:
                        where = f"line {lines[j][2:].split(' ', 1)[0]}: "
                    i = j
                    break
                if lines[j].startswith(("! ", "Type ", "See the ", "Here is how")) or FILE_LINE.match(lines[j]):
                    break
            if m2 := re.match(r"LaTeX Error: File [`'](.+?)' not found", msg):
                msg += (" Check the spelling, or put the file in the paper's folder" if not
                        m2.group(1).endswith((".sty", ".cls")) else
                        " Check the spelling; if it's right, " + MISSING_PACKAGE + " (install the TeX "
                        "package that has it: on a Mac, sudo tlmgr install <package>; on GitHub, add it to "
                        "packages: in .github/workflows/publish.yml), then build again")
            elif m2 := re.search(r"Unicode character (.) \(U\+[0-9A-F]+\)", msg):
                at = _source_line(src_dir, m2.group(1))
                msg += ((f" It's on {at}" + (f" (line {m.group(2)} is just where LaTeX ran into it)"
                                             if m and not at.endswith(f"line {m.group(2)}") else "") + ".")
                        if at else "") + (" pdflatex can't print it: put engine: xelatex (or lualatex) in "
                                          "paper.md, or write it as a LaTeX command (e.g. ≥ is $\\geq$).")
            elif msg.startswith(("File ended while scanning use of", "Paragraph ended before")):
                runaway = ""
                if i >= 2 and lines[i - 2].startswith("Runaway argument"):
                    runaway = lines[i - 1].strip()
                    runaway = runaway[:70] + ("..." if len(runaway) > 70 else "")
                msg += (" A { has no matching } (or a command's argument isn't closed)"
                        + (f"; the unclosed part starts: {runaway}" if runaway else "."))
            if msg == "Emergency stop.":
                if found:
                    msg = ""  # just the consequence of the error already reported
                else:
                    star = next((lines[j].strip() for j in range(i + 1, min(i + 8, len(lines)))
                                 if lines[j].startswith("*** (")), "")
                    msg = ("TeX stopped early (Emergency stop): "
                           + ("the file ended without \\end{document}" if "no legal \\end found" in star else
                              "usually a missing \\end{document} or a file it couldn't find")
                           + (f" {star}" if star else ""))
            if msg.startswith("==> Fatal error"):
                pass  # just the consequence of the error already reported
            elif msg:
                found.append(where + msg + ("\n" + "\n".join(context) if context else ""))
        i += 1
    if not found and "Emergency stop" in log_text:
        found.append("TeX stopped early (Emergency stop): usually a missing \\end{document} or a file it "
                     "couldn't find")
    for text in blg_texts:
        source = None
        for line in text.splitlines():
            if m := re.search(r"Found BibTeX data source '([^']+)'", line):
                source = Path(m.group(1)).name
            if re.search(r"\bERROR\b|I couldn't open|I found no|Illegal|---line \d+", line):
                found.append("bibliography: " + _bib_line(line, source))
            elif re.search(r"\bWARN\b.*BibTeX subsystem", line):  # often points at the real mistake
                found.append("bibliography (warning): " + _bib_line(line, source))
            if len(found) >= 5:
                break
    if not found:
        tail = [ln for ln in tool_output.splitlines() if ln.strip()][-12:]
        found.append("\n".join(tail) or "LaTeX failed without saying why")
    return "\n".join(dict.fromkeys(found))


def log_warnings(log_text):
    """Undefined citations and references (they print as [?] and ?? in the PDF)."""
    missing = re.findall(r"Package biblatex Warning: The following entry could not be found\s+\(biblatex\)\s+in the "
                         r"database:\s+\(biblatex\)\s+(\S+)", log_text)
    out = [f"citation '{key}' isn't in the .bib file (it shows as [?])" for key in missing]
    for m in re.finditer(r"(Citation|Reference) [`']([^']*)' on page (\d+) undefined", log_text):
        if m.group(1) == "Citation" and m.group(2) in missing:
            continue
        out.append(f"{m.group(1).lower()} '{m.group(2)}' is undefined (it shows as "
                   f"{'[?]' if m.group(1) == 'Citation' else '??'} on page {m.group(3)})")
    return tuple(dict.fromkeys(out))


def count_pages(pdf: Path):
    """Fallback page count: the /Count of the page tree with the biggest number (no PDF library)."""
    counts = [int(n) for n in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", pdf.read_bytes())]
    counts += [int(n) for n in re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", pdf.read_bytes())]
    return max(counts, default=0)


def _load(entry: Path, slug, tex):
    try:
        data = json.loads((entry / "result.json").read_text())
    except (OSError, ValueError):
        return None
    pdf = entry / "paper.pdf"
    if data.get("ok") and not pdf.is_file():
        return None
    if not data.get("ok") and data.get("tex") != tex:  # a failure from another TeX installation: retry
        return None
    os.utime(entry)  # most recently used survives prune()
    return Result(slug=slug, ok=data["ok"], pages=data.get("pages", 0), size=data.get("size", 0),
                  error=data.get("error", ""), warnings=tuple(data.get("warnings", ())), cached=True,
                  pdf=pdf if data.get("ok") else None)


def compile_paper(paper, cache=CACHE, timeout=TIMEOUT, force=False):
    """-> Result for one paper (from the cache when its sources haven't changed)."""
    def fail(message):
        return Result(slug=paper.slug, ok=False, error=message)

    if paper.engine not in paperkit.ENGINES:
        return fail(f"engine: '{paper.engine}' isn't one of: {', '.join(paperkit.ENGINES)}")
    main = paper.main_path()
    if main is None or not main.is_file():
        return fail(f"main: {paper.main} isn't a file in {content._where(paper.folder)}/")
    tex_bin = latexmk()
    if not tex_bin:
        return fail("LaTeX isn't installed here (no latexmk found). On a Mac install MacTeX "
                    "(https://tug.org/mactex/), then open a new terminal.")
    files = source_files(paper.folder, paper.main)
    key = cache_key(paper, files)
    entry = cache / key
    tex = tex_fingerprint(tex_bin)
    if not force and (hit := _SESSION.get((key, tex))):
        return hit
    if not force and entry.is_dir() and (hit := _load(entry, paper.slug, tex)):
        return hit

    (cache / "tmp").mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{paper.slug[:40]}-", dir=cache / "tmp"))
    try:
        src = work / "src"
        for rel in files:
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paper.folder / rel, src / rel)
        main_rel = Path(paper.main)
        cwd = src / main_rel.parent
        start = time.monotonic()
        proc = subprocess.Popen(command(paper, tex_bin, main_rel.name), cwd=cwd, env=tex_env(paper, tex_bin),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            output = proc.communicate(timeout=timeout)[0].decode("utf-8", "replace")
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)  # latexmk and the engine / biber it started
            output = proc.communicate()[0].decode("utf-8", "replace")
            timed_out = True
        seconds = time.monotonic() - start
        stem = cwd / main_rel.stem
        log = stem.with_suffix(".log")
        log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        pdf = stem.with_suffix(".pdf")
        if timed_out:
            result = fail(f"LaTeX was still running after {timeout} seconds, so it was stopped "
                          "(an endless loop, or a very slow package?)")
        elif proc.returncode != 0 or not pdf.is_file():
            blgs = [p.read_text(encoding="utf-8", errors="replace") for p in cwd.glob("*.blg")]
            result = fail(excerpt(log_text, blgs, output, src))
        else:
            m = OUTPUT.search(log_text)
            pages = int(m.group(1)) if m else 0  # xelatex reports it for the .xdv; same count
            result = Result(slug=paper.slug, ok=True, pages=pages or count_pages(pdf), size=pdf.stat().st_size,
                            warnings=log_warnings(log_text))
        result.seconds = seconds
        if not result.ok and MISSING_PACKAGE in result.error:
            # Fixed by installing something, not by editing the paper: never cached on disk.
            _SESSION[(key, tex)] = Result(slug=paper.slug, ok=False, error=result.error, cached=True)
        elif not timed_out:  # a timeout may be a slow machine; try again next build
            done = work / "entry"
            done.mkdir()
            if result.ok:
                shutil.copyfile(pdf, done / "paper.pdf")
            data = {k: v for k, v in asdict(result).items() if k in ("ok", "pages", "size", "error", "warnings")}
            if not result.ok:
                data["tex"] = tex
            (done / "result.json").write_text(json.dumps(data, indent=1))
            if entry.exists():
                shutil.rmtree(entry, ignore_errors=True)
            try:
                done.rename(entry)
            except OSError:  # another build stored it first
                pass
            if result.ok:
                result.pdf = entry / "paper.pdf"
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prune(cache=CACHE, keep=KEEP):
    """Keep the `keep` most recently used results."""
    if not cache.is_dir():
        return
    entries = sorted((p for p in cache.iterdir() if p.is_dir() and p.name != "tmp"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for old in entries[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def build(papers, cache=CACHE, timeout=TIMEOUT, force=False, quiet=False):
    """Compile `papers` -> {slug: Result}; each paper's .pdf is set to its Result."""
    results = {}
    live = not quiet and sys.stderr.isatty()  # a "compiling..." line that the result replaces
    for p in papers:
        if live:
            print(f"compiling paper {p.slug} ({p.engine})...", file=sys.stderr, flush=True, end="")
        r = compile_paper(p, cache, timeout, force)
        if live:
            print("\r\033[K", file=sys.stderr, end="", flush=True)
        if not quiet:
            if not r.cached:
                state = f"{r.pages_label}, {r.size_label}" if r.ok else "FAILED"
                print(f"compiled paper {p.slug} ({p.engine}) in {r.seconds:.0f} s: {state}", file=sys.stderr)
        p.pdf = results[p.slug] = r
    prune(cache)
    return results


def main():
    ap = argparse.ArgumentParser(description="Compile the papers in content/papers/ into PDFs.")
    ap.add_argument("slugs", nargs="*", help="only these papers (folder names), drafts included")
    ap.add_argument("--drafts", action="store_true", help="compile drafts too")
    ap.add_argument("--force", action="store_true", help="recompile even if a paper hasn't changed")
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help=f"seconds per paper (default {TIMEOUT})")
    args = ap.parse_args()
    found, errors = paperkit.load_papers()
    for e in errors:
        print(f"{'error' if not e.draft else 'warning'}: {e}" + (" (draft skipped)" if e.draft else ""),
              file=sys.stderr)
    if args.slugs:
        unknown = set(args.slugs) - {p.slug for p in found}
        if unknown:
            sys.exit(f"error: no paper named {', '.join(sorted(unknown))} in content/papers/")
        chosen = [p for p in found if p.slug in args.slugs]
    else:
        chosen = [p for p in found if args.drafts or not p.draft]
    if not chosen:
        print("No papers to compile." + ("" if args.drafts else " (Drafts are skipped; add --drafts.)"))
        return 1 if any(not e.draft for e in errors) else 0
    results = build(chosen, timeout=args.timeout, force=args.force)
    failed = 0
    for p in chosen:
        r = results[p.slug]
        tag = " (draft)" if p.draft else ""
        if r.ok:
            print(f"ok      {p.slug}{tag}: {r.pages_label}, {r.size_label}" + (" (cached)" if r.cached else "")
                  + (f" -> {r.pdf.relative_to(ROOT)}" if r.pdf and ROOT in r.pdf.parents else ""))
            for w in r.warnings:
                print(f"        warning: {w}")
        else:
            failed += 1
            print(f"FAILED  {p.slug}{tag} ({content._where(p.folder)}/{p.main}):\n"
                  + "\n".join("        " + line for line in r.error.splitlines()))
    return 1 if failed or any(not e.draft for e in errors) else 0


if __name__ == "__main__":
    sys.exit(main())
