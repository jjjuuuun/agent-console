"""agent-console-link-definitions-resources: 정의 ↔ 리소스 연동 모듈(design §3R.1.4 L8, R13.1).

저장 전 정의 검사(``definitions.checks``)를 제공한다: 리소스 정의는 그 종류의 검사, 에이전트·팀
구성·공통 설정은 리소스 첨부 덮어쓰기 검사(``x-secret`` 평문 거부). 정의 모듈의 저장 경로·버전
되돌리기와 ``/server-info`` 평문 점검이 이 검사를 쓴다.

공개 API:
    - ``module``(``DefinitionsResourcesLink``): entry point ``agent_console.server_modules``의
      ``link-definitions-resources``.
    - ``DefinitionChecker``: HTTP·서버 없이 쓰는 검사. ``LookupResources``·
      ``resource_document_path``.
    - 포트(``ports``): 받는 포트 4개와 제공 포트 ``DEFINITION_CHECKS``, 소비자 쪽 프로토콜.
"""

from __future__ import annotations

from .checks import DefinitionChecker, LookupResources, resource_document_path
from .module import MODULE_ID, DefinitionsResourcesLink, module
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    SECRET_RULES,
    DefinitionCheck,
    DefinitionLookup,
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITION_CHECKS",
    "MODULE_ID",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "SECRET_RULES",
    "DefinitionCheck",
    "DefinitionChecker",
    "DefinitionLookup",
    "DefinitionsResourcesLink",
    "LookupResources",
    "module",
    "resource_document_path",
]
