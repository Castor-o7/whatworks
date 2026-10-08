"""Preview _site/ the way GitHub Pages serves it (see docs/STATIC_SITE.md).

    .venv/bin/python scripts/serve.py [--port 8000]   ->  http://localhost:8000/whatworks/

Stdlib only. Mirrors the parts of Pages the site depends on: everything lives under the base path,
"/" redirects there, a directory serves its index.html (and gets its trailing slash added by
redirect), and anything missing gets 404.html with a 404 status.
"""
import argparse
import http.server
import posixpath
import tomllib
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
SITE = tomllib.loads((ROOT / "site.toml").read_text())
BASE = ("/" + SITE.get("base_url", "").strip("/")).rstrip("/")


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
        ".gz": "application/gzip",  # like Pages: plain bytes, no Content-Encoding
        ".svg": "image/svg+xml",
        ".md": "text/markdown; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }

    def do_GET(self):
        if self.redirect_to_base():
            return
        super().do_GET()

    def do_HEAD(self):
        if self.redirect_to_base():
            return
        super().do_HEAD()

    def redirect_to_base(self):
        if BASE and urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", BASE + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    def translate_path(self, path):
        """Map /whatworks/x to _site/x; anything outside the base path maps to nothing."""
        path = urlsplit(path).path
        if BASE:
            if path != BASE and not path.startswith(BASE + "/"):
                return str(OUT / "__outside_base__")
            path = path[len(BASE):] or "/"
        if posixpath.basename(path) == ".git" or "/.git/" in path:
            return str(OUT / "__hidden__")  # the deploy repo is not part of the site
        return super().translate_path(path)

    def list_directory(self, path):
        self.send_error(404)  # Pages never lists directories
        return None

    def send_error(self, code, message=None, explain=None):
        page = OUT / "404.html"
        if code != 404 or not page.exists():
            return super().send_error(code, message, explain)
        body = page.read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # always show the latest build
        super().end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()
    if not (OUT / "index.html").exists():
        raise SystemExit("_site/ has no index.html yet: run scripts/build_site.py first.")
    if not (OUT / "data" / "meta.json.gz").exists():
        print("note: _site/data/ is missing, so the Storm Desk will have no data (run scripts/build_data.py).",
              flush=True)
    handler = partial(PagesHandler, directory=str(OUT))
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as httpd:
        print(f"serving {OUT.relative_to(ROOT)}/ at http://localhost:{args.port}{BASE}/  (Ctrl+C to stop)",
              flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
