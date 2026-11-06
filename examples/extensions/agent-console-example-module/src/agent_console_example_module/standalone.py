"""단독 실행 진입점(``python -m agent_console_example_module``가 부른다, 테스트도 직접 부른다).

통합 서버 없이 이 모듈 하나를 같은 호스트 코드(토큰·Host 검사·``/health``)로 띄운다.

- ``--with``를 주지 않으면 ``local_settings_module``(워크스페이스 ``settings.yaml``을
  ``workspace.settings``로 주는 작은 모듈)을 함께 붙인다. 사용자 설정 섹션은 그 파일에 적는다.
- 앱 노트는 상태 폴더의 SQLite 파일(``<state>/example-notes.sqlite3``, 이름은 패키지 데이터)에
  둔다.
- 정의 기능·프로젝트 기록 연동이 없으므로 노트 틀·프로젝트 노트는 409 ``feature_unavailable``이다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.standalone import run
from agent_console_modkit.testing import fake_module
from agent_console_store import SETTINGS_KIND, FileDefinitionStore, NotFound, SqliteDatabase

from .module import module
from .ports import WORKSPACE_SETTINGS
from .settings import package_defaults

LOCAL_SETTINGS_ID = "example-notes-local-settings"
"""단독 실행에서 함께 붙이는 설정 제공 모듈 id."""


def _read(store: FileDefinitionStore) -> WorkspaceSettings:
    try:
        stored = store.get(SETTINGS_KIND.name, SETTINGS_KIND.name)
    except NotFound:
        return WorkspaceSettings()
    return stored.model(WorkspaceSettings)


def local_settings_module(*, workspace: Path | None = None) -> Module:
    """``workspace.settings`` 제공 모듈(``<workspace>/settings.yaml``, 없으면 기본값).

    Args:
        workspace: 설정 폴더. None이면 호스트 경로의 워크스페이스.
    """

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else Path.cwd())
        store = FileDefinitionStore(root, (SETTINGS_KIND,))
        ctx.provide(WORKSPACE_SETTINGS, lambda: _read(store))
        return ModuleParts()

    return fake_module(
        LOCAL_SETTINGS_ID, kind="testing", provides=[WORKSPACE_SETTINGS], on_build=build
    )


def main(argv: Sequence[str] | None = None, **overrides: Any) -> int:
    """모듈을 단독으로 띄운다.

    Args:
        argv: 명령행 인자(``--with``·``--config``·``--host``·``--port``·``--check``).
        overrides: ``agent_console_modkit.standalone.run``에 넘길 인자(테스트 주입).

    Returns:
        종료 코드(0 정상, 1 모듈 꺼짐·확인 실패, 2 인자·설정 오류).
    """
    database_file = str(package_defaults()["database_file"])
    options: dict[str, Any] = {
        "default_with": [local_settings_module()],
        "error_status": HTTP_STATUS_BY_ERROR_CODE,
        "prog": "python -m agent_console_example_module",
        "database": lambda paths: SqliteDatabase.open(paths.state / database_file),
    }
    options.update(overrides)
    return run(module, argv=argv, **options)


__all__ = ["LOCAL_SETTINGS_ID", "local_settings_module", "main"]
