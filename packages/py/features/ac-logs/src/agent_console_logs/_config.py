"""설정 스키마 기본값 채우기와 검증(출처·분류기 `config_schema`)."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import jsonschema

from ._values import JsonValue

__all__ = ["ConfigError", "effective_config"]


class ConfigError(ValueError):
    """설정이 `config_schema`에 맞지 않는다. `path`는 문제 위치(`a.b.0`)."""

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(message)
        self.path = path


def _fill_defaults(schema: Mapping[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties")
    if not isinstance(props, Mapping):
        return value
    for name, sub in props.items():
        if not isinstance(sub, Mapping):
            continue
        if name not in value and "default" in sub:
            value[name] = copy.deepcopy(sub["default"])
        elif isinstance(value.get(name), dict) and sub.get("type") == "object":
            value[name] = _fill_defaults(sub, dict(value[name]))
    return value


def effective_config(
    schema: Mapping[str, JsonValue], config: Mapping[str, JsonValue] | None
) -> dict[str, JsonValue]:
    """스키마의 `properties.*.default`로 빠진 값을 채우고 검증한다(객체 속성은 재귀).

    Args:
        schema: JSON Schema(빈 객체면 검증 없이 그대로).
        config: 사용자 설정(없으면 빈 객체).

    Returns:
        기본값을 채운 새 객체.

    Raises:
        ConfigError: 스키마 검증 실패.
    """
    value = _fill_defaults(schema, dict(config or {}))
    if schema:
        try:
            jsonschema.validate(value, dict(schema))
        except jsonschema.ValidationError as exc:
            path = ".".join(str(p) for p in exc.absolute_path)
            raise ConfigError(exc.message, path) from None
        except jsonschema.SchemaError as exc:
            raise ConfigError(f"설정 스키마 오류: {exc.message}") from None
    return value
