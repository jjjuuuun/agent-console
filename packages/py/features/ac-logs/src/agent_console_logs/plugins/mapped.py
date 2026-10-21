"""`mapped-jsonl`: 설정의 JSON 포인터 대응으로 필드를 채우는 선언형 출처·분류기(X5·X6 기본 제공).

코드 없이 다른 도구의 jsonl을 읽는다. 분류기 설정(`logs.sources[].config.classifier.config`):

- `fields`: 초안 필드 → JSON 포인터(예: `{"title": "/msg", "time": "/ts", "category": "/level"}`)
- `defaults`: 포인터가 없거나 값이 비었을 때 쓸 상수(기본 `{"category": "other"}`)
- `value_maps`: 필드 → {원래 값: 바꿀 값}(예: `{"category": {"ERROR": "error"}}`)
- `correlation`: 근거 이름 → JSON 포인터
- `usage`: 토큰 항목(`input_tokens` 등) → JSON 포인터
- `skip_if_missing`: 이 포인터 중 하나라도 값이 없으면 행을 버린다
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from agent_console_contracts.logs import (
    LogClassifierDescriptor,
    LogSourceDescriptor,
    TokenSample,
)
from agent_console_logs._draft import LogEventDraft
from agent_console_logs._jsonl import JSONL_CONFIG_SCHEMA, JsonlFileSource
from agent_console_logs._source import ClassifyContext, RawRecord
from agent_console_logs._values import json_pointer, timestamp

__all__ = ["MAPPABLE_FIELDS", "MappedJsonlClassifier", "MappedJsonlSource"]

FORMAT_ID = "mapped-jsonl"

_STR_FIELDS = (
    "category",
    "title",
    "stage",
    "status",
    "thread",
    "role",
    "actor",
    "via",
    "tool",
    "call_id",
    "turn_id",
    "message_id",
    "session",
    "cwd",
    "model",
    "run_id",
    "evidence",
)
_LIST_FIELDS = ("from", "to", "node_path", "tags")
_ANY_FIELDS = ("time", "detail", "raw")
MAPPABLE_FIELDS: tuple[str, ...] = (*_STR_FIELDS, *_LIST_FIELDS, *_ANY_FIELDS)
"""`fields`·`defaults`·`value_maps`에 쓸 수 있는 초안 필드 이름."""

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

_POINTER = {"type": "string", "pattern": "^(/.*)?$"}

CLASSIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "object",
            "title": "필드 대응",
            "description": "초안 필드 → JSON 포인터(/a/b).",
            "propertyNames": {"enum": list(MAPPABLE_FIELDS)},
            "additionalProperties": _POINTER,
            "default": {},
        },
        "defaults": {
            "type": "object",
            "title": "기본값",
            "propertyNames": {"enum": list(MAPPABLE_FIELDS)},
            "default": {"category": "other"},
        },
        "value_maps": {
            "type": "object",
            "title": "값 바꾸기",
            "propertyNames": {"enum": list(MAPPABLE_FIELDS)},
            "additionalProperties": {"type": "object"},
            "default": {},
        },
        "correlation": {
            "type": "object",
            "title": "상관 근거",
            "additionalProperties": _POINTER,
            "default": {},
        },
        "usage": {
            "type": "object",
            "title": "토큰 항목",
            "propertyNames": {"enum": list(_USAGE_KEYS)},
            "additionalProperties": _POINTER,
            "default": {},
        },
        "skip_if_missing": {
            "type": "array",
            "items": _POINTER,
            "title": "없으면 버릴 포인터",
            "default": [],
        },
    },
}


class MappedJsonlSource(JsonlFileSource):
    """필드 대응으로 읽는 jsonl 출처. 루트를 지정해야 하므로 기본 꺼짐."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=FORMAT_ID,
        title="필드 대응 jsonl",
        format=FORMAT_ID,
        description="다른 도구의 jsonl을 JSON 포인터 대응(분류기 설정)으로 읽는다.",
        config_schema=JSONL_CONFIG_SCHEMA,
        default_enabled=False,
        reads_paths=True,
        setup_help=(
            "`roots`에 폴더를 넣고 `classifier.config.fields`에 필드 대응을 적는다"
            '(예: `{"title": "/msg", "time": "/ts"}`).'
        ),
    )


def _strs(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, list | tuple):
        return tuple(str(v) for v in value if v not in (None, ""))
    return (str(value),)


class MappedJsonlClassifier:
    """선언형 분류기. 행 단위 무상태."""

    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id=FORMAT_ID,
        formats=[FORMAT_ID],
        title="필드 대응",
        description="JSON 포인터로 초안 필드를 채운다.",
        config_schema=CLASSIFIER_SCHEMA,
    )

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        row = record.data
        cfg = ctx.config
        for pointer in cfg.get("skip_if_missing") or []:
            if json_pointer(row, str(pointer)) in (None, ""):
                return []
        fields: Mapping[str, str] = cfg.get("fields") or {}
        defaults: Mapping[str, Any] = cfg.get("defaults") or {}
        value_maps: Mapping[str, Mapping[str, Any]] = cfg.get("value_maps") or {}

        def get(name: str) -> Any:
            value = json_pointer(row, fields[name]) if name in fields else None
            mapping = value_maps.get(name)
            if mapping is not None and isinstance(value, str | int | float | bool):
                value = mapping.get(str(value), value)
            if value is None or value == "":
                value = defaults.get(name)
            return value

        strs = {n: "" if (v := get(n)) is None else str(v) for n in _STR_FIELDS}
        if not strs["category"]:
            raise ValueError(
                "category를 정하지 못했습니다(fields.category 또는 defaults.category)."
            )
        lists = {n: _strs(get(n)) for n in _LIST_FIELDS}
        correlation: dict[str, str | list[str]] = {}
        for basis, pointer in (cfg.get("correlation") or {}).items():
            value = json_pointer(row, str(pointer))
            if isinstance(value, list):
                correlation[str(basis)] = [str(v) for v in value if v not in (None, "")]
            elif value not in (None, ""):
                correlation[str(basis)] = str(value)
        usage = None
        usage_cfg: Mapping[str, str] = cfg.get("usage") or {}
        if usage_cfg:
            values = {k: json_pointer(row, p) for k, p in usage_cfg.items()}
            ints = {
                k: v for k, v in values.items() if isinstance(v, int) and not isinstance(v, bool)
            }
            if ints:
                usage = TokenSample.model_validate(ints)
        detail = get("detail")
        raw = get("raw")
        return [
            LogEventDraft(
                category=strs["category"],
                title=strs["title"],
                stage=strs["stage"] or "info",
                status=strs["status"],
                thread=strs["thread"],
                role=strs["role"],
                actor=strs["actor"] or strs["thread"],
                from_=lists["from"],
                to=lists["to"],
                via=strs["via"],
                tool=strs["tool"],
                call_id=strs["call_id"],
                turn_id=strs["turn_id"],
                message_id=strs["message_id"],
                session=strs["session"],
                cwd=strs["cwd"],
                model=strs["model"],
                run_id=strs["run_id"],
                node_path=lists["node_path"],
                time=timestamp(get("time")),
                evidence=strs["evidence"] or "observed",
                tags=lists["tags"],
                correlation=correlation,
                detail=row if detail is None else detail,
                raw=row if raw is None else raw,
                usage=usage,
            )
        ]
