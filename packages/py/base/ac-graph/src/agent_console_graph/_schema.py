"""JSON Schema 검사 어댑터(jsonschema 라이브러리를 이 모듈 안에 가둔다)."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import jsonschema
import referencing
import referencing.exceptions


@dataclass(frozen=True)
class SchemaViolation:
    """스키마 위반 하나. `pointer`는 검사 대상 문서 기준 RFC 6901 JSON Pointer."""

    pointer: str
    message: str
    validator: str
    schema_path: str


class InvalidSchemaError(Exception):
    """스키마 자체가 잘못되었다(메타스키마 위반 또는 해석할 수 없는 `$ref`)."""


type SchemaChecker = Callable[[Any], list[SchemaViolation]]
"""컴파일된 검사기: 값 → 위반 목록. `$ref`를 풀 수 없으면 `InvalidSchemaError`."""


# 문서가 하나도 없고 retrieve도 기본값(항상 NoSuchResource)인 레지스트리:
# 외부 문서(URL·파일)는 절대 가져오지 않는다. 로컬 `#/...`·`$defs`만 해석된다.
_OFFLINE_REGISTRY: referencing.Registry[Any] = referencing.Registry()


def compile_schema(schema: Mapping[str, Any]) -> SchemaChecker:
    """스키마를 검사하고 재사용 가능한 검사기를 만든다. 빈 스키마는 모든 값을 허용한다.

    스키마의 `$schema`로 초안을 고르고, 없으면 라이브러리 최신 초안을 쓴다.
    외부 `$ref`(URL 등)는 가져오지 않고 해석 불가로 처리한다. 검사기의 결과는 포인터 순.

    Raises:
        InvalidSchemaError: 스키마 자체가 잘못되었을 때(메타스키마 위반).
    """
    doc = dict(schema)
    cls = jsonschema.validators.validator_for(doc)
    try:
        cls.check_schema(doc)
    except jsonschema.exceptions.SchemaError as exc:
        raise InvalidSchemaError(str(exc.message)) from exc
    validator = cls(doc, registry=_OFFLINE_REGISTRY)

    def check(instance: Any) -> list[SchemaViolation]:
        try:
            found = [
                SchemaViolation(
                    pointer=to_pointer(err.absolute_path),
                    message=str(err.message),
                    validator=str(err.validator),
                    schema_path=to_pointer(err.absolute_schema_path),
                )
                for err in validator.iter_errors(instance)
            ]
        except referencing.exceptions.Unresolvable as exc:
            raise InvalidSchemaError(f"$ref를 해석할 수 없습니다: {exc}") from exc
        found.sort(key=lambda v: (v.pointer, v.schema_path, v.message))
        return found

    return check


def check_instance(schema: Mapping[str, Any], instance: Any) -> list[SchemaViolation]:
    """`compile_schema(schema)(instance)`의 줄임.

    Raises:
        InvalidSchemaError: 스키마가 잘못되었거나 `$ref`를 해석할 수 없을 때.
    """
    return compile_schema(schema)(instance)


def to_pointer(parts: Iterable[Any]) -> str:
    """경로 조각 → RFC 6901 JSON Pointer(`~`→`~0`, `/`→`~1`). 빈 경로는 ``""``."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)
