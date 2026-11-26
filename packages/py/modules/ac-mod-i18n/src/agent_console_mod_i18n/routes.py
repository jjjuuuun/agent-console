"""REST: ``GET /i18n`` and ``GET /i18n/{lang}`` (design §I18N.7), mounted under ``/api/v1``.

``GET /i18n/{lang}`` sends an ``ETag`` (a hash of the body) with ``Cache-Control: no-cache`` and
answers ``If-None-Match`` with 304, so the web can keep a catalog and revalidate cheaply.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import ErrorResponse
from agent_console_contracts.i18n import I18nInfo, MessageCatalog
from agent_console_modkit.host import etag, if_match_version

from .service import I18nService

CACHE_CONTROL = "no-cache"
"""``Cache-Control`` of catalog responses: keep, but revalidate with ``If-None-Match``."""

IfNoneMatchHeader = Annotated[
    str | None,
    Header(alias="If-None-Match", description="ETag of the catalog the caller already has."),
]


def _errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorResponse} for status in statuses}


def matches_etag(header: str | None, version: str) -> bool:
    """Whether an ``If-None-Match`` value names ``version`` (lists, ``W/`` and ``*`` allowed)."""
    if header is None:
        return False
    for part in header.split(","):
        text = part.strip()
        if text == "*" or if_match_version(text) == version:
            return True
    return False


def build_router(service: Callable[[], I18nService]) -> APIRouter:
    """``/i18n`` router.

    Args:
        service: returns the service (called per request).
    """
    router = APIRouter()

    @router.get("/i18n", response_model=I18nInfo, responses=_errors(401, 403, 500))
    def get_info() -> I18nInfo:
        """Languages the server has catalogs for, with sources, and the default/fallback languages.

        With no catalog at all the list is empty (200): the web uses its own catalogs.
        """
        return service().info()

    @router.get(
        "/i18n/{lang}",
        response_model=MessageCatalog,
        responses={304: {"description": "Not modified"}, **_errors(401, 403, 404, 500)},
    )
    def get_catalog(lang: str, if_none_match: IfNoneMatchHeader = None) -> Response:
        """Merged catalog of one language (``en-US`` matches ``en``).

        No catalog → 404 ``i18n.unknown_language``.
        """
        body = service().catalog(lang)
        headers = {"ETag": etag(body.version), "Cache-Control": CACHE_CONTROL}
        if matches_etag(if_none_match, body.version):
            return Response(status_code=304, headers=headers)
        return JSONResponse(content=body.catalog.model_dump(mode="json"), headers=headers)

    return router


__all__ = ["CACHE_CONTROL", "build_router", "matches_etag"]
