"""Serve the static web app in web/ on localhost for local use.

Usage: python run.py [--port N] [--no-browser]

Standard library only. Binds 127.0.0.1 (a free port unless --port is given),
prints the URL on one line, opens it in the default browser unless
--no-browser is given, and stops cleanly on Ctrl-C. Nothing is written to
the repository.
"""

import argparse
import functools
import http.server
import webbrowser
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent / "web"


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Static file handler with explicit types for ES modules and JSON.

    The default type map follows the operating system's registry, so the
    types the app needs are set here rather than left to chance.
    """

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def make_server(root: Path, port: int) -> http.server.ThreadingHTTPServer:
    """Return a server for `root` bound to 127.0.0.1:`port`, not yet serving."""
    handler = functools.partial(_Handler, directory=str(root))
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)


def main(argv: list[str], *, opener=webbrowser.open) -> int:
    """Run the launcher; return 0 once serving ends (Ctrl-C or shutdown)."""
    parser = argparse.ArgumentParser(description="Serve web/ on localhost.")
    parser.add_argument("--port", type=int, default=0, help="port (default: any free)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)

    server = make_server(WEB_ROOT, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(url, flush=True)
    if not args.no_browser:
        opener(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
