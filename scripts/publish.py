#!/usr/bin/env python3
"""Publish: rebuild without drafts, deploy to GitHub Pages, and save your published posts to GitHub.

    scripts/publish.py               # do it
    scripts/publish.py --dry-run     # show what would happen, change nothing
    scripts/publish.py --force       # publish even if the checks below find something

What it does, in order:
  0. Checks the posts going live: it stops on a post it can't read, and, unless you pass --force, on
     a new or changed post with template leftovers (the placeholder summary, empty headings, a [^ref]
     with no source) or a storm chart it can't make sense of. For a
     post going live for the first time, it offers to change its date to today.
  1. Builds the site WITHOUT drafts (scripts/build_site.py).
  2. Deploys it (scripts/deploy.sh), live about a minute later.
  3. Commits your published posts (content/posts/*.md that aren't drafts, deleted posts, and the
     template) to the main branch and pushes them, so your writing is backed up in the repo. Drafts
     and other files (editor backups and such) are never committed: the repo is public, so a draft
     stays only on this computer until you publish it.
Code changes outside content/ are left for you to commit yourself.
"""
import argparse
import os
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
from app import content  # noqa: E402
import build_site  # noqa: E402


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=check, capture_output=True, text=True).stdout


TEMPLATE = "content/POST_TEMPLATE.md"


def content_changes():
    """Changed files under content/ as (status, path), from git's point of view. A rename shows up
    twice: the new path with status 'R', and the old one as a deletion ('D')."""
    out = git("status", "--porcelain", "-z", "--untracked-files=all", "--", "content")
    entries = out.split("\0")
    changes, i = [], 0
    while i < len(entries) and entries[i]:
        status, path = entries[i][:2], entries[i][3:]
        changes.append((status, path))
        if status[0] in "RC":  # renames and copies carry the old path as the next entry
            i += 1
            if status[0] == "R":
                changes.append(("D ", entries[i]))
        i += 1
    return changes


def is_post_path(path):
    """content/posts/<name>.md: the only files (besides the template) that are ever backed up."""
    p = Path(path)
    return p.parent == Path("content/posts") and p.suffix == ".md" and not p.name.startswith(".")


def sort_changes(changes):
    """-> (to_save, drafts, skipped). Only an allowlist is backed up: posts that aren't drafts, deleted
    posts, and the template. Drafts, editor backups (.swp, ~) and anything else stay off GitHub."""
    to_save, drafts, skipped = [], [], []
    for status, path in changes:
        p = ROOT / path
        if path == TEMPLATE:
            to_save.append(path)
        elif not is_post_path(path):
            skipped.append(path)
        elif not p.exists():
            if head_text(path) is not None:  # a deleted post (one never committed has nothing to back up)
                to_save.append(path)
        elif content.is_draft(p.read_text(encoding="utf-8", errors="replace"), path):
            drafts.append(path)
        else:
            to_save.append(path)
    return to_save, drafts, skipped


def head_text(path):
    """The file as of the last commit, or None if it isn't there."""
    shown = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{path}"], capture_output=True)
    return shown.stdout.decode("utf-8", "replace") if shown.returncode == 0 else None


def is_new(path):
    """Not in the last commit yet (or only as a draft): i.e. going live for the first time."""
    old = head_text(path)
    return old is None or content.is_draft(old, path)


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
    ap = argparse.ArgumentParser(description="Build, deploy, and back up published posts.")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen without deploying or committing")
    ap.add_argument("--force", action="store_true", help="publish even with warnings (template leftovers etc.)")
    ap.add_argument("-m", "--message", help="commit message (default lists the posts)")
    args = ap.parse_args()
    if not args.dry_run:
        build_site.install_draft_guard()

    # 0. Every post meant to be live must be readable; a broken draft is just left out.
    posts, errors = content.load_posts()
    broken = [e for e in errors if not e.draft]
    for e in errors:
        print(f"{'error' if not e.draft else 'warning'}: {e}" + ("" if not e.draft else " (draft skipped)"),
              file=sys.stderr)
    if broken:
        print("\nFix the file(s) above first (or add 'draft: true' to keep one private). Nothing was published.",
              file=sys.stderr)
        return 1

    changes = content_changes()
    to_save, held, skipped = sort_changes(changes)
    renamed = {path for status, path in changes if status[0] == "R"}
    new = [(path, content.parse(ROOT / path)) for path in to_save
           if path != TEMPLATE and path not in renamed and (ROOT / path).exists() and is_new(path)]
    if new:
        print("Going live for the first time:")
        for path, post in new:
            print(f"  {post.title}  ({path}, dated {post.date})")
            offer_today(path, post, args.dry_run)

    # 1. Check, then build exactly what readers will see.
    meta = build_site.load_meta()
    warnings = build_site.problems(content.all_posts(), [], meta)
    # Only posts changed since the last publish can stop it; older ones are just mentioned.
    blocking = [w for w in warnings if w.split(": ", 1)[0] in to_save]
    older = [w for w in warnings if w not in blocking]
    if older:
        print("\nNotes on posts already live (fix when you can):\n  " + "\n  ".join(older))
    if blocking:
        print("\nCheck these before publishing:\n  " + "\n  ".join(blocking))
        if not args.force:
            print("Fix them and run publish.py again, or run 'scripts/publish.py --force' to publish anyway."
                  + ("" if not args.dry_run else "\n(Dry run: a real publish would stop here.)"))
            if not args.dry_run:
                return 1
    posts = build_site.build(drafts=False, report=False)
    drafts = [p for p in content.all_posts(drafts=True) if p.draft]

    titles = [content.parse(ROOT / path).title for path in to_save
              if path != TEMPLATE and (ROOT / path).exists()]
    message = args.message or ("Publish: " + "; ".join(titles) if titles else "Publish site")

    print(f"\n{len(posts)} published post(s) will be live.")
    if drafts:
        print(f"{len(drafts)} draft(s) stay private: " + ", ".join(p.slug for p in drafts))
    print("Will back up to GitHub: " + (", ".join(to_save) if to_save else "nothing new"))
    if held:
        print("Not backing up (drafts): " + ", ".join(held))
    if skipped:
        print("Not backing up (not a post file; posts are content/posts/<name>.md): " + ", ".join(skipped))
    if args.dry_run:
        print("\nDry run: nothing deployed or committed.")
        return 0

    # 2. Deploy.
    print("\nDeploying...", flush=True)
    if subprocess.call([str(ROOT / "scripts" / "deploy.sh"), message]) != 0:
        print("Deploy failed; nothing was committed.", file=sys.stderr)
        return 1

    # 3. Back up published writing (only the allowlist above, never drafts). `git commit -- <paths>`
    # commits just these paths, whatever else is staged; untracked ones must be added first, and a
    # deletion is recorded with `git rm --cached` (a no-op if it's already staged).
    if to_save:
        present = [path for path in to_save if (ROOT / path).exists()]
        gone = [path for path in to_save if not (ROOT / path).exists()]
        if present:
            git("add", "--", *present)
        if gone:
            git("rm", "--cached", "--quiet", "--ignore-unmatch", "--", *gone)
        commit = subprocess.run(["git", "-C", str(ROOT), "commit", "--quiet", "-m", message, "--", *to_save],
                                capture_output=True, text=True)
        if commit.returncode:
            print("The site is live, but backing up your posts failed:\n" + (commit.stderr or commit.stdout).strip(),
                  file=sys.stderr)
            return 1
        push = subprocess.run(["git", "-C", str(ROOT), "push", "--quiet"], capture_output=True, text=True)
        if push.returncode:
            print("Committed your posts, but the push to GitHub failed; run 'git push' when you're online.\n"
                  + push.stderr.strip(), file=sys.stderr)
        else:
            print("Backed up your posts to GitHub (main).")
    other = [line for line in git("status", "--porcelain").splitlines() if not line[3:].startswith("content/")]
    if other:
        print(f"Note: {len(other)} other uncommitted change(s) outside content/ (code or settings); "
              "commit those yourself when ready. (The draft guard stops git from committing a draft.)")
    print(f"\nDone. Live in about a minute at https://castor-o7.github.io{build_site.BASE}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
