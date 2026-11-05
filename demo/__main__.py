"""Local demo server: a text box on top, the parsed address below it.

It listens on 127.0.0.1 only, so other devices cannot reach it. Addresses are
not stored or logged, and nothing is sent to the internet.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tradres import parse

HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_BODY_BYTES = 4096
PAGE = Path(__file__).parent / "index.html"


def parse_request(body: bytes) -> dict[str, object]:
    """``{"adres": "..."}`` -> the parsed fields. Raises ValueError on bad input."""
    data = json.loads(body.decode("utf-8"))
    address = data.get("adres") if isinstance(data, dict) else None
    if not isinstance(address, str):
        raise ValueError("'adres' must be a string")
    return parse(address).to_dict()


class Handler(BaseHTTPRequestHandler):
    server_version = "TrAdresDemo"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        else:
            self._send_json(404, {"hata": "bulunamadı"})

    def do_POST(self) -> None:
        if self.path != "/parse":
            self._send_json(404, {"hata": "bulunamadı"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.close_connection = True  # the unread body must not reach the next request
            self._send_json(413, {"hata": "adres çok uzun"})
            return
        try:
            self._send_json(200, parse_request(self.rfile.read(length)))
        except ValueError as error:  # also covers bad JSON and bad UTF-8
            self._send_json(400, {"hata": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        """Stay quiet: the demo keeps no record of what is typed."""


def make_server(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), Handler)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m demo", description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    with make_server(args.port) as server:
        print(f"Open http://{HOST}:{args.port} in your browser. Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
