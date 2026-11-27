"""Claude SDK 백엔드의 계정 모델 조회 재료(X54, design §1.1-MB MD-4).

이 모듈은 SDK·네트워크를 직접 부르지 않는 부분(설정·응답 해석)과 Models API 쪽 넘김 호출을
담는다. 어느 경로도 **모델을 부르지 않는다**(토큰 비용 없음).

- ``sdk_init``: Claude Code CLI ``initialize`` 제어 응답(``ClaudeSDKClient.get_server_info()``)의
  ``models``(항목 ``value``·``displayName``·``description`` …). 백엔드가 ``connect()`` →
  ``get_server_info()`` → ``disconnect()``만 한다(``query()`` 없음).
  확인(MD.3): ``claude-agent-sdk`` 0.2.166 ``client.py`` ``get_server_info``(540행)가
  ``_internal/query.py`` ``initialize``(309~363행)의 응답 원본을 돌려주고, 번들 CLI 2.1.299의
  초기화 응답 스키마에 ``models``(항목 ``value``·``resolvedModel``·``displayName``·
  ``description``·``supportsEffort`` …)가 있다.
- ``models_api``: Anthropic Models API ``GET {base}/v1/models``(``limit``·``after_id`` 쪽 넘김,
  헤더 ``x-api-key``·``anthropic-version``). 응답 ``data[]``(``id``·``display_name``·
  ``max_input_tokens`` …)·``has_more``·``last_id``.

응답 모양은 관대하게 읽는다. 모르는 키는 ``attributes``로, id가 없는 항목은 건너뛰고 개수를
``details.skipped``에 센다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agent_console_runtime import ModelDiscoveryReasons, ModelDiscoveryResult

DEFAULT_ANTHROPIC_API_BASE_URL = "https://api.anthropic.com"
"""Models API 기본 주소(설정 ``model_discovery.api_base_url``·환경변수 ``ANTHROPIC_BASE_URL``가
없을 때)."""

ANTHROPIC_BASE_URL_ENV = "ANTHROPIC_BASE_URL"
"""Models API 주소를 바꾸는 환경변수 이름(Claude Code·Anthropic SDK와 같은 이름)."""

DEFAULT_ANTHROPIC_API_VERSION = "2023-06-01"
"""``anthropic-version`` 헤더 기본값."""

DEFAULT_MODELS_PAGE_LIMIT = 1000
"""Models API 쪽 크기 기본값(API 상한)."""

MAX_MODELS_PAGES = 20
"""쪽 넘김 최대 횟수(응답이 끝을 알리지 않을 때 멈추는 안전 한도)."""

METHOD_SDK_INIT = "sdk_init"
"""조회 방법: Claude Code CLI 초기화 응답."""

METHOD_MODELS_API = "models_api"
"""조회 방법: Anthropic Models API."""

type DiscoveryMethod = Literal["auto", "sdk_init", "models_api"]

_SDK_KEYS = {"value": "id", "displayName": "title", "description": "description"}
_API_KEYS = {"id": "id", "display_name": "title"}
_API_DROP = frozenset({"type"})


class ClaudeSdkModelDiscoveryOptions(BaseModel):
    """설치자 설정 ``model_discovery``: 계정 모델 조회 방법과 Models API 주소·헤더 값."""

    model_config = ConfigDict(extra="forbid")

    method: DiscoveryMethod = Field(
        default="auto",
        title="모델 조회 방법",
        description=(
            "auto = 점검 인증(readiness.auth)이 API 키면 Models API, 구독이면 Claude Code 초기화 "
            "응답. sdk_init·models_api로 고정할 수 있다. 어느 쪽도 모델을 부르지 않는다."
        ),
    )
    api_base_url: str | None = Field(
        default=None,
        title="Models API 주소",
        description=(
            "Models API를 부를 주소(프록시·사내 게이트웨이). 비우면 환경변수 ANTHROPIC_BASE_URL, "
            "그것도 없으면 공식 주소."
        ),
    )
    api_version: str = Field(
        default=DEFAULT_ANTHROPIC_API_VERSION,
        min_length=1,
        title="anthropic-version 헤더",
        description="Models API 요청의 anthropic-version 헤더 값.",
    )
    page_limit: int = Field(
        default=DEFAULT_MODELS_PAGE_LIMIT,
        ge=1,
        le=1000,
        title="쪽 크기",
        description="Models API 한 쪽에 받을 모델 수(1~1000).",
    )


@dataclass(frozen=True)
class ParsedModels:
    """응답 해석 결과.

    Attributes:
        models: ``ModelInfo`` 모양 사전(응답 순서).
        skipped: id가 없거나 모양이 틀려 건너뛴 항목 수.
    """

    models: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0


def _item(raw: Any, keys: Mapping[str, str], drop: frozenset[str] = frozenset()) -> dict[str, Any]:
    """응답 항목 하나 → ``ModelInfo`` 모양(모르는 키는 ``attributes``). id가 없으면 빈 사전."""
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Any] = {}
    attributes: dict[str, Any] = {}
    for key, value in raw.items():
        target = keys.get(str(key))
        if target is not None:
            if isinstance(value, str) and value:
                out[target] = value
            elif target == "id":
                return {}
        elif str(key) not in drop:
            attributes[str(key)] = value
    if "id" not in out:
        return {}
    if attributes:
        out["attributes"] = attributes
    return out


def models_from_server_info(info: Any) -> ParsedModels | None:
    """CLI 초기화 응답(``get_server_info()``) → 모델 목록. ``models`` 키가 없으면 None.

    >>> models_from_server_info({"commands": []}) is None
    True
    >>> parsed = models_from_server_info(
    ...     {"models": [{"value": "m-1", "displayName": "One", "supportsEffort": True}, {"x": 1}]}
    ... )
    >>> parsed.models, parsed.skipped
    ([{'id': 'm-1', 'title': 'One', 'attributes': {'supportsEffort': True}}], 1)

    Raises:
        ValueError: ``models``가 목록이 아니다(``invalid_response``).
    """
    if not isinstance(info, Mapping) or "models" not in info:
        return None
    items = info["models"]
    if not isinstance(items, list):
        raise ValueError("models is not a list")
    out: list[dict[str, Any]] = []
    skipped = 0
    for raw in items:
        parsed = _item(raw, _SDK_KEYS)
        if parsed:
            out.append(parsed)
        else:
            skipped += 1
    return ParsedModels(out, skipped)


@dataclass(frozen=True)
class ApiPage:
    """Models API 한 쪽."""

    parsed: ParsedModels
    has_more: bool
    last_id: str | None


def models_from_api_page(payload: Any) -> ApiPage:
    """Models API 응답 한 쪽 → 모델 목록(``max_input_tokens`` → ``context_window``).

    >>> page = models_from_api_page(
    ...     {"data": [{"type": "model", "id": "m-1", "display_name": "One",
    ...                "max_input_tokens": 9}], "has_more": False, "last_id": "m-1"}
    ... )
    >>> page.parsed.models, page.has_more
    ([{'id': 'm-1', 'title': 'One', 'context_window': 9}], False)

    Raises:
        ValueError: ``data``가 목록이 아니다(``invalid_response``).
    """
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise ValueError("data is not a list")
    out: list[dict[str, Any]] = []
    skipped = 0
    for raw in payload["data"]:
        parsed = _item(raw, _API_KEYS, _API_DROP)
        if not parsed:
            skipped += 1
            continue
        attributes = parsed.get("attributes", {})
        window = attributes.pop("max_input_tokens", None)
        if isinstance(window, int) and not isinstance(window, bool) and window > 0:
            parsed["context_window"] = window
        if not attributes:
            parsed.pop("attributes", None)
        out.append(parsed)
    last = payload.get("last_id")
    return ApiPage(
        ParsedModels(out, skipped),
        has_more=payload.get("has_more") is True,
        last_id=last if isinstance(last, str) and last else None,
    )


type HttpClientFactory = Callable[[], httpx.AsyncClient]
"""Models API 호출용 클라이언트 공장(테스트는 ``httpx.MockTransport``를 넣는다)."""


def default_http_client() -> httpx.AsyncClient:
    """기본 클라이언트(환경의 프록시 설정을 따른다)."""
    return httpx.AsyncClient()


AUTH_STATUSES = frozenset({401, 403})
"""인증 실패로 볼 HTTP 상태."""


def api_base_url(options: ClaudeSdkModelDiscoveryOptions, environ: Mapping[str, str]) -> str:
    """설정 → 환경변수 ``ANTHROPIC_BASE_URL`` → 공식 주소 순(끝의 ``/`` 없음).

    >>> api_base_url(ClaudeSdkModelDiscoveryOptions(), {})
    'https://api.anthropic.com'
    >>> api_base_url(ClaudeSdkModelDiscoveryOptions(), {"ANTHROPIC_BASE_URL": "http://gw/"})
    'http://gw'
    """
    chosen = (
        options.api_base_url
        or environ.get(ANTHROPIC_BASE_URL_ENV)
        or DEFAULT_ANTHROPIC_API_BASE_URL
    )
    return chosen.rstrip("/")


async def list_models_api(
    *,
    api_key: str,
    options: ClaudeSdkModelDiscoveryOptions,
    environ: Mapping[str, str],
    timeout_s: float,
    client_factory: HttpClientFactory = default_http_client,
    max_pages: int = MAX_MODELS_PAGES,
) -> ModelDiscoveryResult:
    """Models API를 쪽 넘김으로 끝까지 읽는다. 키는 헤더에만 싣고 결과·로그에 넣지 않는다.

    실패는 예외가 아니라 ``ok=False`` + 사유: 401·403 → ``auth_failed``, 연결 오류 →
    ``network``, 시간 초과 → ``timeout``, 모양 틀림 → ``invalid_response``, 그 밖의 상태 →
    ``error``(``details.http_status``).
    """
    url = api_base_url(options, environ) + "/v1/models"
    headers = {"x-api-key": api_key, "anthropic-version": options.api_version}
    found: list[dict[str, Any]] = []
    skipped = 0
    pages = 0
    after: str | None = None
    details: dict[str, Any] = {}
    try:
        async with client_factory() as client:
            while True:
                params: dict[str, Any] = {"limit": options.page_limit}
                if after is not None:
                    params["after_id"] = after
                response = await client.get(url, params=params, headers=headers, timeout=timeout_s)
                pages += 1
                if response.status_code in AUTH_STATUSES:
                    return _failed(ModelDiscoveryReasons.AUTH_FAILED, response.status_code)
                if response.status_code >= 400:
                    return _failed(ModelDiscoveryReasons.ERROR, response.status_code)
                try:
                    page = models_from_api_page(response.json())
                except ValueError:
                    return _failed(ModelDiscoveryReasons.INVALID_RESPONSE, response.status_code)
                found.extend(page.parsed.models)
                skipped += page.parsed.skipped
                if not page.has_more or page.last_id is None:
                    break
                if pages >= max_pages:
                    details["truncated"] = True
                    break
                after = page.last_id
    except httpx.TimeoutException:
        return ModelDiscoveryResult(
            ok=False, method=METHOD_MODELS_API, reason=ModelDiscoveryReasons.TIMEOUT
        )
    except httpx.TransportError as exc:
        return ModelDiscoveryResult(
            ok=False,
            method=METHOD_MODELS_API,
            reason=ModelDiscoveryReasons.NETWORK,
            details={"error": type(exc).__name__},
        )
    details.update({"pages": pages, "skipped": skipped})
    return ModelDiscoveryResult(ok=True, models=found, method=METHOD_MODELS_API, details=details)


def _failed(reason: str, status: int) -> ModelDiscoveryResult:
    return ModelDiscoveryResult(
        ok=False, method=METHOD_MODELS_API, reason=reason, details={"http_status": status}
    )


__all__ = [
    "ANTHROPIC_BASE_URL_ENV",
    "AUTH_STATUSES",
    "DEFAULT_ANTHROPIC_API_BASE_URL",
    "DEFAULT_ANTHROPIC_API_VERSION",
    "DEFAULT_MODELS_PAGE_LIMIT",
    "MAX_MODELS_PAGES",
    "METHOD_MODELS_API",
    "METHOD_SDK_INIT",
    "ApiPage",
    "ClaudeSdkModelDiscoveryOptions",
    "HttpClientFactory",
    "ParsedModels",
    "api_base_url",
    "default_http_client",
    "list_models_api",
    "models_from_api_page",
    "models_from_server_info",
]
