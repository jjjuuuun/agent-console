"""앱 DB의 옛 대화를 프로젝트 기록 DB로 옮긴다(design §PI.4.6.7, K33-32, 5.7R.33j2).

`POST /conversations/move-to-project`의 도메인 부분. 이 모듈은 프로젝트도 Run도 모른다 -
``project_id``는 불투명 문자열이다.

- 한 묶음 = 대화 하나 + 그 대기열(``chat_queue``). 순서는 복사(한 트랜잭션, 같은 id는
  ``skipped``) -> 행 수·값 확인 -> 원본 삭제이고, 실패하면 대상을 되돌린다.
- 선택 포트 ``chat.move_hooks``(여러 제공자)에 ``MoveHook``이 있으면 같은 작업에 묶는다: 훅이
  그 대화에 딸린 기록(예: 대화의 Run)을 옮기는 ``RecordsMove``를 돌려주면 모두 복사 -> 모두 확인 ->
  원본 삭제 한 흐름이다(하나라도 실패하면 대상 전부 되돌림). 훅이 ``busy``로 알린 대화는 옮기지
  않고 ``failed``(``conversation.move_busy``)로 알린다. 훅에 선택 메서드 ``after_move(project_id,
  conversation_ids)``가 있으면 성공한 뒤 부른다(예: 세션 보관 사본 만들기). 훅이 없으면 대화와
  대기열만 옮긴다(Run은 건드리지 않는다).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy import Engine

from agent_console_contracts import Issue, RecordsMoveRequest, RecordsMoveResult
from agent_console_store import (
    MoveDependent,
    MoveSpec,
    RecordsMove,
    RecordsStores,
    run_moves,
)

from .storage import SqliteChatStorage

MOVE_BUSY = "conversation.move_busy"
MOVE_NOT_FOUND = "not_found"
MOVE_FAILED = "conversation.move_failed"
"""``failed`` 이슈 코드: 실행 중 / 없는 id / 옮기다 실패(``details.id``)."""

_log = logging.getLogger("agent_console_mod_chat")


class MoveHook(Protocol):
    """대화를 옮길 때 같은 작업에 묶이는 딸린 기록 옮기기(``chat.move_hooks`` 항목)."""

    def busy(self, conversation_ids: Sequence[str]) -> set[str]:
        """지금 옮기면 안 되는(실행 중인) 대화 id."""
        ...

    def prepare(self, project_id: str, conversation_ids: Sequence[str]) -> RecordsMove | None:
        """그 대화들에 딸린 기록을 옮기는 작업(없으면 None). 아직 아무것도 쓰지 않는다."""
        ...


def conversation_transform(project_id: str) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """행 변환: 대화의 ``project_id``(열과 ``doc``)를 대상 프로젝트로."""

    def transform(table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table != "conversations":
            return row
        try:
            doc = json.loads(row["doc"])
        except (KeyError, TypeError, ValueError):
            doc = None
        if isinstance(doc, dict) and doc.get("project_id") != project_id:
            doc["project_id"] = project_id
            row["doc"] = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        row["project_id"] = project_id
        return row

    return transform


def _issue(code: str, message: str, conversation_id: str) -> Issue:
    return Issue(severity="error", code=code, message=message, details={"id": conversation_id})


class ConversationMover:
    """앱 DB(원본) -> 프로젝트 기록 DB(대상) 대화 옮기기.

    Args:
        source: 원본 엔진을 돌려주는 함수(앱 DB, 없으면 None).
        records: 기록 공간 저장소 고르기(``chat_records``). 대상 엔진은 ``writer(id).engine``.
        hooks: 지금 ``chat.move_hooks`` 항목들.
    """

    def __init__(
        self,
        source: Callable[[], Engine | None],
        records: RecordsStores[SqliteChatStorage],
        hooks: Callable[[], Sequence[MoveHook]] = lambda: (),
    ) -> None:
        self._source = source
        self._records = records
        self._hooks = hooks

    @property
    def available(self) -> bool:
        """원본 DB와 기록 공간 포트가 모두 있나."""
        return self._source() is not None and self._records.available

    def _units(self, request: RecordsMoveRequest, engine: Engine) -> tuple[list[str], list[Issue]]:
        failed: list[Issue] = []
        cols = [c["name"] for c in sa.inspect(engine).get_columns("conversations")]
        table = sa.table("conversations", *[sa.column(c) for c in cols])
        project = (
            table.c.project_id
            if "project_id" in table.c
            else sa.func.json_extract(table.c.doc, "$.project_id")
        )
        with engine.connect() as conn:
            if request.select == "ids":
                wanted = list(dict.fromkeys(request.ids or ()))
                found: set[str] = set()
                for i in range(0, len(wanted), 500):
                    stmt = sa.select(table.c.id).where(table.c.id.in_(wanted[i : i + 500]))
                    found.update(str(r[0]) for r in conn.execute(stmt))
                failed.extend(
                    _issue(MOVE_NOT_FOUND, "대화를 찾을 수 없습니다", i)
                    for i in wanted
                    if i not in found
                )
                return [i for i in wanted if i in found], failed
            where = (
                project == request.project_id if request.select == "project" else project.is_(None)
            )
            stmt = sa.select(table.c.id).where(where).order_by(table.c.created_at, table.c.id)
            return [str(r[0]) for r in conn.execute(stmt)], failed

    def move(self, request: RecordsMoveRequest) -> RecordsMoveResult:
        """요청대로 옮긴다. 대상 기록 DB를 못 쓰면 ``RecordsUnavailable``(409)이 그대로 난다.

        Raises:
            RecordsUnavailable: 기록 DB를 쓸 수 없다.
            UnknownSpace: 모르는 프로젝트.
        """
        engine = self._source()
        if engine is None:
            return RecordsMoveResult()
        target = self._records.writer(request.project_id).engine
        units, failed = self._units(request, engine)
        hooks = list(self._hooks())
        busy: set[str] = set()
        for hook in hooks:
            busy |= set(hook.busy(units))
        failed.extend(
            _issue(MOVE_BUSY, "실행 중인 턴이 있어 옮기지 않았습니다", i)
            for i in units
            if i in busy
        )
        units = [i for i in units if i not in busy]
        if not units:
            return RecordsMoveResult(failed=failed)
        spec = MoveSpec(
            "conversations",
            key="id",
            dependents=(MoveDependent("chat_queue", "conversation_id"),),
            transform=conversation_transform(request.project_id),
        )
        own = RecordsMove(engine, target, spec, units)
        taken = set(own.conflicts())  # 이미 있는 대화의 딸린 기록은 건드리지 않는다
        fresh = [u for u in units if u not in taken]
        moves: list[RecordsMove] = [own]
        if fresh:
            for hook in hooks:
                extra = hook.prepare(request.project_id, fresh)
                if extra is not None:
                    moves.append(extra)
        try:
            counts = run_moves(moves, remove_source=request.remove_source)[0]
        except Exception as exc:
            _log.exception("대화 옮기기 실패: %s", request.project_id)
            failed.extend(_issue(MOVE_FAILED, f"옮기지 못했습니다: {exc}", i) for i in units)
            return RecordsMoveResult(failed=failed)
        skipped = set(own.skipped_units)
        done = [u for u in fresh if u not in skipped]
        for hook in hooks:
            after = getattr(hook, "after_move", None)
            if callable(after) and done:
                try:
                    after(request.project_id, done)
                except Exception:
                    _log.exception("옮긴 뒤 훅 실패: %s", request.project_id)
        return RecordsMoveResult(moved=counts.moved, skipped=counts.skipped, failed=failed)


__all__ = [
    "MOVE_BUSY",
    "MOVE_FAILED",
    "MOVE_NOT_FOUND",
    "ConversationMover",
    "MoveHook",
    "conversation_transform",
]
