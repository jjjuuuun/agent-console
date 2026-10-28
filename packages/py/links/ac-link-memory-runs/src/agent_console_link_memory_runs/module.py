"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-memory-runs``).

공유 메모리(``mod-memory``)와 실행(``mod-runs``)을 잇는다(design §5.7R.2).

- 필수: ``memory.service``. 없으면(``mod-memory`` 꺼짐) 이 연동도 꺼진다. 그래도 실행은 정상이고,
  메모리 리소스를 붙인 에이전트에게는 칸이 적용되지 않았다는 경고(R13.5)가 한 번 난다.
- 제공: ``runs.scopes``(Run마다 노드 서비스 ``TOOL_PROVIDERS``에 메모리 도구 공급자),
  ``definitions.checks``(메모리 리소스의 모르는 범위 종류 경고).
- 리소스 종류 ``memory``는 이 패키지의 entry point ``agent_console.resource_types``(패키지 데이터)로
  따로 등록된다. 이 연동 모듈을 끄더라도 리소스는 만들 수 있다(칸을 받을 공급자만 없다).
- 웹 역할 ``memory:runs``(실행 상세의 메모리 쓰기·읽기 칩).
- 설정 ``modules.options.link-memory-runs``: ``max_writes_per_run``(기본 200, 비우면 한도 없음).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .checks import MemoryResourceCheck
from .ports import DEFINITION_CHECKS, MEMORY_SERVICE, RUN_SCOPES
from .resource_type import load_memory_resource_type, memory_slot
from .scope import MemoryRunScope
from .settings import MemoryRunsSettings

MODULE_ID = "link-memory-runs"
WEB_ROLES: tuple[str, ...] = ("memory:runs",)
"""웹 연동 부분 역할(실행 상세의 메모리 칩)."""


def _version() -> str:
    try:
        return version("agent-console-link-memory-runs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class MemoryRunsLink:
    """메모리 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="메모리·실행 연동",
        description="에이전트에게 메모리 도구를 주고 호출마다 memory.* 실행 이벤트를 남긴다",
        provides=(RUN_SCOPES, DEFINITION_CHECKS),
        requires=(MEMORY_SERVICE,),
        settings_schema=MemoryRunsSettings,
        contracts={"memory": CONTRACT_VERSIONS["memory"], "runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, MemoryRunsSettings):
            cfg = MemoryRunsSettings()
        rtype = load_memory_resource_type()
        ctx.provide(
            RUN_SCOPES,
            MemoryRunScope(
                lambda: ctx.port(MEMORY_SERVICE),
                slot=memory_slot(rtype),
                max_writes_per_run=cfg.max_writes_per_run,
                provider_id=MODULE_ID,
            ),
        )
        ctx.provide(
            DEFINITION_CHECKS,
            MemoryResourceCheck(lambda: ctx.port(MEMORY_SERVICE), resource_type=rtype.id),
        )
        return ModuleParts()


module = MemoryRunsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "MemoryRunsLink", "module"]
