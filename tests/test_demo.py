"""Tests for the local demo server."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from demo.__main__ import HOST, MAX_BODY_BYTES, make_server, parse_request, snapshot


def test_parse_request() -> None:
    body = json.dumps({"adres": "Kadıköy"}).encode("utf-8")
    assert parse_request(body)["il"] == "İstanbul"


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"adres": 5}', b"\xff"])
def test_parse_request_rejects_bad_input(body: bytes) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - each case has its own message
        parse_request(body)


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    server = make_server(0)  # port 0: the system picks a free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://{HOST}:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join()


def _post(url: str, body: bytes) -> tuple[int, dict[str, str | None]]:
    request = urllib.request.Request(f"{url}/parse", data=body, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_server_listens_on_localhost_only() -> None:
    assert HOST == "127.0.0.1"


def test_page(url: str) -> None:
    with urllib.request.urlopen(url) as response:
        page = response.read().decode("utf-8")
    assert response.status == 200
    assert "<textarea" in page


def test_parse_endpoint(url: str) -> None:
    status, data = _post(url, json.dumps({"adres": "Kızılay Mah. Çankaya Ankara"}).encode("utf-8"))
    assert status == 200
    assert (data["il"], data["ilce"], data["mahalle"]) == ("Ankara", "Çankaya", "Kızılay")


def test_bad_json_is_a_400(url: str) -> None:
    assert _post(url, b"not json")[0] == 400


def test_long_body_is_refused(url: str) -> None:
    assert _post(url, b"x" * (MAX_BODY_BYTES + 1))[0] == 413


@pytest.mark.parametrize("path", ["/nope"])
def test_unknown_paths(url: str, path: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(url + path)
    assert info.value.code == 404
    request = urllib.request.Request(url + path, data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(request)
    assert info.value.code == 404


def test_snapshot_sees_a_changed_file(tmp_path: Path) -> None:
    code = tmp_path / "nested" / "code.py"
    code.parent.mkdir()
    code.write_text("a = 1", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not watched", encoding="utf-8")

    before = snapshot([tmp_path])
    assert list(before) == [code]

    os.utime(code, ns=(1, 1))
    assert snapshot([tmp_path]) != before


def test_page_is_not_cached(url: str) -> None:
    with urllib.request.urlopen(url) as response:
        assert response.headers["Cache-Control"] == "no-store"
