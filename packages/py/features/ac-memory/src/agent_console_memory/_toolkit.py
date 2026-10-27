"""에이전트 도구 묶음(`MemoryToolkit`): 도구 스펙·입력 스키마·결과 문구·사유 코드·이벤트 payload.

런타임(실행 엔진·에이전트 노드·SDK)을 모른다. 도구 스펙(`ToolSpec`)은 이름·설명·입력 스키마·
비동기 호출 함수뿐이라 플랫폼 도구(`HostTool`), Claude Agent SDK `@tool`, MCP 서버 어느 쪽으로도
감쌀 수 있다. 범위 id는 맥락(`MemoryAccessContext`)에서 계산하고 에이전트가 정하지 못한다.

이벤트 payload(`MemoryEventPayload`)에는 **본문·검색어 원문을 싣지 않는다**(크기·해시만).
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any, Final

from ruamel.yaml import YAML

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import (
    MEMORY_ACCESS_OPS,
    MEMORY_EVENT_PREFIX,
    KnownMemoryAuthorKinds,
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
    MemoryEntry,
    MemoryEventPayload,
    MemoryScopeRef,
)

from ._access import allowed, default_scope_kind, scope_kinds_for
from ._errors import (
    EntryNotFoundError,
    InvalidKeyError,
    MemoryStoreError,
    SecretRejectedError,
    TooLargeError,
    VersionConflictError,
)
from ._scope_kinds import ScopeKindCatalog
from ._store import MemoryQuery, MemoryStore

TOOL_TEXT_RESOURCE: Final = "data/tool_text.yaml"
"""도구 문구 기본 데이터 위치(패키지 안 상대 경로)."""

_FIELD = re.compile(r"\{(\w+)\}")
_ERROR: Final = "error"


def fill(template: str, values: Mapping[str, Any]) -> str:
    """`{이름}` 자리를 값으로 채운다. 모르는 이름·다른 중괄호는 그대로 둔다.

    >>> fill("v{version} {x} {}", {"version": 2})
    'v2 {x} {}'
    """
    return _FIELD.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template
    )


@dataclass(frozen=True, slots=True)
class ToolText:
    """도구 문구(데이터, `data/tool_text.yaml`). 도구 이름·설명·머리 줄은 접근 설정이 정한다."""

    inputs: Mapping[str, str]
    search_item: str
    search_empty: str
    written: str
    deleted: str
    truncated: str
    errors: Mapping[str, str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ToolText:
        """데이터 → 문구. 빠진 키는 `KeyError`."""
        return cls(
            inputs={str(k): str(v) for k, v in data["inputs"].items()},
            search_item=str(data["search_item"]),
            search_empty=str(data["search_empty"]),
            written=str(data["written"]),
            deleted=str(data["deleted"]),
            truncated=str(data["truncated"]),
            errors={str(k): str(v) for k, v in data["errors"].items()},
        )


def load_tool_text() -> ToolText:
    """패키지 기본 도구 문구(`data/tool_text.yaml`)."""
    text = files("agent_console_memory").joinpath(TOOL_TEXT_RESOURCE).read_text("utf-8")
    return ToolText.from_mapping(YAML(typ="safe").load(text))


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """도구 호출 하나의 결과.

    Attributes:
        text: 모델에게 돌려줄 텍스트.
        is_error: 실패 결과인지(실행은 계속된다).
        code: 실패 사유 코드(`memory.denied` 등, 성공이면 None).
        event_type: 이벤트 type(`memory.<op>`).
        event: 이벤트 payload(본문·검색어 원문 없음).
    """

    text: str
    is_error: bool
    code: str | None
    event_type: str
    event: MemoryEventPayload


type ToolCall = Callable[[Mapping[str, Any], str | None], Awaitable[ToolOutcome]]
"""(모델이 준 입력, 도구 호출 id 또는 None) → 결과."""

type EventSink = Callable[[str, MemoryEventPayload], Awaitable[None] | None]
"""이벤트 받는 쪽(type, payload). 동기·비동기 모두 받는다."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """도구 하나. `call(args, call_id)`를 부르면 처리하고 이벤트를 낸다.

    Attributes:
        op: 동작(read·search·write·delete, 계약 어휘).
        name: 모델에게 보이는 이름(접근 설정 데이터).
        description: 모델에게 보이는 설명(데이터).
        input_schema: 입력 JSON Schema(최상위 object).
        call: 비동기 호출 함수.
    """

    op: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    call: ToolCall = field(compare=False)


class WriteBudget:
    """쓰기 횟수 한도(실행 하나에 여러 도구 묶음이 함께 쓴다). None = 한도 없음. 스레드 안전."""

    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        """한 번 쓴다. 남은 횟수가 없으면 False."""
        with self._lock:
            if self.limit is not None and self.used >= self.limit:
                return False
            self.used += 1
            return True


def agent_author(context: MemoryAccessContext) -> MemoryAuthor:
    """맥락 → 에이전트 쓴 주체(빈 값은 None)."""
    return MemoryAuthor(
        kind=KnownMemoryAuthorKinds.AGENT,
        agent_id=context.agent_id or None,
        node_id=context.node_id or None,
        node_path=list(context.node_path),
        run_id=context.run_id or None,
        root_run_id=context.root_run_id or None,
        graph_id=context.graph_id or None,
        project_id=context.project_id or None,
    )


def format_author(author: MemoryAuthor) -> str:
    """쓴 주체 짧은 표시(`<종류>` 또는 `<종류>:<에이전트 id·표시>`).

    >>> format_author(MemoryAuthor(kind="agent", agent_id="a1"))
    'agent:a1'
    """
    name = author.agent_id or author.label
    return f"{author.kind}:{name}" if name else author.kind


def format_time(epoch: float) -> str:
    """Unix epoch 초 → `YYYY-MM-DDTHH:MM:SSZ`(UTC).

    >>> format_time(0)
    '1970-01-01T00:00:00Z'
    """
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _ToolError(Exception):
    def __init__(self, status: str, code: str, **values: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.values = values


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _string(args: Mapping[str, Any], name: str, *, required: bool) -> str | None:
    value = args.get(name)
    if value is None:
        if required:
            raise _ToolError(_ERROR, _ERROR)
        return None
    if not isinstance(value, str):
        raise _ToolError(_ERROR, _ERROR)
    return value


def _strings(args: Mapping[str, Any], name: str) -> list[str] | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _ToolError(_ERROR, _ERROR)
    return list(value)


def _integer(args: Mapping[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _ToolError(_ERROR, _ERROR)
    return value


class MemoryToolkit:
    """에이전트 메모리 도구 묶음. 접근 설정이 허용한 동작의 도구만 낸다.

    Args:
        store: 메모리 저장소(X31).
        access: 리소스 `memory`의 접근 설정(범위 종류별 허용 동작·도구 이름·설명·머리 줄).
        context: 접근 맥락(범위 id 틀이 읽는 값).
        catalog: 범위 종류 목록(`merge_scope_kinds`).
        author: 쓴 주체. 없으면 맥락에서 만든 에이전트 주체.
        text: 도구 문구. 없으면 `load_tool_text()`.
        on_event: 호출마다 `(type, payload)`를 받는 쪽(선택).
        write_budget: 쓰기 횟수 한도(실행 단위로 공유, 선택).
        max_search_results: 검색 결과 최대 수(입력 `limit`의 상한).
        timer: 처리 시간 측정 시계(초).
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        access: MemoryAccessConfig,
        context: MemoryAccessContext,
        catalog: ScopeKindCatalog,
        author: MemoryAuthor | None = None,
        text: ToolText | None = None,
        on_event: EventSink | None = None,
        write_budget: WriteBudget | None = None,
        max_search_results: int = 20,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.store = store
        self.access = access
        self.context = context
        self.catalog = catalog
        self.author = author if author is not None else agent_author(context)
        self.text = text if text is not None else load_tool_text()
        self.on_event = on_event
        self.write_budget = write_budget
        self.max_search_results = max(1, max_search_results)
        self._timer = timer

    # ---- 스펙 ---------------------------------------------------------------------------

    def _tool_text(self, op: str) -> tuple[str, str]:
        tool = getattr(self.access.tools, op)
        return tool.name, tool.description

    def _scope_property(self, op: str) -> dict[str, Any]:
        kinds = scope_kinds_for(self.access, op)
        choices = ", ".join(f"{k}({self.catalog.label(k)})" for k in kinds)
        return {
            "type": "string",
            "enum": kinds,
            "description": fill(self.text.inputs["scope"], {"choices": choices}),
        }

    def _prop(self, name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        return {**schema, "description": self.text.inputs.get(name, "")}

    def input_schema(self, op: str) -> dict[str, Any]:
        """동작 `op`의 입력 JSON Schema(매개변수 이름은 계약 어휘, 설명은 데이터)."""
        props: dict[str, Any] = {}
        required: list[str] = []
        if op == "search":
            props["query"] = self._prop("query", {"type": "string"})
            props["scope"] = self._scope_property(op)
            props["tags"] = self._prop("tags", {"type": "array", "items": {"type": "string"}})
            props["limit"] = self._prop(
                "limit", {"type": "integer", "minimum": 1, "maximum": self.max_search_results}
            )
        else:
            props["key"] = self._prop("key", {"type": "string"})
            required.append("key")
            if op == "write":
                props["content"] = self._prop("content", {"type": "string"})
                required.append("content")
            props["scope"] = self._scope_property(op)
            if op == "write":
                props["tags"] = self._prop("tags", {"type": "array", "items": {"type": "string"}})
                props["if_version"] = self._prop("if_version", {"type": "integer", "minimum": 0})
                props["mode"] = self._prop(
                    "mode", {"type": "string", "enum": ["replace", "append"]}
                )
        return {"type": "object", "properties": props, "required": required}

    def specs(self) -> list[ToolSpec]:
        """허용된 동작의 도구 스펙(계약 어휘 순서). 허용된 범위가 없는 동작은 빠진다."""
        out: list[ToolSpec] = []
        for op in MEMORY_ACCESS_OPS:
            if not scope_kinds_for(self.access, op):
                continue
            name, description = self._tool_text(op)

            async def call(
                args: Mapping[str, Any], call_id: str | None = None, *, _op: str = op
            ) -> ToolOutcome:
                return await self.call(_op, args, call_id)

            out.append(
                ToolSpec(
                    op=op,
                    name=name,
                    description=description,
                    input_schema=self.input_schema(op),
                    call=call,
                )
            )
        return out

    # ---- 호출 ---------------------------------------------------------------------------

    async def call(
        self, op: str, args: Mapping[str, Any], call_id: str | None = None
    ) -> ToolOutcome:
        """동작 하나를 처리하고 이벤트를 낸다. 실패는 예외가 아니라 `is_error` 결과다.

        Args:
            op: 동작(read·search·write·delete).
            args: 모델이 준 입력.
            call_id: 모델의 도구 호출 id(이벤트 `tool_use_id`).

        Raises:
            ValueError: 모르는 동작(모델 입력이 아니라 호출 코드의 잘못).
        """
        if op not in MEMORY_ACCESS_OPS:
            raise ValueError(f"모르는 동작: {op!r}")
        started = self._timer()
        payload: dict[str, Any] = {"op": op, "tool": self._tool_text(op)[0], "tool_use_id": call_id}
        values: dict[str, Any] = {}
        try:
            text = await self._dispatch(op, args, payload, values)
            status, code, is_error = "ok", None, False
        except _ToolError as failure:
            status, code, is_error = failure.status, failure.code, True
            values.update(failure.values)
            if status == "conflict" and values.get("version"):
                payload["version"] = values["version"]
            message = fill(self.text.errors.get(code, self.text.errors[_ERROR]), values)
            text = f"[{code}] {message}"
        payload["status"] = status
        payload["duration_ms"] = max(0.0, (self._timer() - started) * 1000)
        event = MemoryEventPayload.model_validate(payload)
        event_type = f"{MEMORY_EVENT_PREFIX}{op}"
        if self.on_event is not None:
            result = self.on_event(event_type, event)
            if inspect.isawaitable(result):
                await result
        return ToolOutcome(
            text=self._clip(text), is_error=is_error, code=code, event_type=event_type, event=event
        )

    def _clip(self, text: str) -> str:
        limit = self.access.max_result_chars
        if len(text) <= limit:
            return text
        suffix = fill(self.text.truncated, {"limit": limit})
        if len(suffix) >= limit:
            return text[:limit]
        return text[: limit - len(suffix)] + suffix

    def _scope(self, op: str, args: Mapping[str, Any], values: dict[str, Any]) -> MemoryScopeRef:
        kind = _string(args, "scope", required=False) or default_scope_kind(self.access)
        if kind is None:
            raise _ToolError("denied", KnownIssueCodes.MEMORY_DENIED, scope_label="")
        values["scope_label"] = self.catalog.label(kind)
        if not allowed(self.access, op, kind):
            raise _ToolError("denied", KnownIssueCodes.MEMORY_DENIED)
        scope = self.catalog.resolve(kind, self.context)
        if scope is None:
            raise _ToolError("scope_unavailable", KnownIssueCodes.MEMORY_SCOPE_UNAVAILABLE)
        return scope

    async def _store_call[T](self, fn: Callable[[], T]) -> T:
        try:
            return await asyncio.to_thread(fn)
        except VersionConflictError as exc:
            raise _ToolError(
                "conflict", KnownIssueCodes.MEMORY_CONFLICT, version=exc.current_version
            ) from None
        except TooLargeError as exc:
            raise _ToolError(
                "too_large", KnownIssueCodes.MEMORY_TOO_LARGE, limit=exc.limit
            ) from None
        except SecretRejectedError:
            raise _ToolError("secret_rejected", KnownIssueCodes.MEMORY_SECRET_REJECTED) from None
        except EntryNotFoundError:
            raise _ToolError("not_found", KnownIssueCodes.MEMORY_NOT_FOUND) from None
        except InvalidKeyError:
            raise _ToolError(_ERROR, KnownIssueCodes.MEMORY_INVALID_KEY) from None
        except MemoryStoreError:
            raise _ToolError(_ERROR, _ERROR) from None
        except Exception:
            raise _ToolError(_ERROR, _ERROR) from None

    def _entry_values(self, entry: MemoryEntry, values: dict[str, Any]) -> None:
        values.update(
            key=entry.key,
            version=entry.version,
            author=format_author(entry.updated_by),
            updated_at=format_time(entry.updated_at),
        )

    @staticmethod
    def _entry_payload(entry: MemoryEntry, payload: dict[str, Any]) -> None:
        payload.update(
            entry_id=entry.id, version=entry.version, bytes=entry.bytes, sha256=entry.sha256
        )

    async def _dispatch(
        self, op: str, args: Mapping[str, Any], payload: dict[str, Any], values: dict[str, Any]
    ) -> str:
        if op == "search":
            return await self._search(args, payload, values)
        key = _string(args, "key", required=True) or ""
        values["key"] = key
        scope = self._scope(op, args, values)
        payload.update(scope=scope, key=key)
        if op == "read":
            return await self._read(scope, key, payload, values)
        if op == "write":
            return await self._write(scope, key, args, payload, values)
        return await self._delete(scope, key, payload, values)

    async def _search(
        self, args: Mapping[str, Any], payload: dict[str, Any], values: dict[str, Any]
    ) -> str:
        query = _string(args, "query", required=False) or ""
        tags = _strings(args, "tags") or []
        limit = _integer(args, "limit") or self.max_search_results
        limit = min(max(limit, 1), self.max_search_results)
        if query:
            payload.update(query_chars=len(query), query_sha256=_sha(query))
        scope = self._scope("search", args, values)
        payload["scope"] = scope
        page = await self._store_call(
            lambda: self.store.search(
                MemoryQuery(scopes=[scope], text=query, tags=tags, limit=limit)
            )
        )
        payload["results"] = len(page.items)
        if not page.items:
            return self.text.search_empty
        lines = [
            fill(
                self.text.search_item,
                {
                    "scope_label": values["scope_label"],
                    "key": item.key,
                    "version": item.version,
                    "author": format_author(item.updated_by),
                    "updated_at": format_time(item.updated_at),
                    "tags": ", ".join(item.tags),
                    "preview": item.preview.replace("\n", " "),
                },
            )
            for item in page.items
        ]
        return "\n".join(lines)

    async def _read(
        self, scope: MemoryScopeRef, key: str, payload: dict[str, Any], values: dict[str, Any]
    ) -> str:
        entry = await self._store_call(lambda: self.store.find(scope, key))
        if entry is None or entry.archived:
            raise _ToolError("not_found", KnownIssueCodes.MEMORY_NOT_FOUND)
        await self._store_call(lambda: self.store.mark_read(entry.id))
        self._entry_payload(entry, payload)
        self._entry_values(entry, values)
        header = fill(self.access.result_header, values)
        return f"{header}\n{entry.content}"

    async def _write(
        self,
        scope: MemoryScopeRef,
        key: str,
        args: Mapping[str, Any],
        payload: dict[str, Any],
        values: dict[str, Any],
    ) -> str:
        content = _string(args, "content", required=True) or ""
        tags = _strings(args, "tags")
        if_version = _integer(args, "if_version")
        mode = _string(args, "mode", required=False) or "replace"
        if mode not in ("replace", "append"):
            raise _ToolError(_ERROR, _ERROR)
        if self.write_budget is not None and not self.write_budget.take():
            raise _ToolError("rate_limited", KnownIssueCodes.MEMORY_RATE_LIMITED)
        outcome = await self._store_call(
            lambda: self.store.write(
                scope,
                key,
                content,
                author=self.author,
                tags=tags,
                if_version=if_version,
                mode="append" if mode == "append" else "replace",
            )
        )
        self._entry_payload(outcome.entry, payload)
        self._entry_values(outcome.entry, values)
        return fill(self.text.written, values)

    async def _delete(
        self, scope: MemoryScopeRef, key: str, payload: dict[str, Any], values: dict[str, Any]
    ) -> str:
        entry = await self._store_call(lambda: self.store.find(scope, key))
        if entry is None:
            raise _ToolError("not_found", KnownIssueCodes.MEMORY_NOT_FOUND)
        deleted = await self._store_call(lambda: self.store.delete(entry.id, author=self.author))
        self._entry_payload(deleted, payload)
        self._entry_values(deleted, values)
        return fill(self.text.deleted, values)
