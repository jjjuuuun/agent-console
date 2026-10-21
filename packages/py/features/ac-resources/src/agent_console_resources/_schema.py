"""JSON Schema 검사(jsonschema 라이브러리를 이 모듈 안에 가둔다).

외부 `$ref`(URL·파일)는 가져오지 않는다. 로컬 `#/...`·`$defs`만 해석한다.

위반 메시지는 jsonschema의 `err.message`를 쓰지 않고 **스키마 쪽 정보(검사 종류·기대값)만으로**
만든다. `err.message`는 입력값을 그대로 담으므로 평문 비밀이 이슈·로그로 새어 나갈 수 있다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import jsonschema
import referencing
import referencing.exceptions

__all__ = ["ConfigViolation", "InvalidConfigSchemaError", "check_config_schema", "validate_config"]

_OFFLINE: referencing.Registry[Any] = referencing.Registry()


@dataclass(frozen=True, slots=True)
class ConfigViolation:
    """config 값의 스키마 위반 하나. `pointer`는 config 기준 JSON Pointer."""

    pointer: str
    message: str
    """입력값을 담지 않는 메시지(스키마의 기대값만)."""
    validator: str = ""
    """위반한 JSON Schema 키워드(예: `type`, `enum`)."""


class InvalidConfigSchemaError(ValueError):
    """config_schema 자체가 잘못되었다."""


def _pointer(parts: Iterable[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


_SCALAR = (str, int, float, bool)
_LIMITS = {
    "minLength": "길이가 {v}자 이상이어야 합니다",
    "maxLength": "길이가 {v}자 이하여야 합니다",
    "minimum": "{v} 이상이어야 합니다",
    "maximum": "{v} 이하여야 합니다",
    "exclusiveMinimum": "{v}보다 커야 합니다",
    "exclusiveMaximum": "{v}보다 작아야 합니다",
    "multipleOf": "{v}의 배수여야 합니다",
    "minItems": "항목이 {v}개 이상이어야 합니다",
    "maxItems": "항목이 {v}개 이하여야 합니다",
    "minProperties": "키가 {v}개 이상이어야 합니다",
    "maxProperties": "키가 {v}개 이하여야 합니다",
    "format": "형식 {v}에 맞지 않습니다",
}


def _safe_message(err: jsonschema.exceptions.ValidationError) -> str:
    """입력값(`err.instance`)을 쓰지 않는 위반 메시지. 스키마의 기대값만 쓴다."""
    kind = str(err.validator)
    expected = err.validator_value
    if kind == "type":
        names = expected if isinstance(expected, list) else [expected]
        return f"형식이 맞지 않습니다(기대: {', '.join(map(str, names))})"
    if kind == "enum" and isinstance(expected, list):
        allowed = [v for v in expected if isinstance(v, _SCALAR) or v is None]
        return f"허용된 값이 아닙니다(허용: {', '.join(map(str, allowed))})"
    if kind == "const":
        return "정해진 값과 다릅니다"
    if kind == "pattern":
        return "정해진 형식(pattern)에 맞지 않습니다"
    if kind == "required" and isinstance(expected, list):
        present = err.instance if isinstance(err.instance, Mapping) else {}
        missing = [str(k) for k in expected if k not in present]  # 스키마에 적힌 이름만
        return f"필수 항목이 없습니다: {', '.join(missing)}"
    if kind in ("additionalProperties", "unevaluatedProperties", "propertyNames"):
        return "정의되지 않은 키는 쓸 수 없습니다"
    if kind in ("additionalItems", "unevaluatedItems", "items", "prefixItems"):
        return "허용되지 않은 항목이 있습니다"
    if kind == "uniqueItems":
        return "항목이 겹칩니다"
    if kind in _LIMITS and isinstance(expected, _SCALAR):
        return _LIMITS[kind].format(v=expected)
    if kind in ("anyOf", "oneOf", "allOf", "not", "if", "then", "else", "dependentRequired"):
        return f"조건({kind})을 만족하지 않습니다"
    return f"스키마 검사({kind})를 통과하지 못했습니다"


def check_config_schema(schema: Mapping[str, Any]) -> None:
    """스키마가 메타스키마에 맞는지 검사한다.

    Raises:
        InvalidConfigSchemaError: 스키마가 잘못되었을 때.
    """
    doc = dict(schema)
    cls = jsonschema.validators.validator_for(doc)
    try:
        cls.check_schema(doc)
    except jsonschema.exceptions.SchemaError as exc:
        raise InvalidConfigSchemaError(str(exc.message)) from exc


def validate_config(schema: Mapping[str, Any], value: Any) -> list[ConfigViolation]:
    """`value`를 `schema`로 검사해 위반 목록(포인터 순)을 돌려준다. 빈 스키마는 모두 허용.

    메시지에는 입력값이 들어가지 않는다(비밀 누출 방지). 위치는 `pointer`로 알린다.

    Raises:
        InvalidConfigSchemaError: 스키마가 잘못되었거나 `$ref`를 풀 수 없을 때.
    """
    doc = dict(schema)
    check_config_schema(doc)
    validator = jsonschema.validators.validator_for(doc)(doc, registry=_OFFLINE)
    try:
        found = [
            ConfigViolation(_pointer(err.absolute_path), _safe_message(err), str(err.validator))
            for err in validator.iter_errors(value)
        ]
    except referencing.exceptions.Unresolvable as exc:
        raise InvalidConfigSchemaError(f"$ref를 해석할 수 없습니다: {exc}") from exc
    found.sort(key=lambda v: (v.pointer, v.message))
    return found
