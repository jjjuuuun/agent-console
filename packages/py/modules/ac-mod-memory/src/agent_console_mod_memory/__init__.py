"""agent-console-mod-memory: 공유 메모리 서버 모듈(design §5.7R.2·§5.7R.5.2·§5.7R.6, R16).

``ac-memory``(저장소·범위 종류·정리·내보내기/가져오기)를 서버에 꽂는다. REST ``/memory/*``·WS 토픽
``memory.changed``·사용자 설정 섹션 ``memory``·계보 ``memory``·정리 스케줄을 맡고, 실행 연동이 쓰는
포트 ``memory.service``를 낸다. 실행·로그를 모른다.

공개 API:
    - ``module``(``MemoryModule``): entry point ``agent_console.server_modules``의 ``mod-memory``.
    - 포트(``ports``): 제공 ``MEMORY_SERVICE``(``MemoryServicePort``)·``SERVER_WARNINGS``,
      받음(선택) ``WORKSPACE_SETTINGS``.
    - HTTP 없이 쓰는 부품: ``MemoryService``(서비스), ``open_memory_storage``(저장소 열기·계보
      ``BRANCH``), ``ObservedMemoryStore``·``observe``(변경 알림 감싸개), ``parse_memory_settings``·
      ``section_of``(설정 섹션 읽기), ``MemoryModuleSettings``(설치자 옵션).
    - ``build_router``·``topic_handlers``·``ERROR_MAP``,
      호스트 플러그인 로더 ``plugins.load_plugins``.
"""

from __future__ import annotations

from .config import SECTION_KEY, parse_memory_settings, section_of
from .errors import ERROR_MAP, MemoryRequestError, VersionRequiredError
from .module import MODULE_ID, WEB_ROLES, MemoryModule, module
from .observed import ObservedMemoryStore, changed, observe
from .ports import MEMORY_SERVICE, SERVER_WARNINGS, WORKSPACE_SETTINGS, MemoryServicePort
from .routes import build_router
from .service import USER_AUTHOR, MemoryService
from .settings import MemoryModuleSettings
from .storage import BRANCH, MemoryStorage, open_memory_storage, storage_memory_warning
from .ws import MEMORY_TOPIC, LoopPublisher, changed_message, topic_handlers

__all__ = [
    "BRANCH",
    "ERROR_MAP",
    "MEMORY_SERVICE",
    "MEMORY_TOPIC",
    "MODULE_ID",
    "SECTION_KEY",
    "SERVER_WARNINGS",
    "USER_AUTHOR",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "LoopPublisher",
    "MemoryModule",
    "MemoryModuleSettings",
    "MemoryRequestError",
    "MemoryService",
    "MemoryServicePort",
    "MemoryStorage",
    "ObservedMemoryStore",
    "VersionRequiredError",
    "build_router",
    "changed",
    "changed_message",
    "module",
    "observe",
    "open_memory_storage",
    "parse_memory_settings",
    "section_of",
    "storage_memory_warning",
    "topic_handlers",
]
