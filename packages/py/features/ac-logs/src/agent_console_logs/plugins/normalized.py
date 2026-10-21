"""`normalized-v1`: agent_bench events.jsonl v1 규격 출처·분류기(X5·X6 기본 제공).

필수: `schema_version: 1`, `category`·`title` 문자열. 예약 키(`schema_version`·`id`·`uid`·`seq`·
`origin`·`observed_at`)는 쓰지 않는다. actor가 없으면 thread, 그것도 없으면 설정 `default_actor`.
외부 도구가 이 형식으로 jsonl을 쓰면 코드 없이 그대로 수용한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from agent_console_contracts.logs import (
    LogClassifierDescriptor,
    LogDocumentRef,
    LogSourceDescriptor,
    TokenSample,
)
from agent_console_logs._draft import AgentInfo, LogEventDraft
from agent_console_logs._jsonl import JSONL_CONFIG_SCHEMA, JsonlFileSource
from agent_console_logs._source import ClassifyContext, RawRecord
from agent_console_logs._values import timestamp

__all__ = ["RESERVED_KEYS", "NormalizedV1Classifier", "NormalizedV1Source"]

FORMAT_ID = "normalized-v1"

RESERVED_KEYS = frozenset({"schema_version", "id", "uid", "seq", "origin", "observed_at"})
"""v1 행에서 무시하는 키(색인이 매기는 값)."""


class NormalizedV1Source(JsonlFileSource):
    """v1 jsonl 파일 출처. 루트를 지정해야 하므로 기본 꺼짐."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=FORMAT_ID,
        title="정규화 이벤트 jsonl (v1)",
        format=FORMAT_ID,
        description="schema_version: 1 형식으로 쓴 jsonl 파일을 읽는다(agent_bench events.jsonl).",
        config_schema=JSONL_CONFIG_SCHEMA,
        default_enabled=False,
        reads_paths=True,
        setup_help=(
            "`roots`에 jsonl 폴더를 넣는다. "
            "각 줄은 `schema_version: 1`, `category`, `title`을 가진다."
        ),
    )


_STR_FIELDS = (
    "stage",
    "status",
    "thread",
    "role",
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


def _strs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list | tuple):
        return tuple(str(v) for v in value if v not in (None, ""))
    return (str(value),) if value != "" else ()


def _correlation(row: Mapping[str, Any]) -> dict[str, str | list[str]]:
    value = row.get("correlation")
    if value is None and isinstance(row.get("study"), Mapping):
        value = row["study"].get("correlation")
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, str | list[str]] = {}
    for k, v in value.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v if x not in (None, "")]
        elif v not in (None, ""):
            out[str(k)] = str(v)
    return out


def _usage(value: Any) -> TokenSample | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return TokenSample.model_validate(value)
    except ValueError:
        return None


class NormalizedV1Classifier:
    """v1 행 → 초안 하나. 규격에 맞지 않으면 ValueError(→ 진단 이벤트)."""

    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id=FORMAT_ID,
        formats=[FORMAT_ID],
        title="정규화 이벤트 v1",
        description="v1 필드를 그대로 쓴다. 표시용 필드는 detail로 보존한다.",
        config_schema={
            "type": "object",
            "properties": {
                "default_actor": {
                    "type": "string",
                    "default": "controller",
                    "title": "기본 actor",
                    "description": "actor·thread가 모두 없을 때(agent_bench 기본값 controller).",
                }
            },
        },
    )

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        row = record.data
        if not isinstance(row, Mapping) or row.get("schema_version") != 1:
            raise ValueError("events.jsonl에는 schema_version: 1이 필요합니다.")
        if not isinstance(row.get("category"), str) or not isinstance(row.get("title"), str):
            raise ValueError("events.jsonl 이벤트에는 category와 title 문자열이 필요합니다.")
        fields = {k: v for k, v in row.items() if k not in RESERVED_KEYS}
        strs = {name: str(fields.get(name) or "") for name in _STR_FIELDS}
        lists = {name: _strs(fields.get(name)) for name in _LIST_FIELDS}
        thread = strs["thread"]
        actor = str(fields.get("actor") or "") or thread or str(ctx.config.get("default_actor", ""))
        documents = tuple(
            LogDocumentRef.model_validate(d)
            for d in fields.get("documents") or []
            if isinstance(d, Mapping) and d.get("path")
        )
        agent = None
        if thread and isinstance(fields.get("agent"), Mapping):
            info = fields["agent"]
            agent = AgentInfo(
                id=thread,
                label=info.get("label") if isinstance(info.get("label"), str) else None,
                parent_id=info.get("parent_id") if isinstance(info.get("parent_id"), str) else None,
            )
        elif thread and strs["role"]:
            agent = AgentInfo(id=thread, label=strs["role"])  # agent_bench: thread → role 이름
        detail = fields.get("detail", fields)
        return [
            LogEventDraft(
                category=str(fields["category"]),
                title=str(fields["title"]),
                stage=strs["stage"] or "info",
                status=strs["status"],
                thread=thread,
                role=strs["role"],
                actor=actor,
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
                time=timestamp(fields.get("time", fields.get("timestamp"))),
                evidence=strs["evidence"] or "observed",
                tags=lists["tags"],
                documents=documents,
                correlation=_correlation(fields),
                detail=detail,
                raw=fields.get("raw", detail),
                usage=_usage(fields.get("usage")),
                agent=agent,
            )
        ]
