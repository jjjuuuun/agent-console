"""agent-console-architecture: 관측 구조도 순수 라이브러리(design §5.5R.3, 결정 K-1·K-5·K-6·K-7).

로그 이벤트(계약 `LogEvent`)와 구조도 프로필(계약 `ArchitectureProfile`, 사용자 데이터)을 받아
그리기 완결형 `ArchitectureView`를 만든다. 칸·연결·범주·도구·출처 이름은 코드에 없고 전부 프로필
데이터다.
서버·웹·로그 색인 없이 단독으로 쓴다(`ac-logs`를 import하지 않는다 — 오류 범주·출처 종류·토큰
표본은 인자로 받는다).

공개 API:
    - 프로필: ``load_default_profiles(path=None)``, ``parse_profiles_document(text)``,
      ``profiles_from_mapping(data)``, ``ProfileDocumentError``, ``DEFAULT_PROFILES_RESOURCE``
    - 병합: ``merge_profiles(defaults, plugins, user, *, include_defaults=None) -> ProfileCatalog``,
      ``ProfileCatalog``(``pick``·``get``·``ids``), ``ProfileEntry``(``info``), ``ProfileSource``
    - 검사: ``profile_issues(profile, *, operators, filters=None, profile_id=None)``,
      ``check_profile_data(data, ...)``, ``ID_PATTERN``
    - 투영: ``project_architecture(events, profile, *, profile_id, operators, source_kinds, tokens,
      error_categories, max_seq, notes, cell_size) -> ArchitectureView``, ``DEFAULT_CELL_SIZE``,
      ``DEFAULT_METRICS``, ``KNOWN_METRICS``
    - 판정: ``ProfileMatcher``(순수 판정기, 캐시 가능 — 조건은 만들 때 한 번 컴파일하고 참·거짓만
      낸다), ``EventMatch``, ``event_subject``,
      ``event_membership(event, profile, *, profile_id, operators)``,
      ``selector_predicate(profile, selector, *, profile_id, operators)``, ``format_arch``,
      ``parse_arch``, ``ArchTarget``, ``ArchitectureSelectorError``, ``EventPredicate``
    - 플러그인(X23): ``ARCHITECTURE_PROFILES_GROUP``, ``new_profile_registry``,
      ``load_profile_plugins(registry, *, enabled, entry_points)``, ``plugin_sources(registry)``,
      ``as_profile_source``
    - 테스트 도구: 모듈 ``agent_console_architecture.testing``
"""

from __future__ import annotations

from ._catalog import ProfileCatalog, ProfileEntry, ProfileSource, merge_profiles
from ._document import (
    DEFAULT_PROFILES_RESOURCE,
    ProfileDocumentError,
    load_default_profiles,
    parse_profiles_document,
    profiles_from_mapping,
)
from ._issues import ID_PATTERN, check_profile_data, profile_issues
from ._match import EventMatch, ProfileMatcher, event_membership, event_subject
from ._plugins import (
    ARCHITECTURE_PROFILES_EXTENSION,
    ARCHITECTURE_PROFILES_GROUP,
    as_profile_source,
    load_profile_plugins,
    new_profile_registry,
    plugin_sources,
)
from ._project import DEFAULT_CELL_SIZE, DEFAULT_METRICS, KNOWN_METRICS, project_architecture
from ._selector import (
    ArchitectureSelectorError,
    ArchTarget,
    EventPredicate,
    format_arch,
    parse_arch,
    selector_predicate,
)

__all__ = [
    "ARCHITECTURE_PROFILES_EXTENSION",
    "ARCHITECTURE_PROFILES_GROUP",
    "DEFAULT_CELL_SIZE",
    "DEFAULT_METRICS",
    "DEFAULT_PROFILES_RESOURCE",
    "ID_PATTERN",
    "KNOWN_METRICS",
    "ArchTarget",
    "ArchitectureSelectorError",
    "EventMatch",
    "EventPredicate",
    "ProfileCatalog",
    "ProfileDocumentError",
    "ProfileEntry",
    "ProfileMatcher",
    "ProfileSource",
    "as_profile_source",
    "check_profile_data",
    "event_membership",
    "event_subject",
    "format_arch",
    "load_default_profiles",
    "load_profile_plugins",
    "merge_profiles",
    "new_profile_registry",
    "parse_arch",
    "parse_profiles_document",
    "plugin_sources",
    "profile_issues",
    "profiles_from_mapping",
    "project_architecture",
    "selector_predicate",
]
