"""모듈 라우트가 함께 쓰는 HTTP 도우미: ``If-Match``·``ETag``·내려받기 응답(기능 로직 없음).

버전 있는 자원(정의 등)을 다루는 모듈은 같은 규칙을 따른다: 요청 ``If-Match`` = 마지막으로 받은
버전(따옴표·약한 비교 접두 ``W/`` 허용), 응답 ``ETag`` = 지금 버전(따옴표로 감쌈). 본문 파일은 같은
출처에서 HTML로 그려지지 않게 텍스트도 ``text/plain``으로 내려보낸다.

저장은 됐지만 알릴 것이 있으면(경고 이슈) 응답 본문 모양을 바꾸지 않고 ``X-Console-Issues``
헤더에 이슈 목록(JSON 배열, ASCII)을 싣는다(``with_issues``).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from typing import Annotated, Any

from fastapi import Header, Response
from fastapi.responses import JSONResponse

TEXT_FILE_MEDIA_TYPE = "text/plain; charset=utf-8"
BINARY_FILE_MEDIA_TYPE = "application/octet-stream"
TEXT_LIKE_MEDIA_TYPES: frozenset[str] = frozenset({"application/json"})
"""``text/*`` 밖에서 텍스트로 내려보낼 형식."""

ISSUES_HEADER = "X-Console-Issues"
"""성공 응답에 붙이는 경고 이슈 목록 헤더(JSON 배열, ASCII 이스케이프). CORS로 노출된다."""

IfMatchHeader = Annotated[
    str | None,
    Header(alias="If-Match", description="마지막으로 받은 version_hash(ETag)."),
]
"""라우트 매개변수 형식: ``if_match: IfMatchHeader = None``."""


def if_match_version(value: str | None) -> str | None:
    """``If-Match`` 값 → 기대 버전. 따옴표·약한 비교 접두(``W/``)를 벗긴다. 비면 None."""
    if value is None:
        return None
    text = value.strip()
    if text.startswith("W/"):
        text = text[2:]
    return text.strip('"') or None


def etag(version: str) -> str:
    """버전 → ``ETag`` 헤더 값(따옴표로 감쌈)."""
    return f'"{version}"'


def json_with_etag(
    content: Any, *, version: str | None = None, status_code: int = 200
) -> JSONResponse:
    """JSON 응답(+ ``version``이 있으면 ``ETag``). 본문은 그대로 보낸다(모델 직렬화 없음)."""
    headers = {"ETag": etag(version)} if version is not None else None
    return JSONResponse(content=content, status_code=status_code, headers=headers)


def attachment_response(
    data: bytes,
    media_type: str | None,
    *,
    text_like: Collection[str] = TEXT_LIKE_MEDIA_TYPES,
    headers: dict[str, str] | None = None,
) -> Response:
    """본문 파일 내려받기 응답. 텍스트 형식이면 ``text/plain``, 그 밖은 바이너리.

    ``Cache-Control: no-store``·``Content-Disposition: attachment``를 붙인다
    (원래 형식은 목록이 안다).
    """
    is_text = media_type is not None and (media_type.startswith("text/") or media_type in text_like)
    return Response(
        content=data,
        media_type=TEXT_FILE_MEDIA_TYPE if is_text else BINARY_FILE_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "attachment",
            **(headers or {}),
        },
    )


def with_issues[R: Response](response: R, issues: Sequence[Mapping[str, Any]]) -> R:
    """``issues``가 있으면 ``ISSUES_HEADER``에 JSON 배열로 싣고 같은 응답을 돌려준다.

    Args:
        response: 보낼 응답(본문은 그대로).
        issues: 이슈 dict 목록(예: 계약 ``Issue.model_dump(mode="json", exclude_none=True)``).
            값(비밀 등)을 담지 않은 것만 넘긴다. 비어 있으면 헤더를 붙이지 않는다.
    """
    if issues:
        response.headers[ISSUES_HEADER] = json.dumps(
            [dict(i) for i in issues], ensure_ascii=True, separators=(",", ":")
        )
    return response


__all__ = [
    "BINARY_FILE_MEDIA_TYPE",
    "ISSUES_HEADER",
    "TEXT_FILE_MEDIA_TYPE",
    "TEXT_LIKE_MEDIA_TYPES",
    "IfMatchHeader",
    "attachment_response",
    "etag",
    "if_match_version",
    "json_with_etag",
    "with_issues",
]
