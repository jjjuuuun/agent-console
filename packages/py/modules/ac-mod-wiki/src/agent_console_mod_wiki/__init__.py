"""agent-console-mod-wiki: 위키 서버 모듈(design §7R.3·§7R.7).

``ac-wiki``(문법·파싱·링크·색인·저장소·규칙·점검·기록·검색·zip)를 서버에 붙인다: REST ``/wiki/*``,
WS ``wiki.changed``, 정의 종류 기여(X44 — 위키 규칙·위키), 사용자 설정 섹션 ``wiki``, 공간 고르기
(``wiki.spaces``, 없으면 단독 루트), 프로젝트 기록 DB(``records.spaces``), 쓰기 검사(X50
``wiki.write_checks`` + 플러그인), 검색 색인(X48 플러그인), 연동 능력(``wiki.integrations``).
실행·프로젝트를 모른다.

공개 API:
    - ``module``(entry point 값)·``WikiModule``·``MODULE_ID``·``WEB_ROLES``
    - ``WikiService``(포트 ``wiki.service``)·``WikiScope``·``WikiPorts``
    - 포트: ``WIKI_SERVICE``·``WIKI_SPACES``·``WIKI_WRITE_CHECKS``·``WIKI_INTEGRATIONS``·
      ``RECORDS_SPACES``, 모양 ``WikiSpace``·``WikiSpaces``·``WikiIntegration``·``WikiServicePort``,
      능력 이름 ``INTEGRATION_RUNS``
    - 설정: ``WikiModuleSettings``(설치자), ``parse_wiki_settings``·``SECTION_KEY``(사용자 섹션)
    - 기록: ``BRANCH``(계보 ``wiki``)·``RecordsWikiHistory``·``open_host_history``
    - 플러그인 로더 ``load_plugins``(X48·X50), 쓰기 검사 그룹 ``WRITE_CHECKS_GROUP``
"""

from __future__ import annotations

from .config import SECTION_KEY, parse_wiki_settings, section_of
from .errors import ERROR_MAP, SpaceError, WikiNotFound, WikiRequestError
from .history import BRANCH, RecordsWikiHistory, database_file, open_host_history
from .module import MODULE_ID, WEB_ROLES, WikiModule, module, wiki_references
from .plugins import (
    SEARCH_EXTENSION,
    WRITE_CHECKS_EXTENSION,
    WRITE_CHECKS_GROUP,
    as_write_check_factory,
    load_plugins,
    load_write_check_plugins,
    new_write_check_registry,
)
from .ports import (
    INTEGRATION_RUNS,
    RECORDS_SPACES,
    WIKI_INTEGRATIONS,
    WIKI_SERVICE,
    WIKI_SPACES,
    WIKI_WRITE_CHECKS,
    WikiIntegration,
    WikiServicePort,
    WikiSpace,
    WikiSpaces,
)
from .routes import PAGE_ROUTE_WORDS, content_disposition
from .service import WikiPorts, WikiScope, WikiService, unique_id, user_author
from .settings import WikiModuleSettings, package_defaults
from .ws import WIKI_TOPIC

__all__ = [
    "BRANCH",
    "ERROR_MAP",
    "INTEGRATION_RUNS",
    "MODULE_ID",
    "PAGE_ROUTE_WORDS",
    "RECORDS_SPACES",
    "SEARCH_EXTENSION",
    "SECTION_KEY",
    "WEB_ROLES",
    "WIKI_INTEGRATIONS",
    "WIKI_SERVICE",
    "WIKI_SPACES",
    "WIKI_TOPIC",
    "WIKI_WRITE_CHECKS",
    "WRITE_CHECKS_EXTENSION",
    "WRITE_CHECKS_GROUP",
    "RecordsWikiHistory",
    "SpaceError",
    "WikiIntegration",
    "WikiModule",
    "WikiModuleSettings",
    "WikiNotFound",
    "WikiPorts",
    "WikiRequestError",
    "WikiScope",
    "WikiService",
    "WikiServicePort",
    "WikiSpace",
    "WikiSpaces",
    "as_write_check_factory",
    "content_disposition",
    "database_file",
    "load_plugins",
    "load_write_check_plugins",
    "module",
    "new_write_check_registry",
    "open_host_history",
    "package_defaults",
    "parse_wiki_settings",
    "section_of",
    "unique_id",
    "user_author",
    "wiki_references",
]
