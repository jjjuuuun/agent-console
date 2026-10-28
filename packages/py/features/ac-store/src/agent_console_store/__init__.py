"""agent-console-store: 저장소 인터페이스와 구현.

- 정의(graph, agent, settings, ...): `DefinitionStore` -> `FileDefinitionStore`(YAML),
  `InMemoryDefinitionStore`
- 버전 이력: `VersionRepository` (SQLite 또는 메모리), 기록 알림 감싸개 `ObservedVersionRepository`
- 실행 기록: `RunRepository`, `EventRepository`,
  상호작용 `InteractionRepository`
  (대화·채팅 대기열은 `agent_console_mod_chat.storage`가 소유한다, design §3R.1.7)
  -> `open_sqlite(path)`(`SqliteStorage`) 또는 `InMemoryStorage`

계약(`agent_console_contracts`)에만 의존한다. 설계: specs/agent-console/design.md §2.3, §6.2.
"""

from .content_path import check_content_path
from .database import LEGACY_BRANCH, MigrationBranchLike, SqliteDatabase
from .definition_store import (
    DEFAULT_MAX_CONTENT_BYTES,
    BaseDefinitionStore,
    InMemoryDefinitionStore,
    WriteGuard,
)
from .errors import (
    AlreadyExists,
    ContentTooLarge,
    DefinitionCorrupt,
    EventConflict,
    InteractionClosed,
    InvalidContentPath,
    InvalidIdentifier,
    NotFound,
    StoreError,
    StoreErrorBody,
    VersionConflict,
    VersionRequired,
    store_error_body,
)
from .file_store import FileDefinitionStore
from .graphs import list_graph_summaries, to_versioned_graph
from .hashing import HashFn, canonical_json, default_hash
from .interfaces import (
    DefinitionStore,
    DefinitionSummary,
    EventRepository,
    InteractionRepository,
    RunRepository,
    StoredDefinition,
    VersionRepository,
)
from .kinds import (
    AGENT_KIND,
    DEFAULT_KINDS,
    GRAPH_KIND,
    RESOURCE_KIND,
    SCOPE_FIELD,
    SETTINGS_KIND,
    DefinitionKind,
)
from .lazy_versions import LazyVersionRepository, versions_for
from .memory import InMemoryStorage, InMemoryVersionRepository
from .migrate import branch_version_table, current_revision, downgrade, upgrade
from .observed import ObservedVersionRepository, VersionRecorded
from .project_assign import (
    AssignCandidate,
    AssignPlan,
    ProjectAssignStore,
    assign_project,
    count_projects,
    plan_assignment,
    to_project_counts,
)
from .snapshot import get_run_snapshot
from .sqlite import SqliteStorage, create_sqlite_engine, open_sqlite
from .yaml_io import atomic_write_bytes, dump_yaml, load_yaml_text, merge_into, to_plain, wrap_value

__all__ = [
    "AGENT_KIND",
    "DEFAULT_KINDS",
    "DEFAULT_MAX_CONTENT_BYTES",
    "GRAPH_KIND",
    "LEGACY_BRANCH",
    "RESOURCE_KIND",
    "SCOPE_FIELD",
    "SETTINGS_KIND",
    "AlreadyExists",
    "AssignCandidate",
    "AssignPlan",
    "BaseDefinitionStore",
    "ContentTooLarge",
    "DefinitionCorrupt",
    "DefinitionKind",
    "DefinitionStore",
    "DefinitionSummary",
    "EventConflict",
    "EventRepository",
    "FileDefinitionStore",
    "HashFn",
    "InMemoryDefinitionStore",
    "InMemoryStorage",
    "InMemoryVersionRepository",
    "InteractionClosed",
    "InteractionRepository",
    "InvalidContentPath",
    "InvalidIdentifier",
    "LazyVersionRepository",
    "MigrationBranchLike",
    "NotFound",
    "ObservedVersionRepository",
    "ProjectAssignStore",
    "RunRepository",
    "SqliteDatabase",
    "SqliteStorage",
    "StoreError",
    "StoreErrorBody",
    "StoredDefinition",
    "VersionConflict",
    "VersionRecorded",
    "VersionRepository",
    "VersionRequired",
    "WriteGuard",
    "assign_project",
    "atomic_write_bytes",
    "branch_version_table",
    "canonical_json",
    "check_content_path",
    "count_projects",
    "create_sqlite_engine",
    "current_revision",
    "default_hash",
    "downgrade",
    "dump_yaml",
    "get_run_snapshot",
    "list_graph_summaries",
    "load_yaml_text",
    "merge_into",
    "open_sqlite",
    "plan_assignment",
    "store_error_body",
    "to_plain",
    "to_project_counts",
    "to_versioned_graph",
    "upgrade",
    "versions_for",
    "wrap_value",
]
