"""The checks that decide whether the site can go live, shared by scripts/publish.py (on your computer)
and scripts/ci_publish.py (on GitHub, which does the deploying). See docs/STUDIO.md.

    from checks import run
    result = run(changed)    # changed: paths under content/ changed since the last deploy (None = all)

What stops a publish:
  - a post, tool or paper that is meant to be live (not a draft) whose front matter can't be read
    (`result.broken`; nothing overrides this);
  - a published paper LaTeX can't compile (`result.failed`; nothing overrides this either: the site
    would silently lose the paper);
  - a warning (template leftovers, a [^ref] with no source, a storm chart it can't make sense of, a
    paper still holding the template's text...) about a published post, tool or paper that changed
    since the last deploy (`result.blocking`; --force, or "[force]" in a commit message, overrides it).
Warnings about published things that didn't change are only mentioned (`result.older`). Drafts never
stop anything: their problems are warnings for the draft preview.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import content, papers as paperkit, tools as toolkit  # noqa: E402
import build_site  # noqa: E402

PAPERS = Path("content/papers")


@dataclass
class Result:
    broken: list = field(default_factory=list)  # unreadable files that aren't drafts (PostError)
    draft_errors: list = field(default_factory=list)  # unreadable drafts: skipped, never blocking
    failed: list = field(default_factory=list)  # warning lines for published papers that didn't compile
    blocking: list = field(default_factory=list)  # warnings on changed published items
    older: list = field(default_factory=list)  # warnings on unchanged published items
    papers: list = field(default_factory=list)  # published papers, compiled

    def hard(self):
        """Problems no --force gets past."""
        return [str(e) for e in self.broken] + self.failed

    def ok(self, force=False):
        return not self.hard() and (force or not self.blocking)


def paper_folder(path):
    """content/papers/<slug>/... -> 'content/papers/<slug>' (None for anything else)."""
    p = Path(path)
    if PAPERS in p.parents and p.parent != PAPERS:
        return (PAPERS / p.relative_to(PAPERS).parts[0]).as_posix()
    return None


def run(changed=None, quiet=True):
    """Check everything meant to be live. `changed` is the set of paths under content/ changed since the
    last deploy, or None when that isn't known (then every published item counts as changed)."""
    r = Result()
    errors = content.load_posts()[1] + toolkit.load_tools()[1] + paperkit.load_papers()[1]
    r.broken = [e for e in errors if not e.draft]
    r.draft_errors = [e for e in errors if e.draft]
    r.papers = build_site.visible_papers()[0]
    build_site.compile_papers(r.papers, quiet=quiet)  # published only; cached, so usually instant
    warnings = build_site.problems(content.all_posts(), [], build_site.load_meta(), build_site.visible_tools()[0],
                                   r.papers)
    failed = {paperkit.where(p.folder) for p in r.papers if not p.pdf.ok}
    changed_papers = None if changed is None else {paper_folder(p) + "/" for p in changed if paper_folder(p)}
    for w in warnings:
        where, _, message = w.partition(": ")
        if where in failed and message.startswith("LaTeX couldn't compile"):
            r.failed.append(w)
        elif (changed is None or where in changed or where in failed
              or any(w.startswith(folder) for folder in changed_papers)):
            r.blocking.append(w)
        else:
            r.older.append(w)
    # A failed paper whose warning line doesn't mention compiling still has no PDF: never let it pass.
    for where in sorted(failed):
        if not any(w.startswith(where + ":") for w in r.failed):
            r.failed.append(f"{where}: LaTeX couldn't compile it")
    return r
