"""Tests for run.py, the local launcher. Localhost sockets only; no real browser."""

import http.client
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import run  # noqa: E402

WAIT = 10  # seconds; every wait has a limit so a defect fails instead of hanging


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=WAIT)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        resp.read()
        return resp.status, resp.getheader("Content-Type", "")
    finally:
        conn.close()


@pytest.fixture
def serve():
    """Serve a root on port 0 in a thread; yield its port; always shut down."""
    started = []

    def start(root):
        server = run.make_server(root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return server.server_address[1]

    yield start
    for server, thread in started:
        server.shutdown()
        thread.join(WAIT)
        server.server_close()


def test_serves_real_web_files_with_javascript_type(serve):
    port = serve(run.WEB_ROOT)
    js = next((run.WEB_ROOT / "src").rglob("*.js")).relative_to(run.WEB_ROOT)
    assert _get(port, "/index.html")[0] == 200
    status, ctype = _get(port, "/" + js.as_posix())
    assert status == 200
    assert ctype.startswith("text/javascript")


def test_module_and_json_types_are_explicit(serve, tmp_path, monkeypatch):
    # Make the OS-style fallback hostile so only run.py's own map can pass.
    import mimetypes

    monkeypatch.setattr(mimetypes, "guess_type", lambda *a, **k: ("text/plain", None))
    monkeypatch.setattr(
        run.http.server.SimpleHTTPRequestHandler,
        "extensions_map",
        {"": "application/octet-stream"},
    )
    for name in ("a.js", "b.mjs", "c.json"):
        (tmp_path / name).write_text("x")
    port = serve(tmp_path)
    assert _get(port, "/a.js")[1].startswith("text/javascript")
    assert _get(port, "/b.mjs")[1].startswith("text/javascript")
    assert _get(port, "/c.json")[1].startswith("application/json")


def test_path_outside_root_is_not_served(serve, tmp_path):
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text("ok")
    (tmp_path / "secret.txt").write_text("secret")
    port = serve(root)
    assert _get(port, "/index.html")[0] == 200
    assert _get(port, "/../secret.txt")[0] == 404
    assert _get(port, "/%2e%2e/secret.txt")[0] == 404


def _run_main(monkeypatch, argv, capsys):
    """Run main in a thread, wait until it serves, stop it; return (opened, printed)."""
    opened = []
    servers = []
    ready = threading.Event()
    real_make = run.make_server

    def spy(root, port):
        server = real_make(root, port)
        servers.append(server)
        ready.set()
        return server

    monkeypatch.setattr(run, "make_server", spy)
    result = []
    thread = threading.Thread(target=lambda: result.append(run.main(argv, opener=opened.append)))
    thread.start()
    assert ready.wait(WAIT)
    port = servers[0].server_address[1]
    assert _get(port, "/index.html")[0] == 200  # proves serve_forever is running
    servers[0].shutdown()
    thread.join(WAIT)
    assert not thread.is_alive()
    assert result == [0]
    return opened, capsys.readouterr().out.strip(), port


def test_no_browser_never_opens(monkeypatch, capsys):
    opened, out, port = _run_main(monkeypatch, ["--no-browser", "--port", "0"], capsys)
    assert opened == []
    assert out == f"http://127.0.0.1:{port}/"


def test_default_opens_printed_url_once(monkeypatch, capsys):
    opened, out, port = _run_main(monkeypatch, ["--port", "0"], capsys)
    assert opened == [out] == [f"http://127.0.0.1:{port}/"]


def test_explicit_port_is_the_bound_and_printed_port(monkeypatch, capsys):
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        chosen = probe.getsockname()[1]
    opened, out, port = _run_main(monkeypatch, ["--no-browser", "--port", str(chosen)], capsys)
    assert port == chosen
    assert out == f"http://127.0.0.1:{chosen}/"


def test_server_binds_loopback_only():
    server = run.make_server(run.WEB_ROOT, 0)
    try:
        assert server.socket.getsockname()[0] == "127.0.0.1"
    finally:
        server.server_close()
