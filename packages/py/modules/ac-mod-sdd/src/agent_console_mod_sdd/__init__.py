"""agent-console-mod-sdd: 스펙(SDD) 서버 모듈(design §6R.3·§6R.7).

``ac-sdd``(문법·파싱·계획·추적·저장소)를 서버에 붙인다: REST ``/sdd/*``, WS ``sdd.changed``, 정의
종류 기여(X44 — 문서 틀·스펙), 사용자 설정 섹션 ``sdd``, 공간 고르기(``sdd.spaces``, 없으면 단독
루트), 작업 연동(X43 ``sdd.integrations``)·검증 출처(X42 ``sdd.verification_sources`` + 플러그인),
파싱 캐시, 문서 본문 비밀 검사. 실행·프로젝트를 모른다.

공개 API:
    - ``module``(entry point 값)·``SddModule``·``MODULE_ID``·``WEB_ROLES``
    - ``SddService``(포트 ``sdd.service``)·``SddScope``·``SddPorts``
    - 포트: ``SDD_SERVICE``·``SDD_SPACES``·``SDD_INTEGRATIONS``·``SDD_VERIFICATION_SOURCES``,
      모양 ``SddSpace``·``SddSpaces``·``SddServicePort``, 라벨 이름 ``LABEL_*``
    - 설정: ``SddModuleSettings``(설치자), ``parse_sdd_settings``·``SECTION_KEY``(사용자 섹션)
    - ``ParseCache``·``CachedSpecRepository``, ``scan_text``, 플러그인 로더 ``load_plugins``
"""

from __future__ import annotations

from .cache import CachedSpecRepository, ParseCache, syntax_fingerprint
from .config import SECTION_KEY, parse_sdd_settings, section_of
from .errors import ERROR_MAP, SddRequestError, SpaceError
from .module import MODULE_ID, WEB_ROLES, SddModule, module, template_references
from .plugins import (
    VERIFICATION_SOURCES_EXTENSION,
    VERIFICATION_SOURCES_GROUP,
    as_verification_source,
    load_plugins,
)
from .ports import (
    LABEL_NAMES,
    LABEL_PROFILE,
    LABEL_PURPOSE,
    LABEL_SPEC,
    LABEL_TASK,
    SDD_INTEGRATIONS,
    SDD_SERVICE,
    SDD_SPACES,
    SDD_VERIFICATION_SOURCES,
    SddServicePort,
    SddSpace,
    SddSpaces,
)
from .secrets import SecretRejectedError, scan_text
from .service import SddPorts, SddScope, SddService
from .settings import SddModuleSettings, default_label_display, package_defaults
from .ws import SDD_TOPIC

__all__ = [
    "ERROR_MAP",
    "LABEL_NAMES",
    "LABEL_PROFILE",
    "LABEL_PURPOSE",
    "LABEL_SPEC",
    "LABEL_TASK",
    "MODULE_ID",
    "SDD_INTEGRATIONS",
    "SDD_SERVICE",
    "SDD_SPACES",
    "SDD_TOPIC",
    "SDD_VERIFICATION_SOURCES",
    "SECTION_KEY",
    "VERIFICATION_SOURCES_EXTENSION",
    "VERIFICATION_SOURCES_GROUP",
    "WEB_ROLES",
    "CachedSpecRepository",
    "ParseCache",
    "SddModule",
    "SddModuleSettings",
    "SddPorts",
    "SddRequestError",
    "SddScope",
    "SddService",
    "SddServicePort",
    "SddSpace",
    "SddSpaces",
    "SecretRejectedError",
    "SpaceError",
    "as_verification_source",
    "default_label_display",
    "load_plugins",
    "module",
    "package_defaults",
    "parse_sdd_settings",
    "scan_text",
    "section_of",
    "syntax_fingerprint",
    "template_references",
]
