"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-projects-records``).

프로젝트 공간(``mod-projects``)의 폴더에 기록 DB를 열어 실행·대화·사본 버전 모듈에 준다
(design §PI.4.6.2·.3·.5·.6, K33-27~K33-32).

- 필수: ``projects.spaces``. 없으면(``mod-projects`` 꺼짐) 이 연동도 꺼진다.
- 제공: ``records.spaces`` - 공간 이름(``project:<등록 id>``) → 기록 DB 핸들. 처음 쓸 때 열고,
  앱 DB와 같은 계보 사슬(legacy + 켜진 모듈 중 ``project`` 범위 계보)을 맞춘다.
- 앱 id ``host_id``(``<상태 폴더>/host_id``)와 쓰기 실패 대기 파일
  (``<상태 폴더>/records-spool/``)을 둔다.
- 세션 기록 보관(5.7R.33y3, design §PI.4.6.4): ``records.sessions``(대화 이어 가기 상태·복원) 제공,
  ``runs.event`` 구독으로 노드가 끝나면 세션 원본을 ``<구성 폴더>/sessions/<backend>/<session>/``에
  복사(설정 ``session_archive``, 기본 켬). 백엔드 보관 기능은 선택 포트 ``runs.session_archive``.
- 이 연동이 꺼지면: 프로젝트 기록 DB가 없다. 소비 모듈은 ``records.spaces``가 없는 것으로 보고
  앱 조립은 기록을 막는다(앱 DB에 조용히 쓰지 않는다).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .host_id import HOST_ID_FILE, load_host_id
from .pool import PoolOptions, RecordsSpacePool
from .ports import (
    PROJECTS_SPACES,
    RECORDS_SESSIONS,
    RECORDS_SPACES,
    RUNS_EVENT,
    RUNS_READER,
    RUNS_SESSION_ARCHIVE,
    SERVER_WARNINGS,
)
from .sessions import ProjectSessionArchive, SessionArchiver
from .settings import ProjectsRecordsSettings
from .spool import RecordsSpool

MODULE_ID = "link-projects-records"


def _version() -> str:
    try:
        return version("agent-console-link-projects-records")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ProjectsRecordsLink:
    """프로젝트 ↔ 기록 DB 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="프로젝트 기록 연동",
        description="실행·대화 기록을 프로젝트 폴더 안에 둔다",
        provides=(RECORDS_SPACES, RECORDS_SESSIONS, SERVER_WARNINGS),
        requires=(PROJECTS_SPACES,),
        optional=(RUNS_SESSION_ARCHIVE, RUNS_READER),
        settings_schema=ProjectsRecordsSettings,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, ProjectsRecordsSettings):
            cfg = ProjectsRecordsSettings()
        paths = ctx.paths
        if paths is None:
            raise RuntimeError("link-projects-records는 호스트 경로(상태 폴더)가 필요합니다")
        host = load_host_id(paths.state / HOST_ID_FILE)
        spool_root = paths.state / cfg.spool_dir
        pool = RecordsSpacePool(
            lambda: ctx.port(PROJECTS_SPACES),
            lambda: ctx.active_migrations("project"),
            host_id=host,
            spool=RecordsSpool(spool_root),
            options=PoolOptions(
                prefix=cfg.space_prefix,
                max_open=cfg.max_open_spaces,
                idle_close_seconds=cfg.idle_close_seconds,
                busy_timeout=cfg.busy_timeout_ms / 1000,
                keep_backups=cfg.backups_keep,
                journal=cfg.journal,
            ),
        )
        ctx.provide(RECORDS_SPACES, pool)
        sessions = ProjectSessionArchive(
            lambda: ctx.port(PROJECTS_SPACES),
            lambda: ctx.port(RUNS_SESSION_ARCHIVE),
            settings=cfg.session_archive,
        )
        ctx.provide(RECORDS_SESSIONS, sessions)
        ctx.provide(SERVER_WARNINGS, sessions.warnings)
        ctx.subscribe(RUNS_EVENT, SessionArchiver(sessions, lambda: ctx.port(RUNS_READER)))

        async def stop() -> None:
            pool.close_all()

        return ModuleParts(shutdown=[stop])


module = ProjectsRecordsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "ProjectsRecordsLink", "module"]
