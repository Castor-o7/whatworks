"""Which GitHub repo is which (site.toml [repos]; docs/STUDIO.md). Stdlib only, so the git hook can use it.

The studio repo is private and holds everything, drafts included; the public repo gets only what
GitHub Actions pushes. Until scripts/setup_studio.sh has run, this checkout's `origin` is still the
public repo, and then drafts must not be committed (publish.py and the pre-commit hook check this).
"""
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_REPOS = tomllib.loads((ROOT / "site.toml").read_text()).get("repos", {})
STUDIO = _REPOS.get("studio", "Castor-o7/whatworks-studio")
PUBLIC = _REPOS.get("public", "Castor-o7/whatworks")
GITHUB = re.compile(r"^(?:git@github\.com:|ssh://git@github\.com/|https?://(?:[^@/]+@)?github\.com/)"
                    r"([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", re.I)


def github_repo(url):
    """'git@github.com:Castor-o7/whatworks.git' -> 'castor-o7/whatworks' (None for anything else)."""
    m = GITHUB.match((url or "").strip())
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def remote_url(name="origin", root=ROOT):
    """The URL as configured (`git remote get-url` would apply url.*.insteadOf rewrites)."""
    p = subprocess.run(["git", "-C", str(root), "config", "--get", f"remote.{name}.url"], capture_output=True,
                       text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def origin_is_public(root=ROOT):
    """True while origin is the public repo (setup_studio.sh hasn't switched it to the studio yet)."""
    return github_repo(remote_url("origin", root)) == PUBLIC.lower()
