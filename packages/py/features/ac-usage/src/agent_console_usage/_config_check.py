"""출처 설정(`usage.sources[].config`) 검증: 출처 디스크립터 `config_schema`로 본다.

수집(`UsageService`)·저장 전 검사·서버 경고가 같은 규칙을 쓴다. 이슈·오류에는 위치(JSON Pointer)와
어긴 스키마 키워드 이름만 담는다. jsonschema 원문 메시지는 입력 값을 담으므로 내보내지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from agent_console_contracts import (
    ErrorCodes,
    ErrorInfo,
    Issue,
    IssueSeverity,
    JsonObject,
    UsageSettings,
    UsageSourceDescriptor,
)

__all__ = [
    "SOURCE_CONFIG_INVALID",
    "SOURCE_SCHEMA_INVALID",
    "config_error",
    "source_config_issues",
]

SOURCE_CONFIG_INVALID = "usage.source_config_invalid"
"""`source_config_issues` 이슈 코드: 출처 설정이 그 출처의 `config_schema`에 맞지 않는다."""

SOURCE_SCHEMA_INVALID = "usage_source_schema_invalid"
"""출처 디스크립터의 `config_schema` 자체가 잘못됐을 때 `UsageSourceInfo.error.code`."""

_MAX_ISSUES_PER_SOURCE = 20
"""출처 하나에서 내는 이슈 상한(거대한 잘못된 설정이 응답을 부풀리지 않게)."""


def _pointer(parts: Sequence[object]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _violations(
    config: Mapping[str, Any], schema: Mapping[str, Any]
) -> Iterator[tuple[list[object], str]]:
    """(설정 안 위치, 어긴 키워드). 스키마 자체가 틀리면 `jsonschema.SchemaError`."""
    import jsonschema  # 지연 import: 검증을 쓰지 않는 경로를 가볍게

    plain = dict(schema)
    cls = jsonschema.validators.validator_for(plain)
    cls.check_schema(plain)
    for err in sorted(cls(plain).iter_errors(config), key=lambda e: list(map(str, e.path))):
        yield list(err.absolute_path), str(err.validator)


def config_error(config: JsonObject, schema: Mapping[str, Any] | None) -> ErrorInfo | None:
    """출처 하나의 설정 오류(`UsageSourceInfo.error` 모양). 맞으면 `None`.

    Args:
        config: 출처 설정.
        schema: 출처 `config_schema`(없으면 아무 설정이나 맞다).

    Returns:
        첫 위반의 `ErrorInfo`(`details.path` = 설정 안 키 경로 목록, `details.validator` = 키워드)
        또는 스키마 자체가 잘못됐으면 `SOURCE_SCHEMA_INVALID` 오류. 값은 담지 않는다.
    """
    import jsonschema

    try:
        first = next(_violations(config, schema or {}), None)
    except jsonschema.SchemaError:
        return ErrorInfo(
            code=SOURCE_SCHEMA_INVALID,
            message="출처의 설정 스키마가 잘못돼 설정을 검증할 수 없습니다",
        )
    if first is None:
        return None
    path, validator = first
    return ErrorInfo(
        code=ErrorCodes.VALIDATION_FAILED,
        message="출처 설정이 맞지 않습니다(위치·규칙은 details)",
        details={"path": [str(p) for p in path], "validator": validator},
    )


def source_config_issues(
    settings: UsageSettings,
    descriptors: Mapping[str, UsageSourceDescriptor],
    *,
    base_path: str = "/usage/sources",
    severity: IssueSeverity = "error",
) -> list[Issue]:
    """`settings.sources[i].config`를 그 출처 `config_schema`로 검증한 이슈.

    Args:
        settings: 사용량 설정.
        descriptors: 출처 id → 디스크립터(지금 쓸 수 있는 출처). 여기 없는 id(등록되지 않았거나
            연동이 꺼진 런타임 출처)는 검증할 수 없으므로 건너뛴다 — 그 출처가 나타나면 수집·경고가
            다시 본다.
        base_path: 이슈 `path`의 접두(JSON Pointer). 워크스페이스 설정 문서 기준이 기본이다.
        severity: 이슈 심각도(`"error"`면 저장 전 검사가 거부한다, `"warning"`은 알림용).

    Returns:
        `Issue` 목록. `code` = `SOURCE_CONFIG_INVALID`, `path` = 설정 안 위치,
        `details` = `{source, validator}`. 메시지에 값·스키마 원문이 없다. 스키마 자체가 잘못된
        출처는 사용자 설정 문제가 아니므로 이슈를 내지 않는다.
    """
    import jsonschema

    out: list[Issue] = []
    for index, item in enumerate(settings.sources):
        descriptor = descriptors.get(item.id)
        if descriptor is None:
            continue
        prefix = f"{base_path}/{index}/config"
        try:
            found = list(_violations(item.config, descriptor.config_schema or {}))
        except jsonschema.SchemaError:
            continue
        for path, validator in found[:_MAX_ISSUES_PER_SOURCE]:
            out.append(
                Issue(
                    severity=severity,
                    code=SOURCE_CONFIG_INVALID,
                    message=(
                        f"사용량 출처 {item.id}의 설정이 그 출처의 설정 스키마에 맞지 않습니다"
                        f"(규칙: {validator})"
                    ),
                    path=prefix + _pointer(path),
                    details={"source": item.id, "validator": validator},
                )
            )
    return out
