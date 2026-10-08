#!/usr/bin/env bash
# Publish _site/ to the gh-pages branch of castor-o7/whatworks (see docs/STATIC_SITE.md).
#
#     scripts/deploy.sh ["commit message"]
#
# _site/ is its own small git repo (created on first run) whose only branch is gh-pages, so the
# built site never lands on main. Each run commits whatever changed and pushes it. Run
# scripts/build_site.py first; scripts/build_data.py must have been run at least once.
set -euo pipefail

BRANCH="gh-pages"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Publish to the same GitHub repo (and transport, SSH or HTTPS) the source checkout uses.
REMOTE="$(git -C "$ROOT" remote get-url origin 2>/dev/null || echo "https://github.com/castor-o7/whatworks.git")"
SITE="$ROOT/_site"

if [[ ! -f "$SITE/data/meta.json.gz" ]]; then
  echo "error: $SITE/data/meta.json.gz is missing. Run scripts/build_data.py, then scripts/build_site.py." >&2
  exit 1
fi
if [[ ! -f "$SITE/index.html" || ! -f "$SITE/.nojekyll" ]]; then
  echo "error: $SITE has no pages yet. Run scripts/build_site.py." >&2
  exit 1
fi
if [[ -f "$SITE/.drafts" ]]; then
  echo "error: _site/ was built with --drafts (a local preview that includes unpublished drafts)." >&2
  echo "Rebuild without it (.venv/bin/python scripts/build_site.py), or just run scripts/publish.py." >&2
  exit 1
fi
# build_data.py writes into data.tmp/ (and parks the old dataset in data.old/) until it finishes.
# Either one left over means a run is going or was interrupted; publishing it would roughly double
# the site past GitHub Pages' 1 GB limit.
for d in data.tmp data.old; do
  if [[ -e "$SITE/$d" ]]; then
    echo "error: $SITE/$d exists (build_data.py is running or was interrupted). Let it finish, or delete it." >&2
    exit 1
  fi
done

cd "$SITE"
if [[ ! -d .git ]]; then
  git init --quiet
  git symbolic-ref HEAD "refs/heads/$BRANCH"
fi
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE"
else
  git remote add origin "$REMOTE"
fi
# Stay on gh-pages even if the repo was created some other way.
[[ "$(git symbolic-ref --short HEAD)" == "$BRANCH" ]] || git checkout --quiet -B "$BRANCH"

# Never publish build scratch or Finder litter, even if it shows up later; untrack any that slipped in.
printf '%s\n' 'data.tmp/' 'data.old/' '.DS_Store' '.drafts' > .git/info/exclude
if [[ -n "$(git ls-files --cached --ignored --exclude-standard)" ]]; then
  git ls-files -z --cached --ignored --exclude-standard | xargs -0 git rm -r --cached --quiet --
fi
git add --all .
if git diff --cached --quiet && git rev-parse --verify --quiet HEAD >/dev/null; then
  echo "Nothing changed since the last deploy; pushing anyway in case the last push failed."
else
  git commit --quiet -m "${1:-Publish site $(date -u +%Y-%m-%dT%H:%MZ)}"
fi
# _site is the source of truth for gh-pages, so overwrite whatever the remote branch holds.
git push --force --set-upstream origin "$BRANCH"
echo "Pushed to $BRANCH. Live in a minute or two at https://castor-o7.github.io/whatworks/"
