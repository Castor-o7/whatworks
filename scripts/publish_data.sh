#!/usr/bin/env bash
# Publish the storm data (_site/data/, written by scripts/build_data.py) to the public repo's site-data
# branch, then ask GitHub to redeploy the site with it (docs/STUDIO.md).
#
#     scripts/publish_data.sh                 # after build_data.py
#     scripts/publish_data.sh --no-redeploy   # just update site-data
#
# site-data is an orphan branch: each run replaces it with a single commit of the current data, so old
# datasets don't pile up in the public repo. Only files that changed are uploaded (the current tip is
# fetched first). GitHub Actions copies the branch into _site/data/ on every deploy, so the data is
# published the next time the site deploys; this script starts that deploy with `gh workflow run`
# (or tells you how to start it from the Actions tab).
#
# Settings (environment): PUBLIC_URL (where to push; default the `public` git remote, else
# git@github.com:<repos.public>.git from site.toml), GH (the gh command, default gh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/_site/data"
GITDIR="$ROOT/.cache/site-data.git"
GH="${GH:-gh}"
REDEPLOY=1
for arg in "$@"; do
  case "$arg" in
    --no-redeploy) REDEPLOY=0 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "error: unknown option $arg (try --help)" >&2; exit 2 ;;
  esac
done

PY="$ROOT/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
repo() { "$PY" -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb")).get("repos", {}).get(sys.argv[2], sys.argv[3]))' \
  "$ROOT/site.toml" "$1" "$2"; }
PUBLIC_REPO="$(repo public Castor-o7/whatworks)"
STUDIO_REPO="$(repo studio Castor-o7/whatworks-studio)"
URL="${PUBLIC_URL:-$(git -C "$ROOT" remote get-url public 2>/dev/null || echo "git@github.com:$PUBLIC_REPO.git")}"

if [[ ! -f "$DATA/meta.json.gz" ]]; then
  echo "error: $DATA/meta.json.gz is missing. Run scripts/build_data.py first." >&2
  exit 1
fi
# build_data.py writes into data.tmp/ (and parks the old dataset in data.old/) until it finishes.
for d in data.tmp data.old; do
  if [[ -e "$ROOT/_site/$d" ]]; then
    echo "error: _site/$d exists (build_data.py is running or was interrupted). Let it finish, or delete it." >&2
    exit 1
  fi
done

g() { git --git-dir="$GITDIR" -c core.excludesFile= -c core.autocrlf=false "$@"; }
if [[ ! -f "$GITDIR/HEAD" ]]; then
  mkdir -p "$(dirname "$GITDIR")"
  git init --quiet --bare "$GITDIR"
fi
printf '%s\n' '.DS_Store' > "$GITDIR/info/exclude"

echo "Publishing $(du -sh "$DATA" | cut -f1) of storm data to site-data on $URL"
OLD=""
if git ls-remote --exit-code --heads "$URL" site-data >/dev/null 2>&1; then
  g fetch --quiet --no-tags --depth 1 "$URL" +refs/heads/site-data:refs/remotes/public/site-data
  OLD="$(g rev-parse refs/remotes/public/site-data)"
fi

export GIT_INDEX_FILE="$GITDIR/data.index"
rm -f "$GIT_INDEX_FILE"
g --work-tree="$DATA" add --all .
TREE="$(g write-tree)"
rm -f "$GIT_INDEX_FILE"
unset GIT_INDEX_FILE

if [[ -n "$OLD" && "$(g rev-parse "$OLD^{tree}")" == "$TREE" ]]; then
  echo "site-data already has this data; nothing to push."
else
  NAME="$(git config user.name || echo 'What Works')"
  EMAIL="$(git config user.email || echo 'whatworks@users.noreply.github.com')"
  COMMIT="$(GIT_AUTHOR_NAME="$NAME" GIT_AUTHOR_EMAIL="$EMAIL" GIT_COMMITTER_NAME="$NAME" \
    GIT_COMMITTER_EMAIL="$EMAIL" g commit-tree "$TREE" -m "Storm data $(date -u +%Y-%m-%d)")"
  # Orphan commit: it replaces the branch (the lease refuses if someone else pushed since the fetch).
  g push --quiet --force-with-lease="refs/heads/site-data:$OLD" "$URL" "$COMMIT:refs/heads/site-data"
  echo "Pushed site-data ${COMMIT:0:12}."
fi

if [[ "$REDEPLOY" == 0 ]]; then
  echo "Not redeploying (--no-redeploy). The data goes live with the next deploy."
  exit 0
fi
if command -v "$GH" >/dev/null 2>&1 && "$GH" auth status >/dev/null 2>&1; then
  "$GH" workflow run publish.yml -R "$STUDIO_REPO" --ref main
  echo "Started a deploy: https://github.com/$STUDIO_REPO/actions (live in a few minutes)."
else
  echo "To put the new data live, start a deploy: open https://github.com/$STUDIO_REPO/actions,"
  echo "choose \"Publish\", then \"Run workflow\" (or push any commit to the studio repo)."
  echo "(With the GitHub CLI installed and logged in, this script does that for you.)"
fi
