"""agent-console-memory: 공유 메모리 핵심(design §5.7R.2).

저장소(X31)·범위 종류(X29)·접근 판단·에이전트 도구 묶음·비밀 검사. 실행 엔진·에이전트 노드·로그를
모른다(다른 에이전트 프레임워크·MCP 서버에서도 그대로 쓴다).
범위 종류 이름·도구 이름은 전부 데이터다.

공개 API:
    - 저장소(X31): ``MemoryStore`` 프로토콜, ``InMemoryMemoryStore``, ``MemoryQuery``,
      ``MemoryWriteOutcome``, ``WriteMode``.
    - 쓰기 정책: ``MemoryPolicy``·``MemoryLimits``, 비밀 검사 주입 ``SecretScanner``·
      ``SecretRulesScanner``·``MemorySecretGuard``, ``prepare_write``·``content_digest``,
      키 규칙 ``check_key``·``check_tags``.
    - 저장소 구현 도구: ``summarize``·``encode_cursor``·``decode_cursor``·``check_sort``·
      ``versions_to_drop``.
    - 범위 종류(X29): ``MemoryScopeKind``, ``ScopeKindCatalog``, ``ScopeKindOrigins``,
      ``load_default_scope_kinds``, ``scope_kinds_from_mapping``, ``merge_scope_kinds``,
      ``check_scope_kinds``, ``resolve_scope``, ``render_template``, ``template_problems``,
      ``template_context_fields``. 플러그인: ``MEMORY_SCOPE_KINDS_GROUP``,
      ``load_scope_kind_plugins``, ``new_scope_kind_registry``, ``plugin_scope_kinds``,
      ``as_scope_kinds``.
    - 접근: ``allowed``, ``scope_kinds_for``, ``granted_ops``, ``default_scope_kind``.
    - 도구 묶음: ``MemoryToolkit``, ``ToolSpec``, ``ToolOutcome``, ``ToolText``,
      ``load_tool_text``, ``WriteBudget``, ``agent_author``, ``format_author``, ``format_time``,
      ``fill``.
    - 오류: ``MemoryStoreError``, ``InvalidKeyError``, ``EntryNotFoundError``,
      ``EntryExistsError``, ``VersionConflictError``, ``TooLargeError``, ``SecretRejectedError``.
    - 테스트 도구: 하위 모듈 ``testing``(가짜 시계·표본), ``testing.contract``(저장소 계약 묶음).
"""

from ._access import allowed, default_scope_kind, granted_ops, scope_kinds_for
from ._errors import (
    EntryExistsError,
    EntryNotFoundError,
    InvalidKeyError,
    MemoryStoreError,
    SecretRejectedError,
    TooLargeError,
    VersionConflictError,
)
from ._keys import KEY_SEPARATOR, check_key, check_tags
from ._memory_store import InMemoryMemoryStore
from ._plugins import (
    MEMORY_SCOPE_KINDS_EXTENSION,
    MEMORY_SCOPE_KINDS_GROUP,
    as_scope_kinds,
    load_scope_kind_plugins,
    new_scope_kind_registry,
    plugin_scope_kinds,
)
from ._policy import (
    MemoryLimits,
    MemoryPolicy,
    MemorySecretGuard,
    PreparedWrite,
    SecretRulesScanner,
    SecretScanner,
    check_secret_field,
    content_digest,
    prepare_write,
)
from ._scope_kinds import (
    DEFAULT_SCOPE_KINDS_RESOURCE,
    MemoryScopeKind,
    ScopeKindCatalog,
    ScopeKindOrigins,
    ScopeResolver,
    check_scope_kinds,
    load_default_scope_kinds,
    merge_scope_kinds,
    render_template,
    resolve_scope,
    scope_kinds_from_mapping,
    template_context_fields,
    template_problems,
)
from ._shared import check_sort, decode_cursor, encode_cursor, summarize, versions_to_drop
from ._store import MemoryQuery, MemoryStore, MemoryWriteOutcome, SortOrder, WriteMode
from ._toolkit import (
    TOOL_TEXT_RESOURCE,
    EventSink,
    MemoryToolkit,
    ToolCall,
    ToolOutcome,
    ToolSpec,
    ToolText,
    WriteBudget,
    agent_author,
    fill,
    format_author,
    format_time,
    load_tool_text,
)

__all__ = [
    "DEFAULT_SCOPE_KINDS_RESOURCE",
    "KEY_SEPARATOR",
    "MEMORY_SCOPE_KINDS_EXTENSION",
    "MEMORY_SCOPE_KINDS_GROUP",
    "TOOL_TEXT_RESOURCE",
    "EntryExistsError",
    "EntryNotFoundError",
    "EventSink",
    "InMemoryMemoryStore",
    "InvalidKeyError",
    "MemoryLimits",
    "MemoryPolicy",
    "MemoryQuery",
    "MemoryScopeKind",
    "MemorySecretGuard",
    "MemoryStore",
    "MemoryStoreError",
    "MemoryToolkit",
    "MemoryWriteOutcome",
    "PreparedWrite",
    "ScopeKindCatalog",
    "ScopeKindOrigins",
    "ScopeResolver",
    "SecretRejectedError",
    "SecretRulesScanner",
    "SecretScanner",
    "SortOrder",
    "TooLargeError",
    "ToolCall",
    "ToolOutcome",
    "ToolSpec",
    "ToolText",
    "VersionConflictError",
    "WriteBudget",
    "WriteMode",
    "agent_author",
    "allowed",
    "as_scope_kinds",
    "check_key",
    "check_scope_kinds",
    "check_secret_field",
    "check_sort",
    "check_tags",
    "content_digest",
    "decode_cursor",
    "default_scope_kind",
    "encode_cursor",
    "fill",
    "format_author",
    "format_time",
    "granted_ops",
    "load_default_scope_kinds",
    "load_scope_kind_plugins",
    "load_tool_text",
    "merge_scope_kinds",
    "new_scope_kind_registry",
    "plugin_scope_kinds",
    "prepare_write",
    "render_template",
    "resolve_scope",
    "scope_kinds_for",
    "scope_kinds_from_mapping",
    "summarize",
    "template_context_fields",
    "template_problems",
    "versions_to_drop",
]
