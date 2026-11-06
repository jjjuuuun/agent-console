"""노트 읽기 도구 공급자(X30 ``ToolProvider``).

- 묶음에 노트 칸이 없으면 아무것도 하지 않는다(리소스를 붙이지 않은 에이전트에게는 도구·
  지침이 없다).
- 노트 읽기 포트가 없으면 칸을 소비하지 않는다(백엔드가 적용하지 못한 칸 경고가 그대로 난다).
- 노트는 **그 실행 공간의 노트만** 읽는다(루트 Run의 ``project_id``, 없으면 앱 공간). 공간을
  열 수 없으면 도구 결과가 오류이고 실행은 계속된다(다른 공간으로 대신하지 않는다).
- 도구 호출마다 RunEvent(type은 데이터, 기본 ``example_notes.read``)를 낸다. payload에 노트
  본문은 없다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from pydantic import ValidationError

from agent_console_contracts import Issue
from agent_console_nodes_core import ToolProvision, ToolProvisionContext
from agent_console_runtime import HostTool, HostToolResult

from .ports import NoteLike, NotesReaderLike
from .resource_type import NotesAccess
from .settings import NotesToolText

__all__ = ["ACCESS_INVALID", "NotesToolProvider", "merge_access", "render_notes"]

_log = logging.getLogger(__name__)

ACCESS_INVALID: Final = "example_notes.access_invalid"
"""칸의 설정을 합친 결과가 ``NotesAccess`` 형식이 아니다(도구를 주지 않는다)."""

_OK: Final = "ok"
_INVALID_INPUT: Final = "invalid_input"


def merge_access(items: Any) -> tuple[NotesAccess | None, list[Issue]]:
    """칸에 쌓인 첨부(먼 층 → 가까운 층)를 하나로 합친다. 키마다 가까운 층(뒤 항목) 값이 이긴다.

    >>> merge_access([{"config": {"tag": "a", "limit": 3}}, {"config": {"tag": "b"}}])
    (NotesAccess(limit=3, tag='b'), [])
    >>> access, issues = merge_access([{"config": {"limit": 0}}])
    >>> access, [i.code for i in issues]
    (None, ['example_notes.access_invalid'])
    """
    merged: dict[str, Any] = {}
    if isinstance(items, Sequence) and not isinstance(items, str | bytes):
        for item in items:
            config = item.get("config") if isinstance(item, Mapping) else None
            if isinstance(config, Mapping):
                merged.update(config)
    try:
        return NotesAccess.model_validate(merged), []
    except ValidationError as exc:
        where = sorted({"/" + "/".join(str(p) for p in err["loc"]) for err in exc.errors()})
        return None, [
            Issue(
                severity="warning",
                code=ACCESS_INVALID,
                message="노트 리소스 설정을 합친 결과가 형식에 맞지 않아 노트 도구를 주지 않습니다",
                details={"paths": where},
            )
        ]


def render_notes(notes: Sequence[NoteLike], text: NotesToolText) -> str:
    """노트 목록 → 도구 결과 글(문구 틀은 데이터).

    >>> from types import SimpleNamespace as N
    >>> from agent_console_example_link import NotesRunsSettings
    >>> t = NotesRunsSettings().text()
    >>> print(render_notes([N(id="1", text="배포는 금요일", tags=["회의"])], t))
    - [1] 배포는 금요일 (#회의)
    >>> render_notes([], t) == t.empty
    True
    """
    if not notes:
        return text.empty
    lines = []
    for note in notes:
        tags = f" ({' '.join('#' + t for t in note.tags)})" if note.tags else ""
        lines.append(text.line.format(id=note.id, text=note.text, tags=tags))
    return "\n".join(lines)


def _reason(exc: Exception) -> str:
    """예외 → 사유 코드(``code`` 속성 또는 형식 이름). 메시지는 싣지 않는다."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else type(exc).__name__


class NotesToolProvider:
    """X30 ``ToolProvider``: 노트 칸이 있는 노드에 노트 읽기 도구와 지침을 준다.

    Args:
        reader: 지금 노트 읽기 포트를 돌려주는 함수(None이면 칸을 소비하지 않는다).
        slot: 읽을 묶음 칸 이름(리소스 종류 데이터의 ``contributes`` 첫 칸).
        text: 도구 이름·문구·지침·이벤트 type.
        id: 공급자 id(경고 details ``provider``, 지침 출처 ``tool_provider:<id>``).
        project_id: 루트 Run의 프로젝트 id(없으면 앱 공간).
        max_notes: 한 번에 줄 노트 수 상한(None = 노트 모듈 한도).
    """

    def __init__(
        self,
        reader: Callable[[], NotesReaderLike | None],
        *,
        slot: str,
        text: NotesToolText,
        id: str,
        project_id: str | None = None,
        max_notes: int | None = None,
    ) -> None:
        self.id = id
        self.slot = slot
        self.text = text
        self.project_id = project_id or None
        self.max_notes = max_notes
        self._reader = reader

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
        """이 노드의 도구·지침(칸이 없거나 포트가 없으면 빈 결과)."""
        if self.slot not in ctx.bundle.slots:
            return ToolProvision()
        reader = self._reader()
        if reader is None:
            return ToolProvision()
        consumed = frozenset({self.slot})
        access, issues = merge_access(ctx.bundle.slots[self.slot])
        if access is None:
            return ToolProvision(consumed_slots=consumed, warnings=tuple(issues))
        tool = self._tool(ctx, reader, access)
        return ToolProvision(
            host_tools=(tool,),
            consumed_slots=consumed,
            instructions=(self.text.instructions.format(tool=self.text.name),),
        )

    def _count(self, requested: int | None) -> int | None:
        if requested is None:
            return self.max_notes
        return requested if self.max_notes is None else min(requested, self.max_notes)

    def _tool(
        self, ctx: ToolProvisionContext, reader: NotesReaderLike, access: NotesAccess
    ) -> HostTool:
        text = self.text

        async def emit(tool_use_id: str | None, status: str, count: int = 0) -> None:
            payload: dict[str, Any] = {
                "provider": self.id,
                "tool": text.name,
                "tool_use_id": tool_use_id,
                "status": status,
                "count": count,
            }
            if self.project_id:
                payload["project_id"] = self.project_id
            await ctx.emit(text.event_type, payload)

        async def call(arguments: dict[str, Any], tool_use_id: str | None) -> HostToolResult:
            limit = arguments.get("limit", access.limit)
            tag = arguments.get("tag", access.tag)
            if (limit is not None and (not isinstance(limit, int) or limit < 1)) or (
                tag is not None and not isinstance(tag, str)
            ):
                await emit(tool_use_id, _INVALID_INPUT)
                return HostToolResult(text="limit는 1 이상 정수, tag는 문자열입니다", is_error=True)
            count = self._count(limit)
            try:
                # 태그로 거를 때는 넉넉히 받아 거른 뒤 자른다.
                notes = list(reader.list_notes(self.project_id, limit=None if tag else count))
            except Exception as exc:
                reason = _reason(exc)
                _log.info("노트를 읽지 못함: %s (%s)", self.project_id, reason)
                await emit(tool_use_id, reason)
                return HostToolResult(text=f"노트를 읽지 못했습니다({reason})", is_error=True)
            if tag:
                notes = [n for n in notes if tag in n.tags]
            if count is not None:
                notes = notes[:count]
            await emit(tool_use_id, _OK, len(notes))
            return HostToolResult(text=render_notes(notes, text))

        async def handler(arguments: dict[str, Any]) -> HostToolResult:
            return await call(arguments, None)

        return HostTool(
            name=text.name,
            description=text.description,
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1},
                    "tag": {"type": "string"},
                },
            },
            handler=handler,
            call_handler=call,
        )
