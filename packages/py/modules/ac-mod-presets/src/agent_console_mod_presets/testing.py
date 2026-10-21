"""단독 실행·테스트용 모듈(공개). 다른 패키지의 테스트도 이것을 쓴다.

``local_definitions_module``: ``definitions.store``를 워크스페이스 폴더의 파일 저장소
(``FileDefinitionStore``, 버전 기록은 메모리)로 주는 작은 모듈. 단독 실행
``python -m agent_console_mod_presets``가 ``--with`` 없이 실행되면 이것을 붙인다
(design modularity §3.9.4 — 같은 패키지 ``testing``의 구현).
통합 서버에서는 정의 모듈(``definitions.store`` 제공자)이 대신한다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

from .ports import DEFINITIONS_STORE

LOCAL_DEFINITIONS_ID = "local-definitions"
DEFAULT_WORKSPACE = Path(".agent-console")


def local_definitions_module(
    module_id: str = LOCAL_DEFINITIONS_ID, *, workspace: Path | None = None
) -> Module:
    """``definitions.store`` 제공 모듈(워크스페이스 = ``workspace`` 또는 호스트 경로)."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)
        ctx.provide(DEFINITIONS_STORE, FileDefinitionStore(root, DEFAULT_KINDS))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[DEFINITIONS_STORE], on_build=build)


__all__ = ["LOCAL_DEFINITIONS_ID", "local_definitions_module"]
