"""인메모리 구현(테스트·임시 실행용). SQLite 구현과 같은 규칙을 따른다."""

from __future__ import annotations

import builtins
import copy
import hashlib
import threading
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any

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

from .errors import EventConflict, InteractionClosed, NotFound
from .project_assign import AssignCandidate

UNFINISHED_STATUSES: tuple[RunStatus, ...] = ("queued", "running", "paused", "waiting")
"""종료되지 않은 Run 상태(`interrupt_unfinished` 대상)."""


def event_node_id(event: RunEventBase | RunEvent) -> str | None:
    """이벤트가 속한 이 Run의 노드 id(`node_path[0]`). Run 수준 이벤트는 None."""
    return event.node_path[0] if event.node_path else None


class InMemoryVersionRepository:
    """`VersionRepository`의 메모리 구현.

    Args:
        protected: (kind, id) -> 보존 개수와 상관없이 지우지 않을 버전 해시들(예: Run이 참조하는
            그래프 버전). 생략하면 `trim`의 `protect`만 쓴다.
    """

    def __init__(self, protected: Callable[[str, str], Collection[str]] | None = None) -> None:
        self._rows: dict[tuple[str, str, str], DefinitionVersion] = {}
        self._files: dict[tuple[str, str, str], dict[str, str]] = {}
        self._blobs: dict[str, bytes] = {}
        self._protected = protected
        self._lock = threading.RLock()

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
        with self._lock:
            self._rows[(kind, id, version_hash)] = DefinitionVersion(
                kind=kind,
                id=id,
                version_hash=version_hash,
                saved_at=saved_at,
                message=message,
                content=copy.deepcopy(dict(content)),
            )
            if files is not None:
                refs: dict[str, str] = {}
                for path, data in files.items():
                    sha = hashlib.sha256(data).hexdigest()
                    self._blobs.setdefault(sha, bytes(data))
                    refs[path] = sha
                self._files[(kind, id, version_hash)] = refs

    def saved_at(self, kind: str, id: str, version_hash: str) -> float | None:
        with self._lock:
            row = self._rows.get((kind, id, version_hash))
            return None if row is None else row.saved_at

    def list(self, kind: str, id: str) -> list[DefinitionVersion]:
        with self._lock:
            rows = [r for (k, i, _), r in self._rows.items() if k == kind and i == id]
        rows.sort(key=lambda r: (-r.saved_at, r.version_hash))
        return [r.model_copy(update={"content": None}) for r in rows]

    def get(self, kind: str, id: str, version_hash: str) -> DefinitionVersion | None:
        with self._lock:
            row = self._rows.get((kind, id, version_hash))
            return None if row is None else row.model_copy(deep=True)

    def files(self, kind: str, id: str, version_hash: str) -> dict[str, str] | None:
        with self._lock:
            refs = self._files.get((kind, id, version_hash))
            return None if refs is None else dict(refs)

    def blob_size(self, sha256: str) -> int | None:
        with self._lock:
            blob = self._blobs.get(sha256)
            return None if blob is None else len(blob)

    def read_blob(self, sha256: str) -> bytes | None:
        with self._lock:
            return self._blobs.get(sha256)

    def trim(self, kind: str, id: str, *, keep: int, protect: Collection[str] = ()) -> int:
        keep = max(keep, 0)
        with self._lock:
            keepers = set(protect)
            if self._protected is not None:
                keepers |= set(self._protected(kind, id))
            rows = [r for (k, i, _), r in self._rows.items() if k == kind and i == id]
            rows.sort(key=lambda r: (-r.saved_at, r.version_hash))
            candidates = [r for r in rows if r.version_hash not in keepers]
            allowed = max(keep - len(keepers & {r.version_hash for r in rows}), 0)
            doomed = candidates[allowed:]
            for row in doomed:
                self._rows.pop((kind, id, row.version_hash), None)
                self._files.pop((kind, id, row.version_hash), None)
            return len(doomed)

    def prune_blobs(self) -> int:
        with self._lock:
            used = {sha for refs in self._files.values() for sha in refs.values()}
            doomed = [sha for sha in self._blobs if sha not in used]
            for sha in doomed:
                del self._blobs[sha]
            return len(doomed)


class InMemoryStorage:
    """런타임 기록(`runs`, `events`, `versions`, `interactions`)을
    한 상태 위에 묶은 인메모리 묶음.

    Run 삭제가 이벤트·상호작용까지 지우고, `agent` 필터가 이벤트를 볼 수 있도록
    상태를 공유한다.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, Run] = {}
        self._node_runs: dict[str, dict[tuple[str, int, int, int], NodeRun]] = defaultdict(dict)
        self._events: dict[str, dict[int, RunEvent]] = defaultdict(dict)
        self._event_ids: dict[str, set[str]] = defaultdict(set)
        self._interactions: dict[str, Interaction] = {}
        self.versions = InMemoryVersionRepository(self._referenced_graph_versions)
        self.runs = InMemoryRunRepository(self)
        self.events = InMemoryEventRepository(self)
        self.interactions = InMemoryInteractionRepository(self)

    def _referenced_graph_versions(self, kind: str, id: str) -> set[str]:
        """Run이 가리키는 그래프 버전(보존 개수 정리에서 지키는 대상)."""
        if kind != "graph":
            return set()
        with self._lock:
            return {r.graph_version for r in self._runs.values() if r.graph_id == id}

    def close(self) -> None:
        """SQLite 구현과 같은 모양을 맞추기 위한 no-op."""


class InMemoryRunRepository:
    def __init__(self, state: InMemoryStorage) -> None:
        self._s = state

    def save(self, run: Run) -> None:
        with self._s._lock:
            self._s._runs[run.id] = run.model_copy(deep=True)

    def get(self, run_id: str) -> Run | None:
        with self._s._lock:
            run = self._s._runs.get(run_id)
            return None if run is None else run.model_copy(deep=True)

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
        statuses = None if status is None else set(status)
        with self._s._lock:
            rows = [
                r
                for r in self._s._runs.values()
                if (graph_id is None or r.graph_id == graph_id)
                and (statuses is None or r.status in statuses)
                and (parent_run_id is None or r.parent_run_id == parent_run_id)
                and (conversation_id is None or r.conversation_id == conversation_id)
                and (resumed_from is None or r.resumed_from == resumed_from)
                and (root_run_id is None or r.root_run_id == root_run_id)
                and (project_id is None or r.project_id == project_id)
                and (not root_only or r.root_run_id is None)
                and (
                    agent is None
                    or any(e.actor == agent for e in self._s._events.get(r.id, {}).values())
                )
            ]
        rows.sort(key=lambda r: (r.created_at, r.id), reverse=True)
        return [r.model_copy(deep=True) for r in rows[:limit]]

    # ------------------------------------------------ 프로젝트 넣기·개수(`ProjectAssignStore`)

    def project_id_counts(self) -> dict[str | None, int]:
        """루트 Run의 project_id별 개수."""
        out: dict[str | None, int] = {}
        with self._s._lock:
            for r in self._s._runs.values():
                if r.root_run_id is None:
                    out[r.project_id] = out.get(r.project_id, 0) + 1
        return out

    def candidates(self, ids: Collection[str] | None) -> builtins.list[AssignCandidate]:
        wanted = None if ids is None else set(ids)
        with self._s._lock:
            return [
                AssignCandidate(r.id, r.project_id, r.root_run_id, r.status in UNFINISHED_STATUSES)
                for r in self._s._runs.values()
                if (
                    r.project_id is None
                    if wanted is None
                    else r.id in wanted or r.root_run_id in wanted
                )
            ]

    def set_project(self, ids: Collection[str], project_id: str) -> int:
        changed = 0
        with self._s._lock:
            for rid in ids:
                run = self._s._runs.get(rid)
                if run is not None:
                    run.project_id = project_id
                    changed += 1
        return changed

    def save_node_run(self, node_run: NodeRun) -> None:
        key = (node_run.node_id, node_run.attempt, node_run.iteration, node_run.call)
        with self._s._lock:
            self._s._node_runs[node_run.run_id][key] = node_run.model_copy(deep=True)

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        with self._s._lock:
            rows = list(self._s._node_runs.get(run_id, {}).values())
        rows.sort(
            key=lambda n: (
                n.started_at is None,
                n.started_at or 0.0,
                n.node_id,
                n.attempt,
                n.iteration,
                n.call,
            )
        )
        return [n.model_copy(deep=True) for n in rows]

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]:
        ids: list[str] = []
        with self._s._lock:
            for run in self._s._runs.values():
                if run.status in UNFINISHED_STATUSES:
                    run.status = "interrupted"
                    run.ended_at = ended_at
                    if error is not None:
                        run.error = error
                    ids.append(run.id)
        return sorted(ids)

    def delete(self, run_id: str) -> bool:
        with self._s._lock:
            existed = self._s._runs.pop(run_id, None) is not None
            self._s._node_runs.pop(run_id, None)
            self._s._events.pop(run_id, None)
            self._s._event_ids.pop(run_id, None)
            self._s._interactions = {
                k: v for k, v in self._s._interactions.items() if v.run_id != run_id
            }
        return existed


class InMemoryEventRepository:
    def __init__(self, state: InMemoryStorage) -> None:
        self._s = state

    def _append(self, event: RunEventBase) -> bool:
        stored = RunEvent.model_validate(event.model_dump(mode="json"))
        existing = self._s._events[stored.run_id].get(stored.seq)
        if existing is not None:
            if existing.event_id == stored.event_id:
                return False
            raise EventConflict(f"{stored.run_id}#{stored.seq} already has another event")
        ids = self._s._event_ids[stored.run_id]
        if stored.event_id in ids:
            return False
        ids.add(stored.event_id)
        self._s._events[stored.run_id][stored.seq] = stored
        return True

    def append(self, event: RunEventBase) -> bool:
        with self._s._lock:
            return self._append(event)

    def append_many(self, events: Sequence[RunEventBase]) -> int:
        with self._s._lock:
            return sum(self._append(e) for e in events)

    def list(
        self,
        run_id: str,
        *,
        since_seq: int = 0,
        limit: int | None = None,
        actor: str | None = None,
        type_prefix: str | None = None,
    ) -> builtins.list[RunEvent]:
        with self._s._lock:
            rows = [
                e
                for s, e in sorted(self._s._events.get(run_id, {}).items())
                if s > since_seq
                and (actor is None or e.actor == actor)
                and (not type_prefix or e.type.startswith(type_prefix))
            ]
        return [e.model_copy(deep=True) for e in rows[:limit]]

    def _newest(
        self,
        *,
        run_id: str | None,
        actor: str | None,
        type: str | None,
        type_prefix: str | None,
        since: float | None,
        limit: int | None,
    ) -> builtins.list[RunEvent]:
        with self._s._lock:
            runs = [run_id] if run_id is not None else list(self._s._events)
            rows = [
                e
                for r in runs
                for e in self._s._events.get(r, {}).values()
                if (actor is None or e.actor == actor)
                and (type is None or e.type == type)
                and (not type_prefix or e.type.startswith(type_prefix))
                and (since is None or e.ts >= since)
            ]
        rows.sort(key=lambda e: (e.ts, e.run_id, e.seq), reverse=True)
        return [e.model_copy(deep=True) for e in rows[:limit]]

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]:
        return self._newest(
            run_id=run_id, actor=actor, type=type, type_prefix=None, since=None, limit=limit
        )

    def list_by_actor(
        self,
        actor: str,
        *,
        since: float | None = None,
        type_prefix: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[RunEvent]:
        return self._newest(
            run_id=None, actor=actor, type=None, type_prefix=type_prefix, since=since, limit=limit
        )

    def last_seq(self, run_id: str) -> int:
        with self._s._lock:
            seqs = self._s._events.get(run_id)
            return max(seqs) if seqs else 0


def check_close_status(status: str, allowed: tuple[str, ...]) -> None:
    """닫을 때 쓸 수 있는 상태인지 검사한다(두 구현이 같은 규칙을 쓴다)."""
    if status not in allowed:
        raise ValueError(f"status must be one of {allowed}, got {status!r}")


def closed_copy(
    current: Interaction,
    *,
    status: InteractionStatus,
    closed_at: float,
    response: dict[str, Any] | None,
    answered_by: str | None,
    close_reason: str | None,
) -> Interaction:
    """pending 상호작용에 닫힘 정보를 채운 사본."""
    return current.model_copy(
        update={
            "status": status,
            "closed_at": closed_at,
            "response": copy.deepcopy(response) if response is not None else current.response,
            "answered_by": answered_by,
            "close_reason": close_reason,
        },
        deep=True,
    )


def status_set(
    status: InteractionStatus | Iterable[InteractionStatus] | None,
) -> list[str] | None:
    """`status` 필터 인자를 목록으로(문자열 하나도 받는다)."""
    if status is None:
        return None
    return [status] if isinstance(status, str) else list(status)


class InMemoryInteractionRepository:
    def __init__(self, state: InMemoryStorage) -> None:
        self._s = state

    def save(self, interaction: Interaction) -> bool:
        with self._s._lock:
            existing = self._s._interactions.get(interaction.id)
            if existing is not None and existing.status != "pending":
                return False
            self._s._interactions[interaction.id] = interaction.model_copy(deep=True)
            return True

    def get(self, interaction_id: str) -> Interaction | None:
        with self._s._lock:
            row = self._s._interactions.get(interaction_id)
            return None if row is None else row.model_copy(deep=True)

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: InteractionStatus | Iterable[InteractionStatus] | None = None,
        root_run_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Interaction]:
        statuses = status_set(status)
        with self._s._lock:
            rows = [
                i
                for i in self._s._interactions.values()
                if (run_id is None or i.run_id == run_id)
                and (root_run_id is None or root_run_id in (i.run_id, i.root_run_id))
                and (conversation_id is None or i.conversation_id == conversation_id)
                and (statuses is None or i.status in statuses)
            ]
        rows.sort(key=lambda i: (i.created_at, i.id))
        return [i.model_copy(deep=True) for i in rows[:limit]]

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
        with self._s._lock:
            current = self._s._interactions.get(interaction_id)
            if current is None:
                raise NotFound(f"interaction/{interaction_id}")
            if current.status != "pending":
                raise InteractionClosed(current.model_copy(deep=True))
            closed = closed_copy(
                current,
                status=status,
                closed_at=closed_at,
                response=response,
                answered_by=answered_by,
                close_reason=close_reason,
            )
            self._s._interactions[interaction_id] = closed
            return closed.model_copy(deep=True)

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
        result: list[Interaction] = []
        with self._s._lock:
            for key, current in sorted(
                self._s._interactions.items(), key=lambda kv: (kv[1].created_at, kv[0])
            ):
                if current.status != "pending" or (run_id is not None and current.run_id != run_id):
                    continue
                closed = closed_copy(
                    current,
                    status=status,
                    closed_at=closed_at,
                    response=None,
                    answered_by=answered_by,
                    close_reason=close_reason,
                )
                self._s._interactions[key] = closed
                result.append(closed.model_copy(deep=True))
        return result

    def pending_counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, int]:
        wanted = None if conversation_ids is None else set(conversation_ids)
        counts: dict[str, int] = {}
        with self._s._lock:
            for i in self._s._interactions.values():
                cid = i.conversation_id
                if i.status == "pending" and cid is not None and (wanted is None or cid in wanted):
                    counts[cid] = counts.get(cid, 0) + 1
        return counts
