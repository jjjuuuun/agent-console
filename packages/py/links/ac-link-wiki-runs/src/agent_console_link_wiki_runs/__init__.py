"""agent-console-link-wiki-runs: 위키·실행 연동 모듈(design §7R.3·§7R.4).

에이전트에게 위키 도구와 위키 규칙 지침을 준다. 실행 모듈(``mod-runs``)과 위키 모듈(``mod-wiki``)은
서로를 모르고, 이 연동이 실행 범위(X26)로 Run마다 X30 도구 공급자를 넣어 둘을 잇는다. 리소스 종류
``wiki``(패키지 데이터)를 붙인 에이전트만 도구·지침을 받는다(opt-in). 도구 호출마다 RunEvent
``wiki.<op>``(본문·검색어 원문 없음)를 남긴다.

공개 API:
    - ``module``(``WikiRunsLink``): entry point ``agent_console.server_modules``의
      ``link-wiki-runs``. 설정 ``WikiRunsSettings``(``max_writes_per_run``).
    - 리소스 종류: ``WikiResourceType``(entry point ``agent_console.resource_types``의 ``wiki``),
      ``load_wiki_resource_type``, ``wiki_slot``, ``access_item``.
    - 도구 공급자(X30): ``WikiToolProvider``, ``merge_access``(층 합치기), ``author_for``,
      ``agent_label``, ``open_targets``, ``as_host_tool``, ``event_payload``, ``unavailable_issue``,
      경고 코드 ``WikiRunsCodes``.
    - 실행 범위(X26): ``WikiRunScope``·``RunScopeResult``.
    - 노드 종류 ``wiki-update``(X2, entry point ``agent_console.node_types``): ``WikiUpdateNode``·
      ``WikiUpdateConfig``·``WikiNodeServices``(``runs.services``)·``WIKI_UPDATE_SERVICE``·
      ``WIKI_UPDATE_VARIABLES``·``render_values``·``system_author``·``WikiUpdateCodes``.
    - 저장 전 검사: ``WikiResourceCheck``·``known_wiki_ids``(모르는 위키 id 경고).
    - 포트(``ports``): 받음 ``WIKI_SERVICE``(필수)·``PROJECTS_LOOKUP``(선택), 제공
      ``RUN_SCOPES``·``RUN_SERVICES``·``DEFINITION_CHECKS``·``WIKI_INTEGRATIONS``(``WikiRunsIntegration``).
    - ``testing``: ``StaticWikiService``·``memory_repository``·``wiki_service_module``.
"""

from __future__ import annotations

from .checks import WikiResourceCheck, known_wiki_ids
from .module import MODULE_ID, WEB_ROLES, WikiRunsLink, module
from .ports import (
    DEFINITION_CHECKS,
    INTEGRATION_RUNS,
    PROJECTS_LOOKUP,
    RUN_SCOPES,
    RUN_SERVICES,
    WIKI_INTEGRATIONS,
    WIKI_SERVICE,
    ProjectLookupLike,
    WikiRunsIntegration,
    WikiServiceLike,
)
from .provider import (
    DEFAULT_PROVIDER_ID,
    AgentLookup,
    WikiRunsCodes,
    WikiToolProvider,
    agent_label,
    as_host_tool,
    author_for,
    event_payload,
    merge_access,
    open_targets,
    unavailable_issue,
)
from .resource_type import (
    WIKI_RESOURCE_TYPE_RESOURCE,
    WikiResourceType,
    access_item,
    load_wiki_resource_type,
    wiki_slot,
)
from .scope import RunScopeResult, WikiRunScope
from .settings import DEFAULT_MAX_WRITES_PER_RUN, WikiRunsSettings
from .update_node import (
    NODE_TYPE_ID,
    WIKI_UPDATE_SERVICE,
    WIKI_UPDATE_VARIABLES,
    WikiNodeServices,
    WikiUpdateCodes,
    WikiUpdateConfig,
    WikiUpdateNode,
    render_values,
    system_author,
)

__all__ = [
    "DEFAULT_MAX_WRITES_PER_RUN",
    "DEFAULT_PROVIDER_ID",
    "DEFINITION_CHECKS",
    "INTEGRATION_RUNS",
    "MODULE_ID",
    "NODE_TYPE_ID",
    "PROJECTS_LOOKUP",
    "RUN_SCOPES",
    "RUN_SERVICES",
    "WEB_ROLES",
    "WIKI_INTEGRATIONS",
    "WIKI_RESOURCE_TYPE_RESOURCE",
    "WIKI_SERVICE",
    "WIKI_UPDATE_SERVICE",
    "WIKI_UPDATE_VARIABLES",
    "AgentLookup",
    "ProjectLookupLike",
    "RunScopeResult",
    "WikiNodeServices",
    "WikiResourceCheck",
    "WikiResourceType",
    "WikiRunScope",
    "WikiRunsCodes",
    "WikiRunsIntegration",
    "WikiRunsLink",
    "WikiRunsSettings",
    "WikiServiceLike",
    "WikiToolProvider",
    "WikiUpdateCodes",
    "WikiUpdateConfig",
    "WikiUpdateNode",
    "access_item",
    "agent_label",
    "as_host_tool",
    "author_for",
    "event_payload",
    "known_wiki_ids",
    "load_wiki_resource_type",
    "merge_access",
    "module",
    "open_targets",
    "render_values",
    "system_author",
    "unavailable_issue",
    "wiki_slot",
]
