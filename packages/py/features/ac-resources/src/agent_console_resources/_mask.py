"""`x-secret` 위치의 평문 값 가리기(표시용 안전망, 1R.37 후속).

저장 검사(`validate_resource`·`validate_attachment`)가 평문을 막지만, 그 전에 저장된 데이터나
손으로 고친 파일은 남아 있을 수 있다. 유효 설정·묶음 미리보기처럼 config 값을 내보내는
응답은 이 함수로 한 번 더 가린다. `secret://` 참조는 그대로 둔다(값이 아니라 이름이다).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts import Resource, ResourceAttachment
from agent_console_registry import Registry, UnknownExtensionError

from ._base import SECRET_SCHEMA_KEY, is_secret_ref
from ._interfaces import Content, ContentFiles, FileContentLookup, ResourceLookup, ResourceType

SECRET_MASK = "***"
"""가린 값 자리에 넣는 문자열(참조 형식이 아니므로 종류 검사에서 평문 오류로 남는다)."""

_COMBINATORS = ("allOf", "anyOf", "oneOf")


def _mask(value: Any, schema: Any) -> Any:
    if not isinstance(schema, Mapping):
        return value
    if schema.get(SECRET_SCHEMA_KEY) is True:
        if value is None or is_secret_ref(value):
            return value
        return SECRET_MASK
    out = value
    for key in _COMBINATORS:
        for sub in schema.get(key) or ():
            out = _mask(out, sub)
    if isinstance(out, dict):
        props = schema.get("properties")
        props = props if isinstance(props, Mapping) else {}
        extra = schema.get("additionalProperties")
        masked: dict[str, Any] = {}
        for k, v in out.items():
            if k in props:
                masked[k] = _mask(v, props[k])
            elif isinstance(extra, Mapping):
                masked[k] = _mask(v, extra)
            else:
                masked[k] = v
        return masked
    if isinstance(out, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            return [_mask(v, items) for v in out]
    return out


def mask_plain_secrets(value: Any, schema: Mapping[str, Any]) -> Any:
    """`schema`에서 `x-secret: true`인 위치의 값 중 `secret://` 참조가 아닌 것을 `***`로 바꾼 사본.

    따라가는 키워드: `properties`, `additionalProperties`(객체), `items`(객체 스키마),
    `allOf`·`anyOf`·`oneOf`. `$ref`는 따라가지 않는다. 원본은 바꾸지 않는다.
    """
    return _mask(value, schema)


def _schema_of(types: Registry[ResourceType], type_id: str) -> Mapping[str, Any] | None:
    try:
        return types.get(type_id).descriptor.config_schema
    except UnknownExtensionError:
        return None


def mask_resource(resource: Resource, types: Registry[ResourceType]) -> Resource:
    """리소스 config의 `x-secret` 평문을 가린 사본(종류를 모르면 그대로)."""
    schema = _schema_of(types, resource.type)
    if schema is None:
        return resource
    config = mask_plain_secrets(resource.config, schema)
    return resource if config == resource.config else resource.model_copy(update={"config": config})


def mask_attachment(
    attachment: ResourceAttachment, *, types: Registry[ResourceType], resources: ResourceLookup
) -> ResourceAttachment:
    """첨부 `config_override`의 `x-secret` 평문을 가린 사본(리소스·종류를 모르면 그대로)."""
    override = attachment.config_override
    if not override:
        return attachment
    resource = resources.get_resource(attachment.ref)
    schema = _schema_of(types, resource.type) if resource is not None else None
    if schema is None:
        return attachment
    masked = mask_plain_secrets(override, schema)
    if masked == override:
        return attachment
    return attachment.model_copy(update={"config_override": masked})


class MaskedResources:
    """`ResourceLookup` 감싸기: 돌려주는 리소스 config의 `x-secret` 평문을 가린다(본문은 그대로)."""

    def __init__(self, inner: ResourceLookup, types: Registry[ResourceType]) -> None:
        self._inner = inner
        self._types = types

    def get_resource(self, ref: str) -> Resource | None:
        found = self._inner.get_resource(ref)
        return mask_resource(found, self._types) if found is not None else None

    def read_content(self, resource: Resource) -> Content:
        return self._inner.read_content(resource)

    def read_files(self, resource: Resource) -> ContentFiles | None:
        """안쪽 조회가 여러 파일 본문을 읽을 수 있으면 그대로(본문은 가리지 않는다)."""
        if isinstance(self._inner, FileContentLookup):
            return self._inner.read_files(resource)
        return None
