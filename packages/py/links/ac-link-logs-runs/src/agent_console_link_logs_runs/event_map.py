"""플랫폼 실행 이벤트 형식 → 로그 이벤트 대응표(데이터, design §4R.2).

기본값은 패키지 데이터 ``data/run_event_map.yaml``이고, 설정
``logs.sources[id=platform-runs].config.event_map``이 키(형식)별로 통째로 덮어쓴다. 코드는 형식
이름·범주 이름을 모른다(맞는 규칙이 하나도 없을 때만 ``fallback_category``, 기본 ``other``).

- 키: 형식 이름 또는 글롭(``*``·``?``). 정확한 이름이 먼저, 그다음 글롭은 긴 것부터.
- 문자열 값은 틀이다: ``{/JSON 포인터}``(이벤트 JSON 기준)와 이름 ``{type}``·``{node}``·
  ``{parent_node}``·``{thread}``·``{actor}``·``{run_id}``를 채운다. 없는 값은 빈 문자열.
- ``{pointer, map, default}`` 값: 포인터 값을 문자열(``true``·``false``·``null``·숫자는 JSON 표기)로
  바꿔 ``map``에서 찾고, 없으면 ``default``(없으면 그 문자열 그대로). 찾은 ``map`` 값과
  ``default``도 틀이다(예: ``default: "{node}"``). ``from``·``to``도 이 조건부 값을 쓸 수 있다
  (design §5.5R.1 C7: ``node.started``의 ``to``는 위임 호출일 때만).
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from agent_console_contracts import x_ui
from agent_console_logs import JsonValue, effective_config, json_pointer, text

__all__ = [
    "DEFAULT_EVENT_MAP_RESOURCE",
    "DEFAULT_FALLBACK_CATEGORY",
    "EVENT_MAP_SCHEMA",
    "RULE_SCHEMA",
    "TEMPLATE_NAMES",
    "TOKEN_KEYS",
    "VALUE_FIELD_TITLES",
    "EventMap",
    "EventRule",
    "load_default_event_map",
    "load_event_map",
    "names_for",
    "overrides_of",
    "render",
    "resolve",
]

DEFAULT_EVENT_MAP_RESOURCE = "data/run_event_map.yaml"
"""패키지 안 기본 대응표(코드가 아닌 데이터)."""

DEFAULT_FALLBACK_CATEGORY = "other"
"""대응표에 맞는 규칙이 없는 형식의 범주(design §4R.2 "대응표에 없는 형식 = other")."""

TEMPLATE_NAMES: tuple[str, ...] = ("type", "node", "parent_node", "thread", "actor", "run_id")
"""틀에서 포인터 대신 쓸 수 있는 이름."""

TOKEN_KEYS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
"""``usage``에 쓸 수 있는 토큰 항목(계약 ``TokenSample`` 필드)."""

VALUE_FIELDS: tuple[str, ...] = (
    "category",
    "title",
    "stage",
    "status",
    "tool",
    "call_id",
    "via",
    "model",
    "message_id",
    "role",
)
"""틀 또는 ``{pointer, map, default}``로 채우는 초안 필드."""

VALUE_FIELD_TITLES: dict[str, str] = {
    "category": "범주",
    "title": "제목",
    "stage": "단계",
    "status": "상태",
    "tool": "도구",
    "call_id": "호출 id",
    "via": "경유",
    "model": "모델",
    "message_id": "메시지 id",
    "role": "역할",
    "from": "보낸 쪽",
    "to": "받는 쪽",
}
"""``VALUE_FIELDS``의 설정 폼 라벨."""

_POINTER: dict[str, Any] = {"type": "string", "pattern": "^(/.*)?$"}
_TEMPLATE: dict[str, Any] = {"type": "string"}


def _pointer_field(title: str, description: str, example: str) -> dict[str, Any]:
    return {
        **_POINTER,
        "title": title,
        "description": description,
        **x_ui(tier="advanced", example=example),
    }


def _value_schema(
    name: str, *, description: str | None = None, example: str = "{type}"
) -> dict[str, Any]:
    """틀 문자열 또는 ``{pointer, map, default}`` 규칙 하나(필드 ``name``)."""
    label = VALUE_FIELD_TITLES.get(name, name)
    return {
        "title": label,
        "description": description
        or f"로그의 {label} 값. 틀(예: {{type}}) 또는 이벤트에서 읽어 바꾸는 규칙.",
        **x_ui(tier="advanced", example=example),
        "oneOf": [
            {**_TEMPLATE, "title": "틀"},
            {
                "type": "object",
                "title": "이벤트에서 읽기",
                "properties": {
                    "pointer": _pointer_field(
                        "읽을 위치",
                        "값을 읽을 이벤트 안 위치(예: /data/status).",
                        "/data/status",
                    ),
                    "map": {
                        "type": "object",
                        "title": "값 바꾸기",
                        "description": (
                            "읽은 값 → 보일 값(틀, 예: {node}). 없는 값은 없을 때 값을 쓴다."
                        ),
                        **x_ui(tier="advanced"),
                        "additionalProperties": {"type": "string"},
                    },
                    "default": {
                        "type": "string",
                        "title": "없을 때 값",
                        "description": ("바꾸기 표에 없을 때 쓸 값(틀). 비우면 읽은 값 그대로."),
                        **x_ui(tier="advanced", example="other"),
                    },
                },
                "required": ["pointer"],
                "additionalProperties": False,
            },
        ],
    }


RULE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "대응 규칙",
    "properties": {
        **{name: _value_schema(name) for name in VALUE_FIELDS},
        "from": _value_schema(
            "from",
            description="보낸 쪽(틀 또는 이벤트에서 읽어 바꾸는 규칙, 비면 없음).",
            example="{node}",
        ),
        "to": _value_schema(
            "to",
            description="받는 쪽(틀 또는 이벤트에서 읽어 바꾸는 규칙, 비면 없음).",
            example="{parent_node}",
        ),
        "tags": {
            "type": "array",
            "title": "태그",
            "description": "이 형식의 로그에 붙일 태그 목록.",
            **x_ui(tier="advanced"),
            "items": {"type": "string"},
        },
        "correlation": {
            "type": "object",
            "title": "연결 근거",
            "description": "근거 이름 → 틀(session·call_id는 자동).",
            **x_ui(tier="advanced"),
            "additionalProperties": _TEMPLATE,
        },
        "duration_ms": _pointer_field(
            "소요 시간 위치",
            "끝난 구간의 소요 시간(ms) 위치. 있으면 시작·끝 두 이벤트를 낸다.",
            "/data/duration_ms",
        ),
        "session_from": _pointer_field(
            "세션 id 위치", "이 이벤트가 알리는 노드 세션 id의 위치.", "/data/session_id"
        ),
        "cwd_from": _pointer_field(
            "작업 폴더 위치",
            "이 이벤트가 알리는 Run 작업 폴더의 위치. 그 뒤 같은 Run 로그의 프로젝트 기준이 된다.",
            "/data/cwd",
        ),
        "usage": {
            "type": "object",
            "title": "토큰 위치",
            "description": "토큰 항목 → 읽을 위치.",
            **x_ui(tier="advanced"),
            "propertyNames": {"enum": list(TOKEN_KEYS)},
            "additionalProperties": _POINTER,
        },
        "skip": {
            "type": "boolean",
            "title": "색인 안 함",
            "description": "참이면 이 형식의 이벤트를 색인하지 않는다.",
            **x_ui(tier="advanced"),
        },
    },
    "additionalProperties": False,
}
"""대응 규칙 하나의 JSON Schema(설정 폼·검증)."""

EVENT_MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "이벤트 대응표",
    "description": (
        "실행 이벤트 형식(또는 글롭, 예: run.*) → 대응 규칙. 기본 대응표 위에 키별로 덮어쓴다."
    ),
    "additionalProperties": RULE_SCHEMA,
}
"""대응표(형식 → 규칙)의 JSON Schema."""

_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"types": EVENT_MAP_SCHEMA},
    "additionalProperties": False,
}

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


@dataclass(frozen=True, slots=True)
class EventRule:
    """대응 규칙 하나(``RULE_SCHEMA`` 모양 그대로)."""

    spec: Mapping[str, Any] = field(default_factory=dict)

    @property
    def skip(self) -> bool:
        return self.spec.get("skip") is True

    def get(self, name: str) -> Any:
        return self.spec.get(name)


def _string_form(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def render(template: str, document: JsonValue, names: Mapping[str, str]) -> str:
    """틀을 채운다(``{/포인터}``·``{이름}``). 모르는 이름·없는 값은 빈 문자열."""

    def one(match: re.Match[str]) -> str:
        key = match.group(1)
        if key.startswith("/"):
            value = json_pointer(document, key)
            return "" if value is None else text(value)
        return names.get(key, "")

    return _PLACEHOLDER.sub(one, template).strip()


def resolve(spec: Any, document: JsonValue, names: Mapping[str, str]) -> str:
    """규칙 값(틀 또는 ``{pointer, map, default}``) → 문자열. 값이 없으면 빈 문자열.

    ``map``에서 찾은 값과 ``default``도 틀로 채운다(``{node}``·``{/포인터}`` 등).
    """
    if isinstance(spec, str):
        return render(spec, document, names)
    if isinstance(spec, Mapping):
        pointer = spec.get("pointer")
        raw = json_pointer(document, pointer) if isinstance(pointer, str) else None
        key = _string_form(raw)
        table = spec.get("map")
        if isinstance(table, Mapping) and key in table:
            return render(str(table[key]), document, names)
        default = spec.get("default")
        if isinstance(default, str):
            return render(default, document, names)
        return "" if raw is None else key
    return ""


def _is_glob(key: str) -> bool:
    return any(ch in key for ch in "*?[")


class EventMap:
    """형식 → 규칙 대응표.

    Args:
        rules: 형식(또는 글롭) → 규칙 원문(``RULE_SCHEMA`` 모양).
        fallback_category: 맞는 규칙이 없을 때의 범주.
    """

    def __init__(
        self,
        rules: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        fallback_category: str = DEFAULT_FALLBACK_CATEGORY,
    ) -> None:
        self._rules = {str(k): EventRule(dict(v)) for k, v in (rules or {}).items()}
        self._globs = sorted((k for k in self._rules if _is_glob(k)), key=lambda k: (-len(k), k))
        self._fallback = EventRule({"category": fallback_category})
        self._cache: dict[str, EventRule] = {}

    @property
    def fallback_category(self) -> str:
        """맞는 규칙이 없거나 범주 틀이 빈 값일 때의 범주."""
        return str(self._fallback.get("category"))

    @property
    def rules(self) -> dict[str, dict[str, Any]]:
        """규칙 원문 사본."""
        return {k: dict(v.spec) for k, v in self._rules.items()}

    def with_overrides(self, overrides: Mapping[str, Mapping[str, Any]] | None) -> EventMap:
        """키별로 통째로 덮어쓴 새 대응표."""
        if not overrides:
            return self
        merged = self.rules
        merged.update({str(k): dict(v) for k, v in overrides.items()})
        return EventMap(merged, fallback_category=self.fallback_category)

    def rule_for(self, event_type: str) -> EventRule:
        """형식에 맞는 규칙(정확한 이름 → 긴 글롭 순, 없으면 대체 범주)."""
        found = self._cache.get(event_type)
        if found is not None:
            return found
        rule = self._rules.get(event_type)
        if rule is None or _is_glob(event_type):
            rule = next(
                (self._rules[k] for k in self._globs if fnmatch.fnmatchcase(event_type, k)),
                self._fallback,
            )
        self._cache[event_type] = rule
        return rule


def load_event_map(text_value: str) -> EventMap:
    """YAML 문자열(``types: {형식: 규칙}``) → 대응표. 빈 문서 = 빈 대응표.

    Raises:
        ConfigError: 모양이 ``RULE_SCHEMA``와 다르다.
    """
    data = YAML(typ="safe").load(text_value) if text_value.strip() else None
    checked = effective_config(_FILE_SCHEMA, data or {})
    types = checked.get("types")
    return EventMap(types if isinstance(types, Mapping) else {})


@lru_cache(maxsize=4)
def _default_text(path: str | None) -> str | None:
    try:
        if path is not None:
            return Path(path).read_text(encoding="utf-8")
        return (
            resources.files(__package__)
            .joinpath(DEFAULT_EVENT_MAP_RESOURCE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, NotADirectoryError):
        return None


def load_default_event_map(path: Path | None = None) -> EventMap:
    """기본 대응표를 읽는다.

    Args:
        path: 다른 파일을 기본값으로 쓸 때. 없으면 패키지 데이터.

    Returns:
        대응표. 파일이 없으면 빈 대응표(모든 형식이 대체 범주).

    Raises:
        ConfigError: 파일 모양이 틀렸다.
    """
    found = _default_text(str(path) if path is not None else None)
    return load_event_map(found) if found is not None else EventMap()


def overrides_of(value: JsonValue) -> dict[str, dict[str, Any]]:
    """설정 값 → 덮어쓰기(객체가 아니면 빈 값). 검증은 출처 설정 스키마가 한다."""
    if not isinstance(value, Mapping):
        return {}
    return {str(k): dict(v) for k, v in value.items() if isinstance(v, Mapping)}


def names_for(event: Mapping[str, Any], thread: str) -> dict[str, str]:
    """틀 이름 값."""
    path = event.get("node_path")
    nodes: Sequence[Any] = path if isinstance(path, list) else []
    return {
        "type": str(event.get("type") or ""),
        "node": str(nodes[-1]) if nodes else "",
        "parent_node": str(nodes[-2]) if len(nodes) > 1 else "",
        "thread": thread,
        "actor": str(event.get("actor") or ""),
        "run_id": str(event.get("run_id") or ""),
    }
