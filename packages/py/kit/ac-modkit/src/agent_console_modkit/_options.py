"""모듈 옵션 읽기 전용 보기(design §5.2R UX-B5): 스키마·가린 지금 값.

모듈 옵션(설치자 설정 ``modules.options.<id>``)은 설정 파일에서만 바꾼다. 이 파일은 그 값을
**보여 주기만** 한다. 쓰기는 없다. 기능·모듈 이름을 모르고, 모듈 서술자의
``settings_schema``(Pydantic 모델)만 본다.

가리기(안전한 쪽 기본값):

- 스키마가 비밀이라고 말하는 필드(``format: password``·``writeOnly``·``x-secret: true`` — Pydantic
  ``SecretStr``은 앞의 둘을 낸다)는 언제나 가린다.
- ``secret_paths``(주입): 값에서 평문 비밀로 의심되는 위치(JSON Pointer)를 돌려주는 함수. 호스트가
  비밀 규칙을 넘긴다(이 패키지는 비밀 규칙 패키지에 의존하지 않는다).
- ``hide_paths``가 참이면 스키마 ``format: path`` 필드(파일·폴더 경로)도 가린다
  (호스트 경로 표시 끔).

예: README "모듈 옵션 읽기 전용 보기".
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ._module import ModuleDescriptor

OPTIONS_MASK = "[REDACTED]"
"""modkit의 가림 문자열(하나뿐: 옵션 보기 값, 호스트 로그 가림 ``host.REDACTED``가 이것을 쓴다).
비밀 규칙 패키지에 의존하지 않으므로, 호스트는 그 패키지의 가림 문자열을 ``mask=``로 넘겨 맞춘다."""

SECRET_SCHEMA_KEY = "x-secret"
"""스키마 속성 확장 키: 참이면 그 필드 값을 가린다(``SecretStr``을 쓰지 않는 비밀 필드용)."""

type SecretPathFinder = Callable[[Any], Iterable[str]]
"""값(JSON) → 평문 비밀로 의심되는 위치(JSON Pointer, 예: ``/env/API_KEY``) 목록."""


@dataclass(frozen=True)
class ModuleOptions:
    """모듈 옵션 읽기 전용 보기 하나.

    Attributes:
        module_id: 모듈 id.
        schema: 옵션 JSON Schema. None = 모듈이 설정을 받지 않는다(스키마 없음).
        values: 지금 값(기본값 포함, JSON 값). 가린 위치는 ``mask`` 문자열이다.
        masked: 가린 위치(JSON Pointer, 정렬).
        valid: 설정이 스키마 검증을 통과했는지. 거짓이면 ``values``는 설정 원문(가림 적용)이다.
    """

    module_id: str
    schema: dict[str, Any] | None
    values: dict[str, Any]
    masked: tuple[str, ...] = ()
    valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        """JSON 본문(``{module_id, schema, values}``). 조각은 호스트가 붙인다."""
        return {"module_id": self.module_id, "schema": self.schema, "values": self.values}


def _json(value: Any) -> Any:
    """설정 원문을 JSON 값으로(경로 등은 문자열로)."""
    return json.loads(json.dumps(value, default=str))


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _resolve(node: Any, root: Mapping[str, Any]) -> Mapping[str, Any]:
    """``$ref``(문서 안 ``#/$defs/...``)를 따라간다. 못 풀면 빈 객체."""
    seen = 0
    while isinstance(node, Mapping) and isinstance(node.get("$ref"), str) and seen < 32:
        ref = str(node["$ref"])
        if not ref.startswith("#/"):
            return {}
        target: Any = root
        for part in ref[2:].split("/"):
            target = target.get(_unescape(part)) if isinstance(target, Mapping) else None
        node = target
        seen += 1
    return node if isinstance(node, Mapping) else {}


def _variants(node: Mapping[str, Any], root: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """노드와 ``anyOf``·``oneOf``·``allOf`` 갈래(풀어 낸 것)."""
    out = [node]
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in node.get(key, ()) or ():
            out.append(_resolve(sub, root))
    return out


def _flagged(node: Mapping[str, Any], root: Mapping[str, Any], *, hide_paths: bool) -> bool:
    for v in _variants(node, root):
        if v.get(SECRET_SCHEMA_KEY) is True or v.get("writeOnly") is True:
            return True
        if v.get("format") == "password":
            return True
        if hide_paths and v.get("format") == "path":
            return True
    return False


def _schema_pointers(
    schema_node: Any,
    value: Any,
    root: Mapping[str, Any],
    at: str,
    out: list[str],
    *,
    hide_paths: bool,
) -> None:
    node = _resolve(schema_node, root)
    if not node or value is None:
        return
    if at and _flagged(node, root, hide_paths=hide_paths):
        out.append(at)
        return
    for v in _variants(node, root):
        if isinstance(value, Mapping):
            props = v.get("properties")
            extra = v.get("additionalProperties")
            for key, item in value.items():
                sub = props.get(key) if isinstance(props, Mapping) else None
                if sub is None and isinstance(extra, Mapping):
                    sub = extra
                if sub is not None:
                    where = f"{at}/{_escape(str(key))}"
                    _schema_pointers(sub, item, root, where, out, hide_paths=hide_paths)
        elif isinstance(value, list):
            items = v.get("items")
            if isinstance(items, Mapping):
                for i, item in enumerate(value):
                    _schema_pointers(items, item, root, f"{at}/{i}", out, hide_paths=hide_paths)


def _mask_at(values: Any, pointer: str, mask: str) -> bool:
    """``pointer`` 자리 값을 ``mask``로 바꾼다(없는 위치면 거짓)."""
    parts = [_unescape(p) for p in pointer.split("/")[1:]]
    if not parts:
        return False
    target = values
    for part in parts[:-1]:
        if isinstance(target, dict) and part in target:
            target = target[part]
        elif isinstance(target, list) and part.isdigit() and int(part) < len(target):
            target = target[int(part)]
        else:
            return False
    last = parts[-1]
    if isinstance(target, dict) and last in target:
        if target[last] is None:
            return False
        target[last] = mask
        return True
    if isinstance(target, list) and last.isdigit() and int(last) < len(target):
        target[int(last)] = mask
        return True
    return False


def _normalize_pointer(raw: str) -> str:
    """비밀 규칙 결과 위치(``path=`` 접두가 붙을 수 있다) → JSON Pointer."""
    text = raw[len("path=") :] if raw.startswith("path=") else raw
    return text if text.startswith("/") else f"/{text}"


def mask_values(
    values: Mapping[str, Any],
    schema: Mapping[str, Any] | None,
    *,
    secret_paths: SecretPathFinder | None = None,
    hide_paths: bool = False,
    mask: str = OPTIONS_MASK,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """값 사본에서 비밀(과 선택적으로 경로)을 가린다.

    Args:
        values: JSON 값(객체).
        schema: 그 값의 JSON Schema(없으면 스키마 표시로 가리지 않는다).
        secret_paths: 평문 비밀 의심 위치 함수(주입). 실패하면 값 전체를 가린다(안전한 쪽).
        hide_paths: 참이면 스키마 ``format: path`` 필드도 가린다.
        mask: 가린 자리에 넣을 문자열.

    Returns:
        (가린 사본, 가린 위치 정렬 목록).
    """
    copy: dict[str, Any] = _json(dict(values))
    pointers: list[str] = []
    if schema:
        _schema_pointers(schema, copy, schema, "", pointers, hide_paths=hide_paths)
    if secret_paths is not None:
        try:
            found = [_normalize_pointer(getattr(f, "path", f)) for f in secret_paths(copy)]
        except Exception:
            # 판정 실패 = 모든 잎을 가린다(값이 새는 쪽보다 안전).
            return {k: mask for k in copy}, tuple(sorted(f"/{_escape(k)}" for k in copy))
        pointers.extend(found)
    done = sorted({p for p in pointers if _mask_at(copy, p, mask)})
    return copy, tuple(done)


def read_module_options(
    descriptor: ModuleDescriptor,
    raw: Mapping[str, Any] | None = None,
    *,
    secret_paths: SecretPathFinder | None = None,
    hide_paths: bool = False,
    mask: str = OPTIONS_MASK,
) -> ModuleOptions:
    """모듈 하나의 옵션 보기(읽기 전용, 부작용 없음).

    Args:
        descriptor: 모듈 서술자(``settings_schema``가 옵션 모델).
        raw: 설치자 설정 ``modules.options.<id>``(없으면 빈 값 = 기본값).
        secret_paths: 평문 비밀 의심 위치 함수(주입, 예: 비밀 규칙의 ``find_suspected``).
        hide_paths: 참이면 경로 필드도 가린다.
        mask: 가린 자리 문자열.

    Returns:
        ``ModuleOptions``. 스키마가 없으면 ``schema=None``이고 값은 설정 원문(가림 적용)이다.
        검증에 실패하면 ``valid=False``이고 값은 설정 원문(가림 적용)이다.
    """
    model = descriptor.settings_schema
    source = dict(raw or {})
    if model is None:
        values, masked = mask_values(source, None, secret_paths=secret_paths, mask=mask)
        return ModuleOptions(descriptor.id, None, values, masked)
    schema: dict[str, Any] = model.model_json_schema()
    valid = True
    try:
        current: dict[str, Any] = model.model_validate(source).model_dump(mode="json")
    except ValidationError:
        current, valid = source, False
    values, masked = mask_values(
        current, schema, secret_paths=secret_paths, hide_paths=hide_paths, mask=mask
    )
    return ModuleOptions(descriptor.id, schema, values, masked, valid)


__all__ = [
    "OPTIONS_MASK",
    "SECRET_SCHEMA_KEY",
    "ModuleOptions",
    "SecretPathFinder",
    "mask_values",
    "read_module_options",
]
