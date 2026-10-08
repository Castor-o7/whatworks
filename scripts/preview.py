#!/usr/bin/env python3
"""Preview the site locally, drafts included: build with --drafts, serve, and open the browser.

    scripts/preview.py            # http://localhost:8000/whatworks/
    scripts/preview.py --port 8001

Drafts show a "Draft preview" banner. This build can't be deployed by accident: deploy.sh refuses
it, and scripts/publish.py always rebuilds without drafts first. Edit a post, then re-run this (or
just re-run scripts/build_site.py --drafts in another terminal and refresh).
"""
import argparse
import os
import socket
import subprocess
import sys
import threading
import webbrowser
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


def port_free(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as serve.py's server does
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main():
    ap = argparse.ArgumentParser(description="Build with drafts, serve, and open the site.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    args = ap.parse_args()

    if not port_free(args.port):
        print(f"A preview is already running on port {args.port} (or something else is using it).\n"
              f"  It already shows your latest build: just refresh the browser after re-running\n"
              f"  scripts/build_site.py --drafts. Or stop it with Ctrl+C in its terminal window,\n"
              f"  or use another port: scripts/preview.py --port {args.port + 1}", file=sys.stderr)
        return 1
    build_site.install_draft_guard()
    posts = build_site.build(drafts=True)
    drafts = [p for p in posts if p.draft]
    url = f"http://localhost:{args.port}{build_site.BASE}/"
    if drafts:  # land on the draft saved most recently, since that's usually what you're working on
        newest = max(drafts, key=lambda p: (content.POSTS / f"{p.slug}.md").stat().st_mtime)
        url += f"post/{newest.slug}/"
    if not args.no_open:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    print(f"Opening {url}", flush=True)
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "serve.py"), "--port", str(args.port)])


if __name__ == "__main__":
    sys.exit(main())
