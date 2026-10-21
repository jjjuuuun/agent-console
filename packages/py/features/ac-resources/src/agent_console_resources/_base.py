"""리소스 종류 구현 도우미: 스키마 검사 베이스, 설정 덮어쓰기, 비밀 참조 검사."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

from agent_console_contracts import Issue, Resource, ResourceAttachment, ResourceTypeDescriptor

from ._interfaces import Content, ContributeContext, Contribution
from ._schema import InvalidConfigSchemaError, validate_config

__all__ = [
    "PLAIN_SECRET",
    "SECRET_REF_PATTERN",
    "SECRET_REF_PREFIX",
    "SchemaResourceType",
    "content_text",
    "effective_resource",
    "find_plain_secrets",
    "find_schema_plain_secrets",
    "is_secret_ref",
]

SECRET_REF_PREFIX = "secret://"
"""비밀 참조 접두어. 리소스에는 비밀 값 대신 이 참조만 둔다."""

SECRET_REF_PATTERN = r"^secret://[A-Za-z0-9_.\-/]+$"
"""비밀 참조 형식 정규식(스키마 `pattern`에도 쓸 수 있다. 위반 메시지에는 값이 담기지 않는다)."""

_SECRET_RE = re.compile(SECRET_REF_PATTERN)


SECRET_SCHEMA_KEY = "x-secret"
"""config 스키마 주석: `{"x-secret": true}`가 붙은 스키마 위치의 값은 비밀이다(`secret://` 참조만).

화면은 이 주석으로 비밀 입력 칸(가림·참조 고르기)을 그린다. 플러그인·선언형 종류 모두 쓸 수 있다.
JSON Schema 검사기는 모르는 키워드로 무시한다. 평문 거부는 `SchemaResourceType.validate`가
일반 규칙으로 한다(`find_schema_plain_secrets` → `resource.plain_secret` error, 2R.4) — 선언형
종류도 `pattern`을 따로 쓰지 않아도 된다."""

PLAIN_SECRET = "resource.plain_secret"
"""`x-secret` 위치(또는 종류가 정한 비밀 위치)에 참조가 아닌 값이 있을 때의 이슈 코드."""

PLAIN_SECRET_MESSAGE = "비밀 값은 secret://이름 참조로만 넣을 수 있습니다"

_COMBINATORS = ("allOf", "anyOf", "oneOf")


def is_secret_ref(value: Any) -> bool:
    """`secret://이름` 형식 문자열이면 참."""
    return isinstance(value, str) and _SECRET_RE.fullmatch(value) is not None


def find_plain_secrets(config: Mapping[str, Any], fields: tuple[str, ...]) -> Iterator[str]:
    """`config[field]` 객체의 값 중 비밀 참조가 아닌 것의 JSON Pointer를 낸다.

    예: `fields=("env", "headers")` → `/env/API_KEY`(값이 평문일 때).
    """
    for name in fields:
        section = config.get(name)
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            if not is_secret_ref(value):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                yield f"/{name}/{escaped}"


def find_schema_plain_secrets(value: Any, schema: Mapping[str, Any]) -> list[str]:
    """`schema`의 `x-secret: true` 위치에 있는 값 중 `secret://` 참조가 아닌 것의 JSON Pointer.

    따라가는 키워드는 `mask_plain_secrets`와 같다(`properties`, `additionalProperties`, `items`,
    `allOf`·`anyOf`·`oneOf`, `$ref`는 따라가지 않음). null은 값이 없는 것으로 본다.
    """
    return list(dict.fromkeys(_plain_at(value, schema, "")))


def _plain_at(value: Any, schema: Any, pointer: str) -> Iterator[str]:
    if not isinstance(schema, Mapping):
        return
    if schema.get(SECRET_SCHEMA_KEY) is True:
        if value is not None and not is_secret_ref(value):
            yield pointer
        return
    for key in _COMBINATORS:
        for sub in schema.get(key) or ():
            yield from _plain_at(value, sub, pointer)
    if isinstance(value, dict):
        props = schema.get("properties")
        props = props if isinstance(props, Mapping) else {}
        extra = schema.get("additionalProperties")
        for k, v in value.items():
            at = f"{pointer}/{str(k).replace('~', '~0').replace('/', '~1')}"
            if k in props:
                yield from _plain_at(v, props[k], at)
            elif isinstance(extra, Mapping):
                yield from _plain_at(v, extra, at)
    elif isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, v in enumerate(value):
                yield from _plain_at(v, items, f"{pointer}/{index}")


def effective_resource(resource: Resource, attachment: ResourceAttachment | None) -> Resource:
    """첨부의 `config_override`를 config에 얕게 덮어쓴 사본(원본 불변)."""
    if attachment is None or not attachment.config_override:
        return resource
    config = {**resource.config, **attachment.config_override}
    return resource.model_copy(update={"config": config})


def content_text(content: Content) -> str | None:
    """본문을 문자열로(바이트는 UTF-8, 깨진 바이트는 대체 문자). 여러 파일 본문이면 None."""
    if content is None:
        return None
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    if isinstance(content, str):
        return content
    return None


class SchemaResourceType:
    """`descriptor.config_schema`로 config를 검사하는 리소스 종류 베이스.

    하위 클래스는 클래스 속성 `descriptor`와 `contribute`를 정의하고, 추가 검사가 있으면
    `extra_issues`를 덮어쓴다. entry point에는 클래스를 등록하면 된다(인자 없이 인스턴스화).
    스키마의 `x-secret: true` 위치에 평문이 있으면 일반 규칙으로 `resource.plain_secret` error를
    낸다(종류가 `extra_issues`로 같은 위치를 이미 보고하면 한 번만).
    """

    descriptor: ResourceTypeDescriptor

    def validate(self, resource: Resource) -> list[Issue]:
        """config 스키마 위반(`resource.invalid_config`), `x-secret` 위치의 평문
        (`resource.plain_secret`), `extra_issues`를 돌려준다(모두 error, 값은 메시지에 없음)."""
        details = {"resource": resource.id, "resource_type": resource.type}
        issues: list[Issue] = []
        try:
            violations = validate_config(self.descriptor.config_schema, resource.config)
        except InvalidConfigSchemaError as exc:
            return [
                Issue(
                    severity="error",
                    code="resource.invalid_type_schema",
                    message=f"종류 {self.descriptor.id!r}의 설정 스키마가 잘못됐습니다: {exc}",
                    details=details,
                )
            ]
        for v in violations:
            issues.append(
                Issue(
                    severity="error",
                    code="resource.invalid_config",
                    message=v.message,
                    path=v.pointer,
                    details=details,
                )
            )
        extra = self.extra_issues(resource)
        reported = {(i.code, i.path) for i in extra}
        for pointer in find_schema_plain_secrets(resource.config, self.descriptor.config_schema):
            if (PLAIN_SECRET, pointer) in reported:
                continue
            issues.append(
                Issue(
                    severity="error",
                    code=PLAIN_SECRET,
                    message=PLAIN_SECRET_MESSAGE,
                    path=pointer,
                    details=details,
                )
            )
        issues.extend(extra)
        return issues

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """종류별 추가 검사(기본 없음)."""
        return []

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """하위 클래스가 구현한다."""
        raise NotImplementedError
