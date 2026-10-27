"""link-logs-architecture 설정(설치자 값, ``modules.options.link-logs-architecture``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

DEFAULT_CACHE_SCOPES = 8
DEFAULT_CACHE_EVENTS = 100_000
DEFAULT_CACHE_PROFILES = 4
DEFAULT_PAGE_SIZE = 1000
DEFAULT_UNLISTED_PATHS: tuple[str, ...] = ("/detail", "/raw")
"""목록 본문에 없는 이벤트 경로 접두 기본값(목록 이벤트는 ``detail``·``raw``가 비어 있다, M-4)."""


class LogsArchitectureSettings(BaseModel):
    """로그 구조도의 출처 종류 대응과 결과 캐시 크기를 정하는 설치자 설정입니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 설치자 값(``modules.options.link-logs-architecture``). 출처 종류 기본값은 출처 id 그대로다
    # (출처 id = 등록 이름). 같은 형식을 다른 id로 더한 출처만 여기서 종류를 정한다.

    model_config = ConfigDict(extra="forbid")

    source_kinds: dict[str, str] = Field(
        title="출처 종류 대응",
        json_schema_extra=x_ui(tier="advanced", example={"my-log-copy": "my-log-kind"}),
        default_factory=dict,
        description=(
            "로그 출처 id → 구조도 프로필의 출처 종류(coverage·source_priority 키). "
            "적지 않은 출처는 출처 id를 종류로 쓴다."
        ),
    )
    cache_scopes: int = Field(
        title="캐시할 범위 수",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
        default=DEFAULT_CACHE_SCOPES,
        ge=0,
        description=(
            "구조도를 그린 범위(필터)를 몇 개까지 기억할지. 기억한 범위는 다음 호출에서 새 "
            "이벤트만 읽는다. 0이면 캐시하지 않는다."
        ),
    )
    cache_events: int = Field(
        title="캐시 이벤트 상한",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
        default=DEFAULT_CACHE_EVENTS,
        ge=0,
        description="기억한 범위들의 이벤트 수 합의 상한(넘으면 오래 쓰지 않은 범위부터 버린다).",
    )
    cache_profiles: int = Field(
        title="범위마다 기억할 판정 수",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
        default=DEFAULT_CACHE_PROFILES,
        ge=1,
        description=(
            "범위 하나에 프로필(내용·연산자·오류 범주가 같은 것)별 판정 결과를 몇 개까지 "
            "기억할지. 판정 결과는 이벤트 수만큼 커서, 넘으면 오래 쓰지 않은 것부터 버린다."
        ),
    )
    page_size: int = Field(
        title="한 번에 읽을 이벤트 수",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=10_000,
        description=(
            "범위 이벤트를 색인에서 읽을 때 쪽 하나의 크기. 클수록 질의 수가 줄고 한 번에 "
            "메모리에 올리는 이벤트가 는다."
        ),
    )
    unlisted_paths: list[str] = Field(
        title="목록에 없는 경로",
        json_schema_extra=x_ui(tier="advanced", example=["/detail", "/raw"]),
        default_factory=lambda: list(DEFAULT_UNLISTED_PATHS),
        description=(
            "구조도는 목록용 이벤트만 보므로 이 경로(예: /detail) 아래 값을 보는 프로필 "
            "조건은 맞지 않는다. 프로필 검사가 이런 조건을 경고한다. 비우면 경고하지 않는다."
        ),
    )


__all__ = [
    "DEFAULT_CACHE_EVENTS",
    "DEFAULT_CACHE_PROFILES",
    "DEFAULT_CACHE_SCOPES",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_UNLISTED_PATHS",
    "LogsArchitectureSettings",
]
