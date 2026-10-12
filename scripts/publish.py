#!/usr/bin/env python3
"""Publish from your computer: check, build, then commit your writing to the studio repo and push it.
GitHub then builds and deploys the site (scripts/ci_publish.py; docs/STUDIO.md), live a few minutes later.

    scripts/publish.py               # do it
    scripts/publish.py --dry-run     # show what would happen, change nothing
    scripts/publish.py --force       # publish even if the checks below find template leftovers etc.

What it does, in order:
  0. Checks what's meant to be live (scripts/checks.py, the same checks GitHub runs). It stops on a
     post, tool or paper that isn't a draft but can't be read, on a published paper LaTeX can't
     compile, and, unless you pass --force, on template leftovers (the placeholder summary, empty
     headings, a [^ref] with no source) or a storm chart it can't make sense of in a post, tool or
     paper you changed. For a post going live for the first time, it offers to change its date to today.
  1. Builds the site WITHOUT drafts into _site/, as a last look (scripts/build_site.py). Nothing is
     deployed from your computer: GitHub does that, so there's only ever one writer of the live site.
  2. Commits everything in content/, drafts included (the studio repo is private; .gitignore keeps out
     editor backups and LaTeX leftovers), and pushes it to the studio repo's main branch. With --force
     the commit message gets a line "[force]", which tells GitHub to publish despite the warnings.
Code changes outside content/ are left for you to commit yourself. If GitHub has commits this computer
doesn't (made in the browser), it stops before committing and says to run `git pull --rebase --autostash`.

Until scripts/setup_studio.sh has moved `origin` to the private studio repo, this refuses to commit:
origin would still be the public repo, and drafts would be published to it.
"""
import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Run with the project's virtualenv (it has jinja2 + markdown) even when started as scripts/<name>.py.
VENV = ROOT / ".venv"
if (VENV / "bin" / "python").exists() and Path(sys.prefix).resolve() != VENV.resolve():
    os.execv(VENV / "bin" / "python", [str(VENV / "bin" / "python"), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import content, papers as paperkit, tools as toolkit  # noqa: E402
import build_site  # noqa: E402
import checks  # noqa: E402
import repos  # noqa: E402


PULL = "git pull --rebase --autostash"  # puts your commits on top of GitHub's; keeps uncommitted code changes


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=check, capture_output=True, text=True)


def changed_paths():
    """Paths under content/ that differ from what GitHub last got (the upstream branch, else the last
    commit): committed-but-unpushed, uncommitted and new files alike. Both sides of a rename count."""
    base = "@{upstream}" if git("rev-parse", "--verify", "--quiet", "@{upstream}", check=False).returncode == 0 \
        else "HEAD"
    if git("rev-parse", "--verify", "--quiet", base, check=False).returncode:
        return None  # no commits yet: everything is new
    tracked = git("diff", "--name-only", "-z", "--no-renames", base, "--", "content").stdout
    untracked = git("ls-files", "--others", "--exclude-standard", "-z", "--", "content").stdout
    return {p for p in (tracked + untracked).split("\0") if p}


def head_text(path):
    """The file as of the last commit, or None if it isn't there."""
    shown = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{path}"], capture_output=True)
    return content.loose_text(shown.stdout) if shown.returncode == 0 else None


def item_at(path):
    """(kind, item) for a post, tool or paper.md path that exists and can be read, else None."""
    p = Path(path)
    try:
        if p.parent == Path("content/posts") and p.suffix == ".md":
            return "post", content.parse(ROOT / p)
        if p.parent == Path("content/tools") and p.suffix == ".md":
            return "tool", toolkit.parse(ROOT / p)
        if p.name == "paper.md" and checks.paper_folder(path) and p.parent.as_posix() == checks.paper_folder(path):
            return "paper", paperkit.parse(ROOT / p.parent)
    except (OSError, content.PostError):
        return None
    return None


def was_live(path, kind):
    """Was this file live (committed and not a draft) as of the last commit?"""
    old = head_text(path)
    if old is None:
        return False
    if kind == "paper":
        return not paperkit.is_draft_text(old, path)
    if kind == "tool":
        try:
            return not toolkit.parse_text(old, Path(path).stem, path).draft
        except content.PostError as e:
            return not e.draft
    return not content.is_draft(old, path)


def offer_today(path, post, dry_run):
    """A new post keeps the date its draft was started; offer to change it to today."""
    today = date.today()
    if post.date == today:
        return
    print(f"  It's dated {post.date}, not today (a draft keeps the date it was started).")
    if dry_run or not sys.stdin.isatty():
        print(f"  To date it today, change its date: line to {today}.")
        return
    try:
        answer = input(f"  Change its date to today ({today})? [Y/n] ").strip().lower()
    except EOFError:
        answer = "n"
    if answer in ("", "y", "yes"):
        p = ROOT / path
        p.write_text(content.set_fields(p.read_text(encoding="utf-8"), {"date": today.isoformat()}),
                     encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Check, build, and push your writing to the studio repo.")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen without committing or pushing")
    ap.add_argument("--force", action="store_true", help="publish even with warnings (template leftovers etc.)")
    ap.add_argument("-m", "--message", help="commit message (default lists what goes live)")
    args = ap.parse_args()
    if not args.dry_run:
        build_site.install_draft_guard()
    public_origin = repos.origin_is_public()
    if public_origin:
        print(f"Note: origin is still the public repo ({repos.PUBLIC}). Committing here would publish your\n"
              "drafts, so publish.py only commits once scripts/setup_studio.sh has moved origin to the\n"
              f"private studio repo ({repos.STUDIO}). See docs/STUDIO.md.", file=sys.stderr)
        if not args.dry_run:
            return 1

    # Commits made in the browser (github.dev) are on GitHub but not here yet: committing on top of an
    # old main would make the push fail, so stop before changing anything.
    if not public_origin:
        fetched = git("fetch", "--quiet", "origin", check=False)
        if fetched.returncode:
            print("note: couldn't reach GitHub to check for newer commits (offline?):\n  "
                  + fetched.stderr.strip(), file=sys.stderr)
        behind = git("rev-list", "--count", "HEAD..@{upstream}", check=False)
        if behind.returncode == 0 and behind.stdout.strip() not in ("", "0"):
            print(f"GitHub has {behind.stdout.strip()} commit(s) you don't have here (from the browser?). "
                  f"Get them first:\n  {PULL}\nthen run scripts/publish.py again.", file=sys.stderr)
            if not args.dry_run:
                return 1

    changed = changed_paths()
    status = git("status", "--porcelain", "--untracked-files=all", "--", "content").stdout.splitlines()
    new = []
    for path in sorted(changed or []):
        found = item_at(path)
        if found and not found[1].draft and not was_live(path, found[0]):
            new.append((path, *found))
    if new:
        print("Going live for the first time:")
        for path, kind, item in new:
            where = checks.paper_folder(path) + "/" if kind == "paper" else path
            print(f"  {item.title}  ({where}, {kind}" + (f", dated {item.date})" if kind != "tool" else ")"))
            if kind == "post":
                offer_today(path, item, args.dry_run)

    # 0. The same checks GitHub runs before it deploys.
    r = checks.run(changed)
    for e in r.draft_errors:
        print(f"warning: {e} (draft skipped)", file=sys.stderr)
    if r.older:
        print("\nNotes on things already live (fix when you can):\n  " + "\n  ".join(r.older))
    if r.hard():
        print("\nFix these first (or add 'draft: true' to keep one private). Nothing was published:\n  "
              + "\n  ".join(r.hard()), file=sys.stderr)
        if not args.dry_run:
            return 1
    if r.blocking:
        print("\nCheck these before publishing:\n  " + "\n  ".join(r.blocking))
        if not args.force:
            print("Fix them and run publish.py again, or run 'scripts/publish.py --force' to publish anyway."
                  + ("" if not args.dry_run else "\n(Dry run: a real publish would stop here.)"))
            if not args.dry_run:
                return 1

    # 1. A last look at exactly what readers will see.
    posts = build_site.build(drafts=False, report=False)
    drafts = [p.slug for p in content.all_posts(drafts=True) if p.draft]
    drafts += [t.slug for t in toolkit.load_tools()[0] if t.draft]
    drafts += [p.slug for p in paperkit.load_papers()[0] if p.draft]
    print(f"\n{len(posts)} published post(s)" + (f" and {len(r.papers)} paper(s)" if r.papers else "")
          + " will be live.")
    if drafts:
        print(f"{len(drafts)} draft(s) are saved to the studio repo but stay off the site: " + ", ".join(drafts))

    titles = [item.title for path, kind, item in new]
    titles += [found[1].title for path in sorted(changed or []) if (found := item_at(path)) and not found[1].draft
               and path not in {n[0] for n in new}]
    message = args.message or ("Publish: " + "; ".join(titles) if titles else "Update content")
    if args.force and r.blocking:
        message += "\n\n[force]"
    print("Will commit: " + (", ".join(line[3:] for line in status) if status else "nothing new in content/"))
    if args.dry_run:
        print("\nDry run: nothing committed or pushed.")
        return 0

    # 2. Commit all of content/ (drafts too: the studio repo is private) and push.
    if status:
        git("add", "--all", "--", "content")
        commit = git("commit", "--quiet", "-m", message, "--", "content", check=False)
        if commit.returncode:
            print("Committing failed:\n" + (commit.stderr or commit.stdout).strip(), file=sys.stderr)
            return 1
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        print(f"Note: you're on branch '{branch}'. GitHub publishes only main.", file=sys.stderr)
    push = git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}", check=False)
    if push.returncode:
        if re.search(r"non-fast-forward|\[rejected\]|fetch first", push.stderr):
            print("Committed here, but GitHub has newer commits (from the browser?), so the push was refused.\n"
                  f"Get them, then publish again:\n  {PULL}\n  scripts/publish.py\n" + push.stderr.strip(),
                  file=sys.stderr)
        else:
            print("Committed, but the push to GitHub failed; run 'git push' when you're online.\n"
                  + push.stderr.strip(), file=sys.stderr)
        return 1
    print(f"Pushed to {repos.STUDIO} ({branch}).")
    other = [line for line in git("status", "--porcelain").stdout.splitlines() if not line[3:].startswith("content/")]
    if other:
        print(f"Note: {len(other)} other uncommitted change(s) outside content/ (code or settings); "
              "commit those yourself when ready.")
    print(f"\nGitHub builds and deploys it now: watch https://github.com/{repos.STUDIO}/actions\n"
          f"Live in a few minutes at {build_site.ABS}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
