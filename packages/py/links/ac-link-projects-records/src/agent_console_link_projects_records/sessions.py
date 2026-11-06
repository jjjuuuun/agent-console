"""대화 세션 기록 보관·이어 가기 상태(design §PI.4.6.4, K33-29, X38).

대화를 이어 가려면 백엔드 세션 원본이 이 앱 자격 폴더에 있어야 한다. 이 모듈은 프로젝트 폴더
``<구성 폴더>/<dir>/<backend>/<session>/``에 원본 사본을 두고(보관), 다른 앱·경로를 다시 지정한 뒤
보내기 직전에 그 사본(또는 이 앱 안 옛 위치)에서 복원한다. 무엇이 원본인지·어디로 복원하는지는
백엔드의 ``SessionArchive``(``runs.session_archive`` 포트)가 정한다 — 이 모듈은 파일 이름을 모른다.

- ``ProjectSessionArchive``: ``records.sessions`` 포트(``agent_console_chat.SessionContinuity``
  모양 ``state``·``prepare`` + ``archive``). 상태 = ``available``·``relocatable``·``archived``·
  ``missing``·``not_applicable``(계약 ``KnownSessionStates``).
- ``SessionArchiver``: ``runs.event`` 구독. 노드가 끝날 때(또는 Run이 끝날 때) 그 노드 세션을
  보관한다. 실패는 실행을 막지 않고 기록·정보 이슈로만 남긴다.
- 보관을 꺼도(``session_archive.enabled = false``) 이미 있는 사본은 지우지 않고 복원에는 쓴다.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    AgentSessionStartedPayload,
    Issue,
    KnownIssueCodes,
    KnownSessionStates,
    RunEvent,
    x_ui,
)
from agent_console_runtime import (
    ArchiveFile,
    SessionArchive,
    SessionKey,
    copy_files,
    safe_name,
)

from .ports import ProjectSpaces

_log = logging.getLogger("agent_console_link_projects_records")

SESSION_STARTED_EVENT = "agent.session_started"
NODE_END_EVENTS: frozenset[str] = frozenset({"node.completed", "node.failed", "node.cancelled"})
"""노드가 끝난 이벤트(그 노드 세션을 보관한다)."""
RUN_END_EVENTS: frozenset[str] = frozenset(
    {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}
)
"""Run이 끝난 이벤트(남은 세션을 보관하고 정리한다)."""
ARCHIVE_FAILED_CODE: str = KnownIssueCodes.RECORDS_SESSION_ARCHIVE_FAILED
"""보관 실패 정보 이슈 코드(``server.warnings``, 계약 문서 상수
``records.session_archive_failed``)."""
NEWER_TOLERANCE_S = 0.001
"""보관 사본이 이 앱 원본보다 "새것"으로 볼 수정 시각 차이(초)."""


class SessionArchiveSettings(BaseModel):
    """대화 원본 보관(다른 앱에서 대화를 이어 가기 위한 세션 기록 사본)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        title="대화 원본 보관",
        description=(
            "대화 원본(도구 출력 포함)을 프로젝트 폴더에 복사해 다른 앱에서도 이어 갑니다. 로그인 "
            "자격은 넣지 않습니다. 폴더를 공유하면 대화 원본도 함께 공유됩니다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    dir: str = Field(
        default="sessions",
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        title="보관 폴더 이름",
        description=(
            "프로젝트 구성 폴더(.agent-console) 안 보관 폴더 이름. 기본 sessions는 구성 폴더의 "
            ".gitignore가 제외한다. 바꾸면 git 제외 줄도 직접 더한다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )


class BackendArchives(Protocol):
    """``runs.session_archive`` 모양(``agent_console_runtime.BackendSessionArchives``)."""

    def get(self, backend_id: str) -> SessionArchive | None: ...


class RunLookup(Protocol):
    """``runs.reader``에서 쓰는 부분(Run의 ``project_id``)."""

    def get(self, run_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class _Place:
    cwd: Path
    root: Path


class ProjectSessionArchive:
    """프로젝트 폴더의 세션 기록 보관 사본과 이어 가기 상태(``records.sessions`` 포트).

    Args:
        spaces: ``projects.spaces``(등록 id → 공간 — ``folder``·``records_db_path``).
        archives: ``runs.session_archive``(없으면 모든 상태가 ``not_applicable``).
        settings: 보관 켜기·폴더 이름.
    """

    def __init__(
        self,
        spaces: Callable[[], ProjectSpaces | None],
        archives: Callable[[], BackendArchives | None],
        *,
        settings: SessionArchiveSettings | None = None,
    ) -> None:
        self._spaces = spaces
        self._archives = archives
        self.settings = settings or SessionArchiveSettings()
        self._lock = threading.Lock()
        self.failures: list[dict[str, str]] = []
        """최근 보관 실패(정보 이슈용, 최대 20개, 비밀·내용 없음)."""

    # ------------------------------------------------------------ 위치

    def _place(self, project_id: str | None) -> _Place | None:
        if not project_id:
            return None
        spaces = self._spaces()
        if spaces is None:
            return None
        try:
            space = spaces.open(project_id)
        except Exception:
            return None
        return _Place(
            cwd=Path(space.folder), root=Path(space.records_db_path).parent / self.settings.dir
        )

    def _backend(self, session: SessionKey) -> SessionArchive | None:
        archives = self._archives()
        if archives is None:
            return None
        try:
            return archives.get(session.backend)
        except Exception:
            return None

    def archive_dir(self, project_id: str | None, session: SessionKey) -> Path | None:
        """그 세션의 보관 폴더(``<구성 폴더>/<dir>/<backend>/<session>``, 없어도 경로만)."""
        place = self._place(project_id)
        if place is None or not (safe_name(session.backend) and safe_name(session.session_id)):
            return None
        return place.root / session.backend / session.session_id

    # ------------------------------------------------------------ 상태·복원

    def state(self, project_id: str | None, session: SessionKey) -> str:
        """이어 가기 상태(파일을 쓰지 않는다)."""
        backend = self._backend(session)
        place = self._place(project_id)
        if backend is None or place is None:
            return KnownSessionStates.NOT_APPLICABLE
        current = backend.status(session, cwd=place.cwd)
        if current in (KnownSessionStates.AVAILABLE, KnownSessionStates.RELOCATABLE):
            return current
        folder = self.archive_dir(project_id, session)
        if folder is not None and _has_files(folder):
            return KnownSessionStates.ARCHIVED
        return KnownSessionStates.MISSING

    def prepare(self, project_id: str | None, session: SessionKey) -> str:
        """보내기 직전에 이어 갈 수 있게 놓는다(보관 사본이 이 앱 원본보다 새것이면 그것으로).

        Returns:
            ``archived``(보관 사본에서 복원)·``relocatable``(이 앱 옛 위치에서 옮김)·``available``
            (그대로)·``missing``(놓지 못함)·``not_applicable``.
        """
        backend = self._backend(session)
        place = self._place(project_id)
        if backend is None or place is None:
            return KnownSessionStates.NOT_APPLICABLE
        current = backend.status(session, cwd=place.cwd)
        folder = self.archive_dir(project_id, session)
        archived = folder is not None and _has_files(folder)
        if archived and folder is not None:
            local = (
                backend.files(session, cwd=place.cwd)
                if current != KnownSessionStates.MISSING
                else None
            )
            if _newer(folder, local) and backend.restore(folder, session, cwd=place.cwd):
                return KnownSessionStates.ARCHIVED
        if current == KnownSessionStates.AVAILABLE:
            return current
        if current == KnownSessionStates.RELOCATABLE and backend.restore(
            None, session, cwd=place.cwd
        ):
            return current
        if archived and folder is not None and backend.restore(folder, session, cwd=place.cwd):
            return KnownSessionStates.ARCHIVED
        return KnownSessionStates.MISSING

    # ------------------------------------------------------------ 보관

    def archive(self, project_id: str | None, session: SessionKey) -> int | None:
        """세션 원본을 보관 폴더로 복사한다(덮어씀). 보관을 껐거나 할 수 없으면 None.

        Returns:
            복사한 파일 수.

        Raises:
            OSError: 쓰기 실패(호출자가 기록한다).
        """
        if not self.settings.enabled:
            return None
        backend = self._backend(session)
        place = self._place(project_id)
        folder = self.archive_dir(project_id, session)
        if backend is None or place is None or folder is None:
            return None
        files = backend.files(session, cwd=place.cwd)
        if not files:
            return None
        return copy_files(files, folder)

    def note_failure(self, project_id: str, session: SessionKey, error: BaseException) -> None:
        """보관 실패를 남긴다(실행은 막지 않는다)."""
        _log.warning(
            "세션 기록 보관 실패(프로젝트 %s, 백엔드 %s): %s",
            project_id,
            session.backend,
            type(error).__name__,
        )
        with self._lock:
            self.failures.append(
                {
                    "project_id": project_id,
                    "backend": session.backend,
                    "error": type(error).__name__,
                }
            )
            del self.failures[:-20]

    def warnings(self) -> list[Issue]:
        """``server.warnings``: 최근 보관 실패가 있으면 정보 이슈 하나."""
        with self._lock:
            if not self.failures:
                return []
            last = dict(self.failures[-1])
            count = len(self.failures)
        return [
            Issue(
                severity="info",
                code=ARCHIVE_FAILED_CODE,
                message="대화 원본을 프로젝트 폴더에 보관하지 못했습니다(실행에는 영향 없음)",
                details={"count": count, **last},
            )
        ]


def _has_files(folder: Path) -> bool:
    try:
        return folder.is_dir() and any(p.is_file() for p in folder.rglob("*"))
    except OSError:
        return False


def _mtime(paths: Iterable[Path]) -> float:
    best = 0.0
    for path in paths:
        try:
            best = max(best, path.stat().st_mtime)
        except OSError:
            continue
    return best


def _newer(folder: Path, local: list[ArchiveFile] | None) -> bool:
    """보관 사본이 이 앱 원본보다 새것인가(원본이 없으면 참)."""
    if not local:
        return True
    try:
        archived = [p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()]
    except OSError:
        return False
    return _mtime(archived) > _mtime(f.source for f in local) + NEWER_TOLERANCE_S


@dataclass
class _Pending:
    sessions: dict[str, SessionKey] = field(default_factory=dict)


class SessionArchiver:
    """``runs.event`` 처리기: 노드 세션을 노드가 끝날 때 보관한다.

    Args:
        archive: 보관 사본 관리.
        runs: Run 조회(``project_id``를 읽는다). 없으면 보관하지 않는다.
        submit: 보관 작업 실행기(기본: 실행 중 이벤트 루프의 스레드 풀, 루프가 없으면 바로).
    """

    def __init__(
        self,
        archive: ProjectSessionArchive,
        runs: Callable[[], RunLookup | None],
        *,
        submit: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._archive = archive
        self._runs = runs
        self._submit = submit or _default_submit
        self._pending: dict[str, _Pending] = {}

    def __call__(self, event: RunEvent) -> None:
        if not self._archive.settings.enabled:
            return
        top = len(event.node_path) == 1
        if event.type == SESSION_STARTED_EVENT and top:
            ref = _session_of(event.payload)
            if ref is not None:
                self._pending.setdefault(event.run_id, _Pending()).sessions[event.node_path[0]] = (
                    ref
                )
        elif event.type in NODE_END_EVENTS and top:
            pending = self._pending.get(event.run_id)
            ref = pending.sessions.pop(event.node_path[0], None) if pending is not None else None
            if ref is not None:
                self._schedule(event.run_id, [ref])
        elif event.type in RUN_END_EVENTS and not event.node_path:
            pending = self._pending.pop(event.run_id, None)
            if pending is not None and pending.sessions:
                self._schedule(event.run_id, list(pending.sessions.values()))

    def _schedule(self, run_id: str, sessions: list[SessionKey]) -> None:
        self._submit(lambda: self._run(run_id, sessions))

    def _run(self, run_id: str, sessions: list[SessionKey]) -> None:
        runs = self._runs()
        if runs is None:
            return
        try:
            run = runs.get(run_id)
        except Exception:
            return
        project_id = getattr(run, "project_id", None)
        if not project_id:
            return
        for ref in sessions:
            try:
                self._archive.archive(project_id, ref)
            except Exception as exc:
                self._archive.note_failure(project_id, ref, exc)


class _Ref:
    __slots__ = ("backend", "session_id")

    def __init__(self, backend: str, session_id: str) -> None:
        self.backend = backend
        self.session_id = session_id


def _session_of(payload: Mapping[str, Any]) -> SessionKey | None:
    try:
        parsed = AgentSessionStartedPayload.model_validate(payload)
    except ValidationError:
        return None
    return _Ref(parsed.backend, parsed.session_id)


def _default_submit(job: Callable[[], None]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        job()
        return
    future = loop.run_in_executor(None, job)
    future.add_done_callback(_log_failure)


def _log_failure(future: asyncio.Future[None]) -> None:
    if not future.cancelled() and future.exception() is not None:
        _log.warning("세션 기록 보관 작업 실패: %s", type(future.exception()).__name__)


__all__ = [
    "ARCHIVE_FAILED_CODE",
    "NODE_END_EVENTS",
    "RUN_END_EVENTS",
    "BackendArchives",
    "ProjectSessionArchive",
    "RunLookup",
    "SessionArchiveSettings",
    "SessionArchiver",
]
