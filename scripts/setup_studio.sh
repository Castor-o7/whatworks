#!/usr/bin/env bash
# One-time setup of the studio workflow (docs/STUDIO.md): a private repo for all the writing, drafts
# included, and GitHub Actions publishing the site to the public repo.
#
#     scripts/setup_studio.sh --dry-run   # print the plan; changes nothing and contacts nothing
#     scripts/setup_studio.sh             # do it, asking before every step that changes anything
#
# Steps (each is skipped when it's already done, so it's safe to run again after a failure):
#   1. Create the private repo <repos.studio> on GitHub (gh repo create --private).
#   2. Make a deploy key: an ed25519 key pair generated in a temporary folder. The public half becomes a
#      deploy key with WRITE access on <repos.public> only; the private half becomes the studio secret
#      PUBLIC_DEPLOY_KEY (gh secret set). Then the temporary folder is deleted, so the private key exists
#      only inside GitHub's secret store.
#   3. Push the storm data (_site/data/) to the public repo's site-data branch (scripts/publish_data.sh).
#   4. Push your main branch to the studio repo. This starts the first deploy.
#   5. Point this checkout's `origin` at the studio repo and add the public repo as the remote `public`,
#      fetch only: its push URL is set to one that fails, since only CI may write the public repo.
#   6. If step 4 had nothing to push, start a deploy with gh workflow run.
#
# Needs the GitHub CLI (`gh auth login` first), ssh-keygen, and the studio code committed on main.
# Settings (environment, for testing): GH (the gh command), STUDIO_URL, PUBLIC_URL (git URLs; by default
# GitHub URLs in the same form, SSH or HTTPS, as the current origin).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DRY=0
YES=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY=1 ;;
    --yes) YES=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "error: unknown option $arg (try --help)" >&2; exit 2 ;;
  esac
done

GH="${GH:-gh}"
PY="$ROOT/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
repo() { "$PY" -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb")).get("repos", {}).get(sys.argv[2], sys.argv[3]))' \
  "$ROOT/site.toml" "$1" "$2"; }
STUDIO_REPO="$(repo studio Castor-o7/whatworks-studio)"
PUBLIC_REPO="$(repo public Castor-o7/whatworks)"
ORIGIN="$(git config --get remote.origin.url || true)"
if [[ "$ORIGIN" == https://* ]]; then
  gh_url() { echo "https://github.com/$1.git"; }
else
  gh_url() { echo "git@github.com:$1.git"; }
fi
STUDIO_URL="${STUDIO_URL:-$(gh_url "$STUDIO_REPO")}"
PUBLIC_URL="${PUBLIC_URL:-$(gh_url "$PUBLIC_REPO")}"
KEY_TITLE="whatworks-studio CI (PUBLIC_DEPLOY_KEY)"
SECRET=PUBLIC_DEPLOY_KEY

N=0
step() { N=$((N + 1)); echo; echo "== Step $N: $1"; }
say() { echo "   $*"; }
cmd() { echo "   \$ $*"; }
# Ask before doing what was just printed. In a dry run, say so and answer no.
confirm() {
  if [[ "$DRY" == 1 ]]; then say "(dry run: would ask \"Do this?\", then run the commands above)"; return 1; fi
  if [[ "$YES" == 1 ]]; then return 0; fi
  local answer
  read -r -p "   Do this? [y/N] " answer || answer=""
  [[ "$answer" == y || "$answer" == Y || "$answer" == yes ]] || { say "Skipped."; return 1; }
}
lower() { tr '[:upper:]' '[:lower:]'; }
is_repo_url() {  # is_repo_url <url> <owner/name>: does the URL point at that GitHub repo?
  local u; u="$(echo "$1" | lower)"; u="${u%.git}"; u="${u%/}"
  [[ "$u" == *"github.com:$(echo "$2" | lower)" || "$u" == *"github.com/$(echo "$2" | lower)" ]]
}

echo "Studio setup: private $STUDIO_REPO (all writing, drafts included) publishes to public $PUBLIC_REPO."
[[ "$DRY" == 1 ]] && echo "DRY RUN: nothing will be changed, and nothing on GitHub will be contacted."
echo "   studio: $STUDIO_URL"
echo "   public: $PUBLIC_URL"
echo "   origin now: ${ORIGIN:-(none)}"

# ------------------------------------------------------------------ preflight (local, read-only)
echo; echo "== Before starting: check this checkout (nothing changes here)"
BLOCKERS=0
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != main ]]; then say "BLOCKER: you're on '$BRANCH'; switch to main (git switch main)."; BLOCKERS=1; fi
if git cat-file -e HEAD:.github/workflows/publish.yml 2>/dev/null && git cat-file -e HEAD:scripts/ci_publish.py 2>/dev/null; then
  say "ok: the studio code (.github/workflows/publish.yml, scripts/ci_publish.py) is committed on $BRANCH."
else
  say "BLOCKER: commit the studio code first (.github/workflows/publish.yml and scripts/ci_publish.py aren't"
  say "in the last commit). Commit your code changes outside content/, e.g.: git add -A -- ':!content' && git commit"
  BLOCKERS=1
fi
if [[ -f _site/data/meta.json.gz ]]; then
  say "ok: _site/data/ ($(du -sh _site/data | cut -f1)) is there for the site-data branch."
else
  say "BLOCKER: _site/data/meta.json.gz is missing: run scripts/build_data.py first."; BLOCKERS=1
fi
DRAFTS_LOCAL="$(git status --porcelain --untracked-files=all -- content | wc -l | tr -d ' ')"
say "note: $DRAFTS_LOCAL uncommitted file(s) in content/ (drafts and such) stay on this computer until"
say "      scripts/publish.py commits them to the studio repo after setup."
if [[ "$DRY" == 0 ]]; then
  command -v "$GH" >/dev/null || { echo "error: the GitHub CLI ($GH) isn't installed: brew install gh" >&2; exit 1; }
  "$GH" auth status >/dev/null 2>&1 || { echo "error: run 'gh auth login' first." >&2; exit 1; }
  command -v ssh-keygen >/dev/null || { echo "error: ssh-keygen isn't installed." >&2; exit 1; }
  if [[ "$BLOCKERS" == 1 ]]; then echo "Fix the BLOCKER(s) above and run this again." >&2; exit 1; fi
fi

# ------------------------------------------------------------------ 1. private studio repo
step "Create the private studio repo $STUDIO_REPO"
if [[ "$DRY" == 1 ]]; then
  say "would check: $GH repo view $STUDIO_REPO (skip if it exists; stop if it exists and isn't private)"
  cmd "$GH repo create $STUDIO_REPO --private --description \"What Works? writing studio (private)\""
  confirm || true
else
  VIS="$("$GH" repo view "$STUDIO_REPO" --json visibility -q .visibility 2>/dev/null || true)"
  if [[ -n "$VIS" && "$VIS" != PRIVATE ]]; then
    echo "error: $STUDIO_REPO exists and is $VIS. Drafts would be public: make it private on GitHub" \
      "(Settings > General > Danger Zone > Change visibility), then run this again." >&2
    exit 1
  elif [[ -n "$VIS" ]]; then
    say "already exists (private)."
  else
    cmd "$GH repo create $STUDIO_REPO --private --description \"What Works? writing studio (private)\""
    if confirm; then
      "$GH" repo create "$STUDIO_REPO" --private --description "What Works? writing studio (private)"
    else
      echo "The other steps need the studio repo; stopping." >&2; exit 1
    fi
  fi
fi

# ------------------------------------------------------------------ 2. deploy key + secret
step "Deploy key: write access to $PUBLIC_REPO, private half stored as the studio secret $SECRET"
show_key_plan() {
  cmd "TMP=\$(mktemp -d)"
  cmd "ssh-keygen -t ed25519 -N '' -C '$KEY_TITLE' -f \$TMP/key"
  cmd "$GH repo deploy-key add \$TMP/key.pub -R $PUBLIC_REPO --allow-write --title '$KEY_TITLE'"
  cmd "$GH secret set $SECRET -R $STUDIO_REPO < \$TMP/key"
  cmd "rm -rf \$TMP"
}
if [[ "$DRY" == 1 ]]; then
  say "would check: $GH secret list -R $STUDIO_REPO and $GH repo deploy-key list -R $PUBLIC_REPO"
  say "(skip if both the secret and a key titled '$KEY_TITLE' exist; otherwise make a new pair:)"
  show_key_plan
  say "then delete older deploy keys with the same title (their private halves are gone): $GH repo deploy-key delete <id> -R $PUBLIC_REPO"
  confirm || true
else
  HAS_SECRET=0
  "$GH" secret list -R "$STUDIO_REPO" --json name -q '.[].name' | grep -qx "$SECRET" && HAS_SECRET=1
  OLD_KEYS="$("$GH" repo deploy-key list -R "$PUBLIC_REPO" --json id,title \
    -q ".[] | select(.title == \"$KEY_TITLE\") | .id")"
  if [[ "$HAS_SECRET" == 1 && -n "$OLD_KEYS" ]]; then
    say "already set up (secret $SECRET and deploy key '$KEY_TITLE' exist)."
  else
    show_key_plan
    if confirm; then
      TMP="$(mktemp -d)"
      trap 'rm -rf "$TMP"' EXIT
      ssh-keygen -q -t ed25519 -N '' -C "$KEY_TITLE" -f "$TMP/key"
      "$GH" repo deploy-key add "$TMP/key.pub" -R "$PUBLIC_REPO" --allow-write --title "$KEY_TITLE"
      "$GH" secret set "$SECRET" -R "$STUDIO_REPO" < "$TMP/key"
      rm -rf "$TMP"
      trap - EXIT
      say "Done; the temporary key files are deleted."
      for id in $OLD_KEYS; do
        say "An older deploy key '$KEY_TITLE' (id $id) is left from an earlier attempt; its private half is gone."
        cmd "$GH repo deploy-key delete $id -R $PUBLIC_REPO"
        if confirm; then "$GH" repo deploy-key delete "$id" -R "$PUBLIC_REPO"; fi
      done
    else
      say "Without the key GitHub Actions can't publish; run this again when ready."
    fi
  fi
fi

# ------------------------------------------------------------------ 3. storm data
step "Push the storm data (_site/data/) to $PUBLIC_REPO's site-data branch"
cmd "PUBLIC_URL=$PUBLIC_URL scripts/publish_data.sh --no-redeploy"
say "(uploads only what the branch doesn't have; nothing if it's already current)"
if confirm; then
  PUBLIC_URL="$PUBLIC_URL" GH="$GH" "$ROOT/scripts/publish_data.sh" --no-redeploy
fi

# ------------------------------------------------------------------ 4. push main to the studio
step "Push main to the studio repo (this starts the first deploy)"
PUSHED=0
LOCAL_MAIN="$(git rev-parse main)"
if [[ "$DRY" == 1 ]]; then
  say "would check: git ls-remote $STUDIO_URL refs/heads/main (skip if it already has ${LOCAL_MAIN:0:12})"
  cmd "git push $STUDIO_URL main:main"
  confirm || true
else
  REMOTE_MAIN="$(git ls-remote "$STUDIO_URL" refs/heads/main | cut -f1)"
  if [[ "$REMOTE_MAIN" == "$LOCAL_MAIN" ]]; then
    say "already there (${LOCAL_MAIN:0:12})."
  else
    cmd "git push $STUDIO_URL main:main"
    if confirm; then git push "$STUDIO_URL" main:main && PUSHED=1; fi
  fi
fi

# ------------------------------------------------------------------ 5. local remotes
step "Point origin at the studio repo; the public repo becomes the remote 'public' (fetch only)"
# This checkout holds every draft, so it must never push to the public repo: only CI writes there. The
# remote 'public' gets a push URL that can't work (git push public fails at once); its fetch URL, which
# publish_data.sh reads, stays real. scripts/git-hooks/pre-push refuses such pushes too.
NO_PUSH="NO_PUSH_public_is_written_by_CI_only"
CUR_PUBLIC="$(git config --get remote.public.url || true)"
guard_public() {
  if [[ "$(git config --get remote.public.pushurl || true)" != "$NO_PUSH" ]]; then
    git config --unset-all remote.public.pushurl 2>/dev/null || true
    git remote set-url --push public "$NO_PUSH"
  fi
}
if [[ "$ORIGIN" == "$STUDIO_URL" ]] || is_repo_url "$ORIGIN" "$STUDIO_REPO"; then
  say "origin is already the studio repo."
  if [[ -z "$CUR_PUBLIC" ]]; then cmd "git remote add public $PUBLIC_URL"; fi
  if [[ -z "$CUR_PUBLIC" || "$(git config --get remote.public.pushurl || true)" != "$NO_PUSH" ]]; then
    cmd "git remote set-url --push public $NO_PUSH"
    if confirm; then
      [[ -n "$CUR_PUBLIC" ]] || git remote add public "$PUBLIC_URL"
      guard_public
    fi
  fi
else
  if [[ -z "$CUR_PUBLIC" ]]; then cmd "git remote add public $PUBLIC_URL"; else say "remote 'public' exists: $CUR_PUBLIC"; fi
  cmd "git remote set-url --push public $NO_PUSH"
  cmd "git remote set-url origin $STUDIO_URL"
  cmd "git fetch origin && git branch --set-upstream-to=origin/main main"
  cmd "git config core.hooksPath scripts/git-hooks   (if it isn't set to something else already)"
  if confirm; then
    [[ -n "$CUR_PUBLIC" ]] || git remote add public "$PUBLIC_URL"
    guard_public
    git remote set-url origin "$STUDIO_URL"
    git fetch --quiet origin && git branch --quiet --set-upstream-to=origin/main main
    if [[ -z "$(git config --get core.hooksPath || true)" ]]; then git config core.hooksPath scripts/git-hooks; fi
    say "origin -> $STUDIO_URL; public -> $(git config --get remote.public.url) (pushes refused)"
  fi
fi

# ------------------------------------------------------------------ 6. first deploy
step "First deploy"
if [[ "$PUSHED" == 1 ]]; then
  say "The push in step 4 started it."
else
  say "(only needed when step 4 had nothing to push; a push starts the run by itself)"
  cmd "$GH workflow run publish.yml -R $STUDIO_REPO --ref main"
  if confirm; then "$GH" workflow run publish.yml -R "$STUDIO_REPO" --ref main; fi
fi

echo
echo "Watch it at https://github.com/$STUDIO_REPO/actions (the first run installs TeX Live; later runs are faster)."
echo "GitHub Pages settings don't change: $PUBLIC_REPO still serves its gh-pages branch."
echo "From now on: write in the browser (https://github.dev/$STUDIO_REPO) or locally with scripts/publish.py."
echo "The first deploy also replaces the public repo's main with the code only (content/ is no longer there)."
if [[ -d _site/.git ]]; then
  echo "_site/.git (the old deploy.sh repo) is no longer used; you can delete it: rm -rf _site/.git"
fi
[[ "$DRY" == 1 ]] && echo "Dry run complete: nothing was changed."
exit 0
