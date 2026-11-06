"""앱 DB의 옛 Run 기록을 프로젝트 기록 DB로 옮긴다(design §PI.4.6.7, K33-32, 5.7R.33j2).

`POST /runs/move-to-project`의 도메인 부분. 이 모듈은 프로젝트를 모른다 - ``project_id``는 불투명
문자열이고 대상 기록 DB는 ``RecordsStores.writer(project_id)``가 준다.

- 한 묶음 = 루트 Run 하나와 그 자손(``root_run_id``). ``runs``·``node_runs``·``run_events``·
  ``interactions``(와 있으면 ``run_labels``)의 행을 함께 옮긴다.
- 순서: 대상에 한 트랜잭션으로 복사(같은 id는 ``skipped``) -> 행 수·값 확인 -> 원본 삭제
  (``remove_source``). 도중에 실패하면 대상을 되돌리고 원본은 그대로다
  (``agent_console_store.run_moves``).
- 끝나지 않은 Run이 있는 묶음은 옮기지 않고 ``failed``(``run.move_busy``)로 알린다(실행기가 나중에
  저장하면 덮어쓰므로). 끝난 Run은 ``host_id``를 그대로 둔다(복구 대상이 아니다).
- 대화를 옮길 때는 ``link-chat-runs``가 대화 모듈의 옮기기 훅(``chat.move_hooks``)으로
  ``conversation_hook``을 건다: 대화의 ``conversation_id``를 가진 Run을 같은 작업에 묶는다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from agent_console_contracts import Issue, RecordsMoveRequest, RecordsMoveResult
from agent_console_store import (
    MoveDependent,
    MoveSpec,
    RecordsMove,
    RecordsStores,
    SqliteStorage,
    run_moves,
)

UNFINISHED = ("queued", "running", "paused", "waiting")
"""끝나지 않은 Run 상태(이 묶음은 옮기지 않는다)."""

MOVE_BUSY = "run.move_busy"
MOVE_NOT_FOUND = "not_found"
MOVE_FAILED = "run.move_failed"
"""``failed`` 이슈 코드: 실행 중 / 없는 id / 옮기다 실패(``details.id``)."""

RUN_DEPENDENTS: tuple[MoveDependent, ...] = (
    MoveDependent("node_runs", "run_id"),
    MoveDependent("run_events", "run_id"),
    MoveDependent("interactions", "run_id"),
    MoveDependent("run_labels", "run_id"),
)
"""Run 행에 딸린 표(없는 표는 건너뛴다 - 라벨 표는 계보 ``runs_0004`` 뒤에 생긴다)."""

_log = logging.getLogger("agent_console_mod_runs")


def _doc(row: dict[str, Any]) -> dict[str, Any]:
    try:
        found = json.loads(row["doc"])
    except (KeyError, TypeError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def run_transform(project_id: str) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """행 변환: Run의 ``project_id``(열과 ``doc``)를 대상 프로젝트로, 새 열은 ``doc``에서 채운다."""

    def transform(table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table == "runs":
            doc = _doc(row)
            if doc.get("project_id") != project_id:
                doc["project_id"] = project_id
                row["doc"] = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
            row["project_id"] = project_id
            for key in ("root_run_id", "parent_node_id"):
                row.setdefault(key, doc.get(key))
        elif table == "interactions":
            row.setdefault("root_run_id", _doc(row).get("root_run_id"))
        return row

    return transform


def _expand(conn: Connection, units: Sequence[str]) -> list[str]:
    """묶음(루트 Run) -> 자신과 자손 Run id."""
    out: list[str] = list(units)
    runs = _runs_table(conn)
    root = _root_expr(conn, runs)
    for i in range(0, len(units), 500):
        chunk = list(units[i : i + 500])
        out.extend(str(r[0]) for r in conn.execute(sa.select(runs.c.id).where(root.in_(chunk))))
    return out


def _runs_table(conn: Connection | Engine) -> sa.TableClause:
    cols = [c["name"] for c in sa.inspect(conn).get_columns("runs")]
    return sa.table("runs", *[sa.column(c) for c in cols])


def _root_expr(conn: Connection | Engine, runs: sa.TableClause) -> Any:
    return (
        runs.c.root_run_id
        if "root_run_id" in runs.c
        else sa.func.json_extract(runs.c.doc, "$.root_run_id")
    )


def _project_expr(runs: sa.TableClause) -> Any:
    return (
        runs.c.project_id
        if "project_id" in runs.c
        else sa.func.json_extract(runs.c.doc, "$.project_id")
    )


def _spec(project_id: str) -> MoveSpec:
    return MoveSpec(
        "runs", dependents=RUN_DEPENDENTS, expand=_expand, transform=run_transform(project_id)
    )


def _issue(code: str, message: str, run_id: str) -> Issue:
    return Issue(severity="error", code=code, message=message, details={"id": run_id})


class RunMover:
    """앱 DB(원본) -> 프로젝트 기록 DB(대상) Run 옮기기.

    Args:
        source: 원본 엔진을 돌려주는 함수(앱 DB. 없으면 None - 메모리 저장소).
        records: 기록 공간 저장소 고르기(``space_records``). 대상 엔진은 ``writer(id).engine``.
    """

    def __init__(
        self,
        source: Callable[[], Engine | None],
        records: RecordsStores[SqliteStorage],
    ) -> None:
        self._source = source
        self._records = records

    @property
    def available(self) -> bool:
        """원본 DB와 기록 공간 포트가 모두 있나."""
        return self._source() is not None and self._records.available

    # ------------------------------------------------------------------ 묶음 고르기

    def _units(self, request: RecordsMoveRequest, engine: Engine) -> tuple[list[str], list[Issue]]:
        failed: list[Issue] = []
        runs = _runs_table(engine)
        root, project = _root_expr(engine, runs), _project_expr(runs)
        with engine.connect() as conn:
            if request.select == "ids":
                wanted = list(dict.fromkeys(request.ids or ()))
                found: set[str] = set()
                for i in range(0, len(wanted), 500):
                    stmt = sa.select(runs.c.id).where(runs.c.id.in_(wanted[i : i + 500]))
                    found.update(str(r[0]) for r in conn.execute(stmt))
                failed.extend(
                    _issue(MOVE_NOT_FOUND, "Run을 찾을 수 없습니다", i)
                    for i in wanted
                    if i not in found
                )
                units = [i for i in wanted if i in found]
            else:
                where = (
                    project == request.project_id
                    if request.select == "project"
                    else project.is_(None)
                )
                stmt = (
                    sa.select(runs.c.id)
                    .where(where, root.is_(None))
                    .order_by(runs.c.created_at, runs.c.id)
                )
                units = [str(r[0]) for r in conn.execute(stmt)]
            busy = self._busy_units(conn, runs, root, units)
        failed.extend(
            _issue(MOVE_BUSY, "실행 중인 Run이 있어 옮기지 않았습니다", i)
            for i in units
            if i in busy
        )
        return [i for i in units if i not in busy], failed

    @staticmethod
    def _busy_units(
        conn: Connection, runs: sa.TableClause, root: Any, units: Sequence[str]
    ) -> set[str]:
        """끝나지 않은 Run을 가진 묶음(자신 또는 자손이 실행 중)."""
        busy: set[str] = set()
        for i in range(0, len(units), 500):
            chunk = list(units[i : i + 500])
            stmt = sa.select(runs.c.id, root).where(
                sa.or_(runs.c.id.in_(chunk), root.in_(chunk)), runs.c.status.in_(UNFINISHED)
            )
            for rid, root_id in conn.execute(stmt):
                busy.add(str(root_id if root_id is not None else rid))
        return busy

    # ------------------------------------------------------------------ 옮기기

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
        if not units:
            return RecordsMoveResult(failed=failed)
        move = RecordsMove(engine, target, _spec(request.project_id), units)
        try:
            counts = run_moves([move], remove_source=request.remove_source)[0]
        except Exception as exc:
            _log.exception("Run 옮기기 실패: %s", request.project_id)
            failed.extend(_issue(MOVE_FAILED, f"옮기지 못했습니다: {exc}", i) for i in units)
            return RecordsMoveResult(failed=failed)
        return RecordsMoveResult(moved=counts.moved, skipped=counts.skipped, failed=failed)

    # ------------------------------------------------------------------ 대화 연동(훅)

    def _conversation_units(self, conversation_ids: Sequence[str]) -> dict[str, str]:
        """대화 id를 가진 Run id -> 대화 id."""
        engine = self._source()
        if engine is None or not conversation_ids:
            return {}
        runs = _runs_table(engine)
        out: dict[str, str] = {}
        with engine.connect() as conn:
            for i in range(0, len(conversation_ids), 500):
                chunk = list(conversation_ids[i : i + 500])
                stmt = sa.select(runs.c.id, runs.c.conversation_id).where(
                    runs.c.conversation_id.in_(chunk)
                )
                out.update((str(r[0]), str(r[1])) for r in conn.execute(stmt))
        return out

    def conversation_hook(self) -> ConversationRunMove:
        """대화 모듈의 옮기기 훅(``link-chat-runs``가 ``chat.move_hooks``로 낸다)."""
        return ConversationRunMove(self)


class ConversationRunMove:
    """대화를 옮길 때 그 대화의 Run을 같은 작업으로 옮기는 훅(대화 모듈 ``MoveHook`` 모양)."""

    def __init__(self, mover: RunMover) -> None:
        self._mover = mover

    def busy(self, conversation_ids: Sequence[str]) -> set[str]:
        """끝나지 않은 Run을 가진 대화 id(그 대화의 Run 묶음 안에 실행 중인 Run이 있다)."""
        mover = self._mover
        engine = mover._source()
        by_run = mover._conversation_units(conversation_ids)
        if engine is None or not by_run:
            return set()
        runs = _runs_table(engine)
        with engine.connect() as conn:
            live = mover._busy_units(conn, runs, _root_expr(engine, runs), list(by_run))
        return {by_run[r] for r in live}

    def prepare(self, project_id: str, conversation_ids: Sequence[str]) -> RecordsMove | None:
        """그 대화들의 Run을 옮기는 작업(없으면 None). 아직 아무것도 쓰지 않는다."""
        mover = self._mover
        engine = mover._source()
        units = list(mover._conversation_units(conversation_ids))
        if engine is None or not units:
            return None
        return RecordsMove(
            engine, mover._records.writer(project_id).engine, _spec(project_id), units
        )


__all__ = [
    "MOVE_BUSY",
    "MOVE_FAILED",
    "MOVE_NOT_FOUND",
    "RUN_DEPENDENTS",
    "ConversationRunMove",
    "RunMover",
    "run_transform",
]
