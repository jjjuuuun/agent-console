"""HTTP 도우미: If-Match·ETag·내려받기 응답(3R.12)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_console_modkit.host import (
    BINARY_FILE_MEDIA_TYPE,
    ISSUES_HEADER,
    TEXT_FILE_MEDIA_TYPE,
    IfMatchHeader,
    attachment_response,
    etag,
    if_match_version,
    json_with_etag,
    with_issues,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ('"abc"', "abc"), ('W/"abc"', "abc"), (" abc ", "abc"), ('""', None)],
)
def test_if_match_version(value: str | None, expected: str | None) -> None:
    assert if_match_version(value) == expected


def test_json_with_etag_and_attachment() -> None:
    app = FastAPI()

    @app.get("/doc")
    async def doc(if_match: IfMatchHeader = None) -> object:
        return json_with_etag({"seen": if_match_version(if_match)}, version="v1", status_code=201)

    @app.get("/file/{kind}")
    async def file(kind: str) -> object:
        media = {"md": "text/markdown", "json": "application/json", "bin": "image/png"}[kind]
        return attachment_response(b"x", media, headers={"ETag": etag("v2")})

    with TestClient(app) as client:
        r = client.get("/doc", headers={"If-Match": 'W/"v0"'})
        assert (r.status_code, r.json(), r.headers["etag"]) == (201, {"seen": "v0"}, '"v1"')
        for kind, media in (("md", TEXT_FILE_MEDIA_TYPE), ("json", TEXT_FILE_MEDIA_TYPE)):
            r = client.get(f"/file/{kind}")
            assert r.headers["content-type"] == media
        r = client.get("/file/bin")
        assert r.headers["content-type"] == BINARY_FILE_MEDIA_TYPE
        assert r.headers["content-disposition"] == "attachment"
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["etag"] == '"v2"'
    assert json_with_etag([]).headers.get("etag") is None


def test_with_issues_header() -> None:
    """경고 이슈는 본문을 바꾸지 않고 헤더(JSON 배열, ASCII)로 실린다. 없으면 헤더 없음."""
    import json

    plain = with_issues(json_with_etag({"a": 1}, version="v"), [])
    assert ISSUES_HEADER not in plain.headers
    issue = {"severity": "warning", "code": "x.y", "message": "예약 이름"}
    res = with_issues(json_with_etag({"a": 1}, version="v"), [issue])
    raw = res.headers[ISSUES_HEADER]
    assert raw.isascii()
    assert json.loads(raw) == [issue]
    assert json.loads(bytes(res.body)) == {"a": 1}
