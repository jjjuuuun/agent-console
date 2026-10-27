"""agent-console-logs: 로그 분석 코어(design §4R.1~§4R.6).

- 질의 확장 지점(X27 범위 종류·X28 필터 확장): `LogScopeKind`·`LogFilterExtension` 프로토콜,
  등록 묶음 `LogQueryExtensions`(필터 읽기·`scope`/확장 필터 풀기·스키마).
- 출처·분류기 확장 지점(X5·X6): `LogSource`·`LogClassifier` 프로토콜, `LogRegistries`
  (entry point `agent_console.log_sources`·`agent_console.log_classifiers`).
- 증분 jsonl 출처 기반 클래스 `JsonlFileSource`(agent_bench `_ingest` 규칙).
- 수집기 `LogIngestor`, 색인 프로토콜 `LogIndex`(메모리 구현은 `testing.MemoryLogIndex`).
- 색인 비우기(M-3): `purge_index`(출처·범주·시각 범위, `dry_run`)·`reset_index`, 선택 능력
  `PurgeableLogIndex`(메모리·SQLite 색인이 가진다).
- 행 읽기(5.5R.36): `query_event_rows`·`iter_event_rows` — 목록 쪽을 모델 없이 JSON 행(dict)으로
  (선택 능력 `LogEventRowReader`, 메모리·SQLite 색인이 가진다).
- 순수 함수: `bounded`·`event_uid`·`link_events`·`merge_taxonomy`·`group_projects`·`block_windows`,
  질의 의미 `agent_console_logs.query`.
- 오프라인 보관본: `build_archive`(`LogArchive` v1, 필터 범위·크기 한도·가림) +
  `render_archive`(스크립트 없는 HTML).
- 기본 제공 플러그인 `normalized-v1`·`mapped-jsonl`(`agent_console_logs.plugins`)도 entry point로만
  등록된다. 특정 도구 형식(Claude Code 등)은 이 패키지가 모른다.

서버·웹 없이 쓴다. fastapi·starlette를 import하지 않는다.
"""

from __future__ import annotations

from agent_console_registry import LoadReport

from ._archive import (
    ARCHIVE_VERSION,
    DEFAULT_ARCHIVE_MAX_BYTES,
    DEFAULT_ARCHIVE_MAX_EVENTS,
    build_archive,
    filter_to_params,
)
from ._archive_html import DEFAULT_ARCHIVE_TITLE, escape_html, render_archive
from ._build import build_record, event_uid, identity_for
from ._config import ConfigError, effective_config
from ._correlate import correlation_keys, link_events, pair_durations
from ._draft import TAG_DIAGNOSTIC, TAG_SESSION_TITLE, TAG_TOOL, AgentInfo, LogEventDraft
from ._extend import LogFilterContext, LogFilterExtension, LogQueryExtensions, LogScopeKind
from ._filter import (
    DIMENSIONS,
    FILTER_FIELDS,
    METRICS,
    EventPredicate,
    LogFilter,
    LogQueryError,
    LogScope,
    QueryContext,
    parse_log_filter,
    parse_tz,
    query_context,
    query_schema,
    require_refined,
)
from ._glob import glob_match
from ._index import BatchResult, IndexBatch, IndexRecord, LogIndex, StoredCursor
from ._ingest import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_BUDGET_BYTES,
    ERROR_INVALID_CONFIG,
    ERROR_SOURCE_FAILED,
    ERROR_UNKNOWN_CLASSIFIER,
    LogIngestor,
    source_enabled,
)
from ._jsonl import JSONL_CONFIG_SCHEMA, JsonlFileSource, expand_user_path
from ._projects import (
    UNGROUPED_PROJECT,
    RepoRootResolver,
    git_worktree_root,
    group_projects,
    resolve_project,
)
from ._purge import PurgeableLogIndex, PurgeResult, PurgeScope, purge_index, reset_index
from ._registries import (
    LOG_CLASSIFIERS_EXTENSION,
    LOG_CLASSIFIERS_GROUP,
    LOG_SOURCES_EXTENSION,
    LOG_SOURCES_GROUP,
    LogRegistries,
    as_log_classifier,
    as_log_source,
)
from ._rows import (
    LogEventRow,
    LogEventRowPage,
    LogEventRowReader,
    PageCallback,
    complete_event_row,
    event_row,
    iter_event_rows,
    page_rows,
    query_event_rows,
)
from ._source import (
    DIAGNOSTIC_META_KEY,
    ClassifyContext,
    Cursor,
    LogClassifier,
    LogSource,
    LogSourceContext,
    RawRecord,
    ReadResult,
    SourceRef,
    read_only_open,
)
from ._taxonomy import (
    error_categories,
    hidden_categories,
    load_default_taxonomy,
    load_taxonomy,
    merge_taxonomy,
)
from ._titles import (
    DEFAULT_SESSION_TITLE_RULES,
    DEFAULT_SESSION_TITLE_RULES_RESOURCE,
    SessionTitleRule,
    load_default_session_title_rules,
    parse_session_title_rules,
    pick_session_title,
)
from ._values import (
    JsonValue,
    bounded,
    dirty_surrogates,
    json_pointer,
    scrub_surrogates,
    text,
    timestamp,
)
from ._windows import TokenBlock, block_windows, rolling_totals, sum_samples

__all__ = [
    "ARCHIVE_VERSION",
    "DEFAULT_ARCHIVE_MAX_BYTES",
    "DEFAULT_ARCHIVE_MAX_EVENTS",
    "DEFAULT_ARCHIVE_TITLE",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_BUDGET_BYTES",
    "DEFAULT_SESSION_TITLE_RULES",
    "DEFAULT_SESSION_TITLE_RULES_RESOURCE",
    "DIAGNOSTIC_META_KEY",
    "DIMENSIONS",
    "ERROR_INVALID_CONFIG",
    "ERROR_SOURCE_FAILED",
    "ERROR_UNKNOWN_CLASSIFIER",
    "FILTER_FIELDS",
    "JSONL_CONFIG_SCHEMA",
    "LOG_CLASSIFIERS_EXTENSION",
    "LOG_CLASSIFIERS_GROUP",
    "LOG_SOURCES_EXTENSION",
    "LOG_SOURCES_GROUP",
    "METRICS",
    "TAG_DIAGNOSTIC",
    "TAG_SESSION_TITLE",
    "TAG_TOOL",
    "UNGROUPED_PROJECT",
    "AgentInfo",
    "BatchResult",
    "ClassifyContext",
    "ConfigError",
    "Cursor",
    "EventPredicate",
    "IndexBatch",
    "IndexRecord",
    "JsonValue",
    "JsonlFileSource",
    "LoadReport",
    "LogClassifier",
    "LogEventDraft",
    "LogEventRow",
    "LogEventRowPage",
    "LogEventRowReader",
    "LogFilter",
    "LogFilterContext",
    "LogFilterExtension",
    "LogIndex",
    "LogIngestor",
    "LogQueryError",
    "LogQueryExtensions",
    "LogRegistries",
    "LogScope",
    "LogScopeKind",
    "LogSource",
    "LogSourceContext",
    "PageCallback",
    "PurgeResult",
    "PurgeScope",
    "PurgeableLogIndex",
    "QueryContext",
    "RawRecord",
    "ReadResult",
    "RepoRootResolver",
    "SessionTitleRule",
    "SourceRef",
    "StoredCursor",
    "TokenBlock",
    "as_log_classifier",
    "as_log_source",
    "block_windows",
    "bounded",
    "build_archive",
    "build_record",
    "complete_event_row",
    "correlation_keys",
    "dirty_surrogates",
    "effective_config",
    "error_categories",
    "escape_html",
    "event_row",
    "event_uid",
    "expand_user_path",
    "filter_to_params",
    "git_worktree_root",
    "glob_match",
    "group_projects",
    "hidden_categories",
    "identity_for",
    "iter_event_rows",
    "json_pointer",
    "link_events",
    "load_default_session_title_rules",
    "load_default_taxonomy",
    "load_taxonomy",
    "merge_taxonomy",
    "page_rows",
    "pair_durations",
    "parse_log_filter",
    "parse_session_title_rules",
    "parse_tz",
    "pick_session_title",
    "purge_index",
    "query_context",
    "query_event_rows",
    "query_schema",
    "read_only_open",
    "render_archive",
    "require_refined",
    "reset_index",
    "resolve_project",
    "rolling_totals",
    "scrub_surrogates",
    "source_enabled",
    "sum_samples",
    "text",
    "timestamp",
]
