"""연동 모듈 ``link-example-notes-runs``(entry point ``agent_console.server_modules``).

노트 모듈(``example_notes.reader``)과 실행 모듈(``runs.reader``)이 **둘 다** 있을 때만
켜진다. 하나라도 없으면 이 연동만 ``unsatisfied``이고 서버와 나머지 모듈은 그대로 시작한다.
그때 노트 리소스를 붙인 에이전트는 "적용하지 못한 칸" 경고를 받고 실행은 정상으로 끝난다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Final

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .ports import NOTES_READER, RUN_SCOPES, RUNS_READER
from .resource_type import load_resource_type, notes_slot
from .scope import NotesRunScope
from .settings import NotesRunsSettings

__all__ = ["MODULE_ID", "NotesRunsLink", "module"]

MODULE_ID: Final = "link-example-notes-runs"


def _version() -> str:
    try:
        return version("agent-console-example-link")
    except PackageNotFoundError:  # 설치 없이 소스로 실행
        return "0.0.0"


class NotesRunsLink:
    """노트 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="노트·실행 연동(예제)",
        description="노트 리소스를 붙인 에이전트가 실행 중에 노트를 읽게 한다",
        provides=(RUN_SCOPES,),
        requires=(NOTES_READER, RUNS_READER),
        settings_schema=NotesRunsSettings,
        contracts={"runs": CONTRACT_VERSIONS["runs"]},
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings if isinstance(ctx.settings, NotesRunsSettings) else NotesRunsSettings()
        ctx.provide(
            RUN_SCOPES,
            NotesRunScope(
                lambda: ctx.port(NOTES_READER),
                slot=notes_slot(load_resource_type()),
                text=cfg.text(),
                provider_id=MODULE_ID,
                max_notes=cfg.max_notes_per_call,
            ),
        )
        return ModuleParts()


module = NotesRunsLink()
"""entry point가 가리키는 모듈 인스턴스."""
