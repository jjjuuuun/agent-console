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
    VersionWriteCheck,
)
from .kinds import (
    AGENT_KIND,
    DEFAULT_KINDS,
    GRAPH_KIND,
    RESOURCE_KIND,
    SCOPE_FIELD,
    SETTINGS_KIND,
    DefinitionKind,
    KindContributionLike,
    KindSkipped,
    contributed_kinds,
)
from .lazy_versions import LazyVersionRepository, versions_for
from .memory import InMemoryStorage, InMemoryVersionRepository
from .migrate import (
    branch_version_table,
    current_revision,
    downgrade,
    script_revisions,
    upgrade,
    upgrade_on,
)
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
from .records import (
    RECORDS_SPACES_PORT,
    RecordsAbsent,
    RecordsDb,
    RecordsHandle,
    RecordsSpaces,
    RecordsState,
    RecordsUnavailable,
    can_write_path,
    inspect_records,
    is_network_fs,
    open_records_db,
)
from .records_move import (
    MoveCounts,
    MoveDependent,
    MoveError,
    MovePartialError,
    MoveSpec,
    MoveVerifyError,
    RecordsMove,
    run_moves,
)
from .records_stores import RecordsStores
from .records_versions import RecordsEngines, RecordsVersionRepository
from .run_page import MAX_PAGE_LIMIT, InvalidCursor, decode_cursor, encode_cursor
from .snapshot import get_run_snapshot
from .source_page import (
    SourcePage,
    decode_source_cursor,
    encode_source_cursor,
    page_across_sources,
)
from .spaces import (
    DEFINITIONS_SPACES_PORT,
    DefinitionSpaces,
    MappedSpaces,
    SpaceStores,
    SpacesUnavailable,
    UnknownSpace,
)
from .sqlite import SqliteStorage, create_sqlite_engine, open_sqlite
from .yaml_io import atomic_write_bytes, dump_yaml, load_yaml_text, merge_into, to_plain, wrap_value

__all__ = [
    "AGENT_KIND",
    "DEFAULT_KINDS",
    "DEFAULT_MAX_CONTENT_BYTES",
    "DEFINITIONS_SPACES_PORT",
    "GRAPH_KIND",
    "LEGACY_BRANCH",
    "MAX_PAGE_LIMIT",
    "RECORDS_SPACES_PORT",
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
    "DefinitionSpaces",
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
    "InvalidCursor",
    "InvalidIdentifier",
    "KindContributionLike",
    "KindSkipped",
    "LazyVersionRepository",
    "MappedSpaces",
    "MigrationBranchLike",
    "MoveCounts",
    "MoveDependent",
    "MoveError",
    "MovePartialError",
    "MoveSpec",
    "MoveVerifyError",
    "NotFound",
    "ObservedVersionRepository",
    "ProjectAssignStore",
    "RecordsAbsent",
    "RecordsDb",
    "RecordsEngines",
    "RecordsHandle",
    "RecordsMove",
    "RecordsSpaces",
    "RecordsState",
    "RecordsStores",
    "RecordsUnavailable",
    "RecordsVersionRepository",
    "RunRepository",
    "SourcePage",
    "SpaceStores",
    "SpacesUnavailable",
    "SqliteDatabase",
    "SqliteStorage",
    "StoreError",
    "StoreErrorBody",
    "StoredDefinition",
    "UnknownSpace",
    "VersionConflict",
    "VersionRecorded",
    "VersionRepository",
    "VersionRequired",
    "VersionWriteCheck",
    "WriteGuard",
    "assign_project",
    "atomic_write_bytes",
    "branch_version_table",
    "can_write_path",
    "canonical_json",
    "check_content_path",
    "contributed_kinds",
    "count_projects",
    "create_sqlite_engine",
    "current_revision",
    "decode_cursor",
    "decode_source_cursor",
    "default_hash",
    "downgrade",
    "dump_yaml",
    "encode_cursor",
    "encode_source_cursor",
    "get_run_snapshot",
    "inspect_records",
    "is_network_fs",
    "list_graph_summaries",
    "load_yaml_text",
    "merge_into",
    "open_records_db",
    "open_sqlite",
    "page_across_sources",
    "plan_assignment",
    "run_moves",
    "script_revisions",
    "store_error_body",
    "to_plain",
    "to_project_counts",
    "to_versioned_graph",
    "upgrade",
    "upgrade_on",
    "versions_for",
    "wrap_value",
]
