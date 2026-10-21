"""SQLite 구현(SQLAlchemy 2 Core). `open_sqlite()`로 열면 마이그레이션까지 적용된다.

의존: sqlalchemy. 대안: 표준 `sqlite3` 직접 사용(agent_bench 방식; 스키마 이력·이식성 약함).
인터페이스가 동기식인 이유: 이벤트 한 건 저장이 마이크로~밀리초 단위의 로컬 쓰기라
asyncio 루프에서 직접 호출해도 되고, 무거운 호출은 앱이 스레드풀로 감싼다.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import sqlite3
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.pool import StaticPool

from agent_console_contracts import (
    INTERACTION_CLOSED_STATUSES,
    DefinitionVersion,
    ErrorInfo,
    Interaction,
    InteractionStatus,
    NodeRun,
    Run,
    RunEvent,
    RunEventBase,
    RunStatus,
)

from . import schema as t
from .errors import EventConflict, InteractionClosed, NotFound
from .memory import (
    UNFINISHED_STATUSES,
    check_close_status,
    closed_copy,
    event_node_id,
    status_set,
)
from .migrate import upgrade


def create_sqlite_engine(target: str | Path, *, journal_mode: str = "WAL") -> Engine:
    """SQLite 엔진. `target`은 파일 경로, `":memory:"`, 또는 `sqlite:///...` URL.

    `journal_mode`: 기본 WAL. 지원하지 않는 파일시스템이면 SQLite 기본값으로 둔다.
    """
    text = str(target)
    if text == ":memory:" or text == "sqlite://" or text.startswith("sqlite:///:memory:"):
        engine = sa.create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        if text.startswith("sqlite"):
            url = text
        else:
            path = Path(text)
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{path.as_posix()}"
        engine = sa.create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @sa.event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA journal_mode={journal_mode}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
        finally:
            cursor.close()

    return engine


def _json(model: Any) -> str:
    return str(model.model_dump_json())


class SqliteVersionRepository:
    """`VersionRepository`의 SQLite 구현. 본문 스냅샷은 `content_blobs`에 내용 주소로 둔다."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        kind: str,
        id: str,
        version_hash: str,
        content: Mapping[str, Any],
        *,
        saved_at: float,
        message: str = "",
        files: Mapping[str, bytes] | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "kind": kind,
            "def_id": id,
            "version_hash": version_hash,
            "saved_at": saved_at,
            "message": message,
            "content": json.dumps(content, ensure_ascii=False),
        }
        refs: dict[str, str] = {}
        blobs: list[dict[str, Any]] = []
        if files is not None:
            for path, data in files.items():
                sha = hashlib.sha256(data).hexdigest()
                refs[path] = sha
                blobs.append({"sha256": sha, "size": len(data), "data": bytes(data)})
            values["content_files"] = json.dumps(refs, ensure_ascii=False, sort_keys=True)
        stmt = sqlite_insert(t.definition_versions).values(**values)
        update = {
            "saved_at": stmt.excluded.saved_at,
            "message": stmt.excluded.message,
            "content": stmt.excluded.content,
        }
        if files is not None:
            update["content_files"] = stmt.excluded.content_files
        stmt = stmt.on_conflict_do_update(
            index_elements=["kind", "def_id", "version_hash"], set_=update
        )
        with self._engine.begin() as conn:
            for blob in blobs:
                conn.execute(sqlite_insert(t.content_blobs).values(**blob).on_conflict_do_nothing())
            conn.execute(stmt)

    def saved_at(self, kind: str, id: str, version_hash: str) -> float | None:
        stmt = sa.select(t.definition_versions.c.saved_at).where(
            t.definition_versions.c.kind == kind,
            t.definition_versions.c.def_id == id,
            t.definition_versions.c.version_hash == version_hash,
        )
        with self._engine.connect() as conn:
            value = conn.execute(stmt).scalar()
        return None if value is None else float(value)

    def list(self, kind: str, id: str) -> list[DefinitionVersion]:
        c = t.definition_versions.c
        stmt = (
            sa.select(c.version_hash, c.saved_at, c.message)
            .where(c.kind == kind, c.def_id == id)
            .order_by(c.saved_at.desc(), c.version_hash)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [
            DefinitionVersion(
                kind=kind,
                id=id,
                version_hash=r.version_hash,
                saved_at=r.saved_at,
                message=r.message,
            )
            for r in rows
        ]

    def get(self, kind: str, id: str, version_hash: str) -> DefinitionVersion | None:
        c = t.definition_versions.c
        stmt = sa.select(c.saved_at, c.message, c.content).where(
            c.kind == kind, c.def_id == id, c.version_hash == version_hash
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        if row is None:
            return None
        return DefinitionVersion(
            kind=kind,
            id=id,
            version_hash=version_hash,
            saved_at=row.saved_at,
            message=row.message,
            content=json.loads(row.content),
        )

    def files(self, kind: str, id: str, version_hash: str) -> dict[str, str] | None:
        c = t.definition_versions.c
        stmt = sa.select(c.content_files).where(
            c.kind == kind, c.def_id == id, c.version_hash == version_hash
        )
        with self._engine.connect() as conn:
            raw = conn.execute(stmt).scalar()
        if raw is None:
            return None
        loaded = json.loads(raw)
        return {str(k): str(v) for k, v in loaded.items()}

    def blob_size(self, sha256: str) -> int | None:
        stmt = sa.select(t.content_blobs.c.size).where(t.content_blobs.c.sha256 == sha256)
        with self._engine.connect() as conn:
            value = conn.execute(stmt).scalar()
        return None if value is None else int(value)

    def read_blob(self, sha256: str) -> bytes | None:
        stmt = sa.select(t.content_blobs.c.data).where(t.content_blobs.c.sha256 == sha256)
        with self._engine.connect() as conn:
            value = conn.execute(stmt).scalar()
        return None if value is None else bytes(value)

    def trim(self, kind: str, id: str, *, keep: int, protect: Collection[str] = ()) -> int:
        keep = max(keep, 0)
        c = t.definition_versions.c
        with self._engine.begin() as conn:
            keepers = set(protect)
            if kind == "graph":  # Run이 가리키는 버전은 과거 Run 조회에 필요하다
                keepers |= set(
                    conn.execute(
                        sa.select(t.runs.c.graph_version).where(t.runs.c.graph_id == id).distinct()
                    ).scalars()
                )
            hashes = list(
                conn.execute(
                    sa.select(c.version_hash)
                    .where(c.kind == kind, c.def_id == id)
                    .order_by(c.saved_at.desc(), c.version_hash)
                ).scalars()
            )
            candidates = [h for h in hashes if h not in keepers]
            allowed = max(keep - len(keepers & set(hashes)), 0)
            doomed = candidates[allowed:]
            for version_hash in doomed:
                conn.execute(
                    sa.delete(t.definition_versions).where(
                        c.kind == kind, c.def_id == id, c.version_hash == version_hash
                    )
                )
        return len(doomed)

    def prune_blobs(self) -> int:
        with self._engine.begin() as conn:
            used: set[str] = set()
            for raw in conn.execute(
                sa.select(t.definition_versions.c.content_files).where(
                    t.definition_versions.c.content_files.is_not(None)
                )
            ).scalars():
                used.update(str(v) for v in json.loads(raw).values())
            doomed = [
                sha
                for sha in conn.execute(sa.select(t.content_blobs.c.sha256)).scalars()
                if sha not in used
            ]
            for sha in doomed:
                conn.execute(sa.delete(t.content_blobs).where(t.content_blobs.c.sha256 == sha))
        return len(doomed)


class SqliteRunRepository:
    """Run·NodeRun 저장.

    계보 `runs`의 새 열(`root_run_id`·`parent_node_id`·`call`·`invoked_by`, design §5R.10)이 DB에
    있으면 읽고 쓴다. 없으면(계보를 올리지 않은 단독 사용) 값은 `doc`에만 남고 `root_run_id` 조회는
    `doc`의 JSON을 훑는다(느리지만 같은 결과). 이 경우 같은 노드의 호출 NodeRun(`call`)은 키에
    들어가지 못해 덮어쓴다(호출 NodeRun은 계보가 있을 때만 구분된다).
    열의 유무는 만들 때 한 번 본다.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lineage = t.runs_lineage_active(engine)
        self._project = self._lineage and t.runs_project_active(engine)
        self._runs = t.runs_v2 if self._lineage else t.runs
        self._node_runs = t.node_runs_v2 if self._lineage else t.node_runs

    def save(self, run: Run) -> None:
        values = {
            "id": run.id,
            "graph_id": run.graph_id,
            "graph_version": run.graph_version,
            "status": run.status,
            "origin": run.origin,
            "parent_run_id": run.parent_run_id,
            "conversation_id": run.conversation_id,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "resumed_from": run.resumed_from,
            "doc": _json(run),
        }
        if self._lineage:
            values["parent_node_id"] = run.parent_node_id
            values["root_run_id"] = run.root_run_id
        if self._project:
            values["project_id"] = run.project_id
        stmt = sqlite_insert(self._runs).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={k: v for k, v in values.items() if k != "id"}
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def get(self, run_id: str) -> Run | None:
        with self._engine.connect() as conn:
            doc = conn.execute(sa.select(t.runs.c.doc).where(t.runs.c.id == run_id)).scalar()
        return None if doc is None else Run.model_validate_json(doc)

    def list(
        self,
        *,
        graph_id: str | None = None,
        status: Iterable[RunStatus] | None = None,
        parent_run_id: str | None = None,
        conversation_id: str | None = None,
        agent: str | None = None,
        resumed_from: str | None = None,
        root_run_id: str | None = None,
        project_id: str | None = None,
        root_only: bool = False,
        limit: int | None = None,
    ) -> list[Run]:
        stmt = sa.select(self._runs.c.doc)
        if project_id is not None:
            stmt = stmt.where(
                self._runs.c.project_id == project_id
                if self._project
                else sa.func.json_extract(self._runs.c.doc, "$.project_id") == project_id
            )
        if root_only:
            stmt = stmt.where(
                self._runs.c.root_run_id.is_(None)
                if self._lineage
                else sa.func.json_extract(self._runs.c.doc, "$.root_run_id").is_(None)
            )
        if root_run_id is not None:
            stmt = stmt.where(
                self._runs.c.root_run_id == root_run_id
                if self._lineage
                else sa.func.json_extract(self._runs.c.doc, "$.root_run_id") == root_run_id
            )
        if resumed_from is not None:
            stmt = stmt.where(self._runs.c.resumed_from == resumed_from)
        if conversation_id is not None:
            stmt = stmt.where(self._runs.c.conversation_id == conversation_id)
        if agent is not None:
            stmt = stmt.where(
                self._runs.c.id.in_(
                    sa.select(t.run_events.c.run_id).where(t.run_events.c.actor == agent)
                )
            )
        if graph_id is not None:
            stmt = stmt.where(self._runs.c.graph_id == graph_id)
        if status is not None:
            stmt = stmt.where(self._runs.c.status.in_(list(status)))
        if parent_run_id is not None:
            stmt = stmt.where(self._runs.c.parent_run_id == parent_run_id)
        stmt = stmt.order_by(self._runs.c.created_at.desc(), self._runs.c.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._engine.connect() as conn:
            return [Run.model_validate_json(d) for d in conn.execute(stmt).scalars()]

    def save_node_run(self, node_run: NodeRun) -> None:
        values = {
            "run_id": node_run.run_id,
            "node_id": node_run.node_id,
            "attempt": node_run.attempt,
            "iteration": node_run.iteration,
            "status": node_run.status,
            "node_type": node_run.node_type,
            "started_at": node_run.started_at,
            "ended_at": node_run.ended_at,
            "duration_ms": node_run.duration_ms,
            "doc": _json(node_run),
        }
        key = ["run_id", "node_id", "attempt", "iteration"]
        if self._lineage:
            values["call"] = node_run.call
            values["invoked_by"] = node_run.invoked_by
            key.append("call")
        stmt = sqlite_insert(self._node_runs).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=key, set_={k: v for k, v in values.items() if k not in key}
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        c = self._node_runs.c
        order = [c.started_at.is_(None), c.started_at, c.node_id, c.attempt, c.iteration]
        if self._lineage:
            order.append(self._node_runs.c.call)
        stmt = sa.select(c.doc).where(c.run_id == run_id).order_by(*order)
        with self._engine.connect() as conn:
            return [NodeRun.model_validate_json(d) for d in conn.execute(stmt).scalars()]

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]:
        ids: list[str] = []
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.select(t.runs.c.doc).where(t.runs.c.status.in_(list(UNFINISHED_STATUSES)))
            ).scalars()
            for doc in list(rows):
                run = Run.model_validate_json(doc)
                run.status = "interrupted"
                run.ended_at = ended_at
                if error is not None:
                    run.error = error
                conn.execute(
                    sa.update(t.runs)
                    .where(t.runs.c.id == run.id)
                    .values(status=run.status, ended_at=ended_at, doc=_json(run))
                )
                ids.append(run.id)
        return sorted(ids)

    def delete(self, run_id: str) -> bool:
        with self._engine.begin() as conn:
            for table in (t.run_events, t.node_runs, t.routing_decisions, t.interactions):
                conn.execute(sa.delete(table).where(table.c.run_id == run_id))
            result = conn.execute(sa.delete(t.runs).where(t.runs.c.id == run_id))
        return result.rowcount > 0


def _with_type_prefix(stmt: sa.Select[Any], prefix: str | None) -> sa.Select[Any]:
    """`type`이 `prefix`로 시작하는 행만. LIKE는 대소문자를 가리지 않아 범위 비교를 쓴다
    (인덱스도 탄다)."""
    if not prefix:
        return stmt
    column = t.run_events.c.type
    upper = prefix[:-1] + chr(ord(prefix[-1]) + 1) if ord(prefix[-1]) < 0x10FFFF else None
    stmt = stmt.where(column >= prefix)
    return stmt if upper is None else stmt.where(column < upper)


class SqliteEventRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _insert(conn: Connection, event: RunEventBase) -> bool:
        body = RunEvent.model_validate(event.model_dump(mode="json"))
        stmt = (
            sqlite_insert(t.run_events)
            .values(
                run_id=body.run_id,
                seq=body.seq,
                event_id=body.event_id,
                ts=body.ts,
                type=body.type,
                node_id=event_node_id(body),
                attempt=body.attempt,
                actor=body.actor,
                body=_json(body),
            )
            .on_conflict_do_nothing()
        )
        if conn.execute(stmt).rowcount == 1:
            return True
        existing = conn.execute(
            sa.select(t.run_events.c.event_id).where(
                t.run_events.c.run_id == body.run_id, t.run_events.c.seq == body.seq
            )
        ).scalar()
        if existing is not None and existing != body.event_id:
            raise EventConflict(f"{body.run_id}#{body.seq} already has another event")
        return False

    def append(self, event: RunEventBase) -> bool:
        with self._engine.begin() as conn:
            return self._insert(conn, event)

    def append_many(self, events: Sequence[RunEventBase]) -> int:
        with self._engine.begin() as conn:
            return sum(self._insert(conn, e) for e in events)

    def list(
        self,
        run_id: str,
        *,
        since_seq: int = 0,
        limit: int | None = None,
        actor: str | None = None,
        type_prefix: str | None = None,
    ) -> builtins.list[RunEvent]:
        c = t.run_events.c
        stmt = sa.select(c.body).where(c.run_id == run_id, c.seq > since_seq).order_by(c.seq)
        if actor is not None:
            stmt = stmt.where(c.actor == actor)
        stmt = _with_type_prefix(stmt, type_prefix)
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._engine.connect() as conn:
            return [RunEvent.model_validate_json(b) for b in conn.execute(stmt).scalars()]

    def _newest(self, stmt: sa.Select[Any], limit: int | None) -> builtins.list[RunEvent]:
        c = t.run_events.c
        stmt = stmt.order_by(c.ts.desc(), c.run_id.desc(), c.seq.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._engine.connect() as conn:
            return [RunEvent.model_validate_json(b) for b in conn.execute(stmt).scalars()]

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]:
        c = t.run_events.c
        stmt = sa.select(c.body).where(c.type == type)
        if run_id is not None:
            stmt = stmt.where(c.run_id == run_id)
        if actor is not None:
            stmt = stmt.where(c.actor == actor)
        return self._newest(stmt, limit)

    def list_by_actor(
        self,
        actor: str,
        *,
        since: float | None = None,
        type_prefix: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[RunEvent]:
        c = t.run_events.c
        stmt = sa.select(c.body).where(c.actor == actor)
        if since is not None:
            stmt = stmt.where(c.ts >= since)
        return self._newest(_with_type_prefix(stmt, type_prefix), limit)

    def last_seq(self, run_id: str) -> int:
        stmt = sa.select(sa.func.max(t.run_events.c.seq)).where(t.run_events.c.run_id == run_id)
        with self._engine.connect() as conn:
            return int(conn.execute(stmt).scalar() or 0)


class SqliteInteractionRepository:
    """상호작용 저장. `root_run_id` 열은 계보 `runs`가 있을 때만 쓴다(없으면 `doc`을 훑는다)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lineage = t.runs_lineage_active(engine)
        self._table = t.interactions_v2 if self._lineage else t.interactions

    def _columns(self, interaction: Interaction) -> dict[str, Any]:
        values = self._base_columns(interaction)
        if self._lineage:
            values["root_run_id"] = interaction.root_run_id
        return values

    @staticmethod
    def _base_columns(interaction: Interaction) -> dict[str, Any]:
        return {
            "run_id": interaction.run_id,
            "conversation_id": interaction.conversation_id,
            "node_id": interaction.node_id,
            "actor": interaction.actor,
            "kind": interaction.kind,
            "status": interaction.status,
            "created_at": interaction.created_at,
            "closed_at": interaction.closed_at,
            "doc": _json(interaction),
        }

    def save(self, interaction: Interaction) -> bool:
        values = {"id": interaction.id, **self._columns(interaction)}
        stmt = sqlite_insert(self._table).values(**values)
        # 닫힌 행은 덮어쓰지 않는다: 충돌 시 갱신은 기존 행이 pending일 때만.
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: v for k, v in values.items() if k != "id"},
            where=t.interactions.c.status == "pending",
        )
        with self._engine.begin() as conn:
            return conn.execute(stmt).rowcount == 1

    def get(self, interaction_id: str) -> Interaction | None:
        stmt = sa.select(t.interactions.c.doc).where(t.interactions.c.id == interaction_id)
        with self._engine.connect() as conn:
            doc = conn.execute(stmt).scalar()
        return None if doc is None else Interaction.model_validate_json(doc)

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: InteractionStatus | Iterable[InteractionStatus] | None = None,
        root_run_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Interaction]:
        c = self._table.c
        stmt = sa.select(c.doc)
        if run_id is not None:
            stmt = stmt.where(c.run_id == run_id)
        if root_run_id is not None:
            root = (
                self._table.c.root_run_id
                if self._lineage
                else sa.func.json_extract(c.doc, "$.root_run_id")
            )
            stmt = stmt.where(sa.or_(c.run_id == root_run_id, root == root_run_id))
        if conversation_id is not None:
            stmt = stmt.where(c.conversation_id == conversation_id)
        statuses = status_set(status)
        if statuses is not None:
            stmt = stmt.where(c.status.in_(statuses))
        stmt = stmt.order_by(c.created_at, c.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._engine.connect() as conn:
            return [Interaction.model_validate_json(d) for d in conn.execute(stmt).scalars()]

    @staticmethod
    def _close_row(conn: Connection, closed: Interaction) -> bool:
        """`status='pending'` 조건부 갱신. 이 호출이 이겼으면 True."""
        c = t.interactions.c
        result = conn.execute(
            sa.update(t.interactions)
            .where(c.id == closed.id, c.status == "pending")
            .values(
                status=closed.status,
                closed_at=closed.closed_at,
                doc=_json(closed),
            )
        )
        return result.rowcount == 1

    def close(
        self,
        interaction_id: str,
        *,
        status: InteractionStatus,
        closed_at: float,
        response: dict[str, Any] | None = None,
        answered_by: str | None = None,
        close_reason: str | None = None,
    ) -> Interaction:
        check_close_status(status, INTERACTION_CLOSED_STATUSES)
        with self._engine.begin() as conn:
            doc = conn.execute(
                sa.select(t.interactions.c.doc).where(t.interactions.c.id == interaction_id)
            ).scalar()
            if doc is None:
                raise NotFound(f"interaction/{interaction_id}")
            current = Interaction.model_validate_json(doc)
            closed = closed_copy(
                current,
                status=status,
                closed_at=closed_at,
                response=response,
                answered_by=answered_by,
                close_reason=close_reason,
            )
            if current.status == "pending" and self._close_row(conn, closed):
                return closed
        # 졌다: 먼저 닫은 쪽의 상태를 다시 읽어 알려 준다.
        latest = self.get(interaction_id)
        if latest is None:
            raise NotFound(f"interaction/{interaction_id}")
        raise InteractionClosed(latest)

    def close_pending(
        self,
        *,
        status: InteractionStatus,
        closed_at: float,
        run_id: str | None = None,
        answered_by: str | None = "system",
        close_reason: str | None = None,
    ) -> builtins.list[Interaction]:
        check_close_status(status, ("expired", "cancelled"))
        c = t.interactions.c
        stmt = sa.select(c.doc).where(c.status == "pending").order_by(c.created_at, c.id)
        if run_id is not None:
            stmt = stmt.where(c.run_id == run_id)
        result: list[Interaction] = []
        with self._engine.begin() as conn:
            for doc in list(conn.execute(stmt).scalars()):
                closed = closed_copy(
                    Interaction.model_validate_json(doc),
                    status=status,
                    closed_at=closed_at,
                    response=None,
                    answered_by=answered_by,
                    close_reason=close_reason,
                )
                if self._close_row(conn, closed):
                    result.append(closed)
        return result

    def pending_counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, int]:
        c = t.interactions.c
        stmt = (
            sa.select(c.conversation_id, sa.func.count())
            .where(c.status == "pending", c.conversation_id.is_not(None))
            .group_by(c.conversation_id)
        )
        if conversation_ids is not None:
            stmt = stmt.where(c.conversation_id.in_(list(conversation_ids)))
        with self._engine.connect() as conn:
            return {str(cid): int(n) for cid, n in conn.execute(stmt)}


class SqliteStorage:
    """SQLite 위의 런타임 기록 묶음: `runs`, `events`, `versions`, `interactions`."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.versions = SqliteVersionRepository(engine)
        self.runs = SqliteRunRepository(engine)
        self.events = SqliteEventRepository(engine)
        self.interactions = SqliteInteractionRepository(engine)

    def close(self) -> None:
        """엔진의 연결을 모두 닫는다."""
        self.engine.dispose()


def open_sqlite(
    target: str | Path, *, migrate: bool = True, journal_mode: str = "WAL"
) -> SqliteStorage:
    """SQLite 저장소를 연다.

    Args:
        target: DB 파일 경로(상위 폴더는 만든다), `":memory:"`, 또는 `sqlite:///...` URL.
        migrate: True면 Alembic `head`까지 적용한다.
        journal_mode: SQLite journal_mode(기본 WAL).
    """
    engine = create_sqlite_engine(target, journal_mode=journal_mode)
    if migrate:
        upgrade(engine)
    return SqliteStorage(engine)
