"""agent-console-link-memory-runs: 메모리·실행 연동 모듈(design §5.7R.2·§5.7R.3).

에이전트에게 공유 메모리 도구를 준다. 실행 모듈(``mod-runs``)과 메모리 모듈(``mod-memory``)은 서로를
모르고, 이 연동이 실행 범위(X26)로 Run마다 X30 도구 공급자를 넣어 둘을 잇는다. 리소스 종류
``memory``(패키지 데이터)를 붙인 에이전트만 도구를 받는다(opt-in). 도구 호출마다 RunEvent
``memory.<op>``(본문·검색어 원문 없음)를 남긴다.

공개 API:
    - ``module``(``MemoryRunsLink``): entry point ``agent_console.server_modules``의
      ``link-memory-runs``. 설정 ``MemoryRunsSettings``(``max_writes_per_run``).
    - 리소스 종류: ``MemoryResourceType``(entry point ``agent_console.resource_types``의
      ``memory``), ``load_memory_resource_type``, ``memory_slot``, ``access_item``.
    - 도구 공급자(X30): ``MemoryToolProvider``, ``merge_access``(층 합치기), ``access_context``,
      ``as_host_tool``, ``event_payload``, 경고 코드 ``MemoryRunsCodes``.
    - 실행 범위(X26): ``MemoryRunScope``·``RunScopeResult``.
    - 저장 전 검사: ``MemoryResourceCheck``(모르는 범위 종류 경고).
    - 포트(``ports``): 받음 ``MEMORY_SERVICE``(필수), 제공 ``RUN_SCOPES``·``DEFINITION_CHECKS``.
    - ``testing``: ``StaticMemoryService``·``memory_service_module``(단독 실행·테스트).
"""

from __future__ import annotations

from .checks import MemoryResourceCheck
from .module import MODULE_ID, WEB_ROLES, MemoryRunsLink, module
from .ports import DEFINITION_CHECKS, MEMORY_SERVICE, RUN_SCOPES, MemoryServiceLike
from .provider import (
    DEFAULT_PROVIDER_ID,
    MemoryRunsCodes,
    MemoryToolProvider,
    access_context,
    as_host_tool,
    event_payload,
    merge_access,
)
from .resource_type import (
    MEMORY_RESOURCE_TYPE_RESOURCE,
    MemoryResourceType,
    access_item,
    load_memory_resource_type,
    memory_slot,
)
from .scope import MemoryRunScope, RunScopeResult
from .settings import DEFAULT_MAX_WRITES_PER_RUN, MemoryRunsSettings

__all__ = [
    "DEFAULT_MAX_WRITES_PER_RUN",
    "DEFAULT_PROVIDER_ID",
    "DEFINITION_CHECKS",
    "MEMORY_RESOURCE_TYPE_RESOURCE",
    "MEMORY_SERVICE",
    "MODULE_ID",
    "RUN_SCOPES",
    "WEB_ROLES",
    "MemoryResourceCheck",
    "MemoryResourceType",
    "MemoryRunScope",
    "MemoryRunsCodes",
    "MemoryRunsLink",
    "MemoryRunsSettings",
    "MemoryServiceLike",
    "MemoryToolProvider",
    "RunScopeResult",
    "access_context",
    "access_item",
    "as_host_tool",
    "event_payload",
    "load_memory_resource_type",
    "memory_slot",
    "merge_access",
    "module",
]
