/**
 * @agent-console/memory-view — 공유 메모리 표현 컴포넌트.
 * 범위 나무·항목 표(가상 목록)·본문 편집기·항목 정보·버전 목록/비교·정리 미리보기와 순수 함수
 * (`groupScopes`·`scopeLabel`·`formatAuthor`·`visibleScopes`)를 낸다. API·저장소·api-client·log-view를 모른다.
 * 범위 종류·범위 이름·도구 이름은 코드에 없고 전부 props 데이터다.
 */
export { MemoryScopeTree } from "./MemoryScopeTree";
export type { MemoryScopeTreeProps } from "./MemoryScopeTree";
export {
  COLUMN_WIDTHS, KEY_COLUMN_MIN, MemoryEntryTable, ROW_HEIGHT_COMPACT, ROW_HEIGHT_TALL, TAGS_COLUMN_MIN_WIDTH, tableColumns, tableRowHeight,
} from "./MemoryEntryTable";
export type { EntryColumnId, MemoryEntryTableProps } from "./MemoryEntryTable";
export { MemoryEntryEditor } from "./MemoryEntryEditor";
export type { EditorSlotProps, EntrySaveState, MemoryEntryEditorHandle, MemoryEntryEditorProps } from "./MemoryEntryEditor";
export { MemoryEntryMeta } from "./MemoryEntryMeta";
export type { MemoryEntryMetaProps, MemoryMetaDraft } from "./MemoryEntryMeta";
export { MemoryVersionList } from "./MemoryVersionList";
export type { MemoryVersionListProps } from "./MemoryVersionList";
export { DEFAULT_BODYLESS_OPS, DEFAULT_DELETE_OPS, MemoryVersionDiff } from "./MemoryVersionDiff";
export type { MemoryVersionDiffProps, VersionCompareTarget } from "./MemoryVersionDiff";
export { RETENTION_MAX_ROWS, RetentionPreview } from "./RetentionPreview";
export type { RetentionItemDetail, RetentionPreviewProps } from "./RetentionPreview";

export { formatAuthor, groupScopes, parseScopeId, sameScope, scopeKey, scopeLabel, templateFields, visibleScopes } from "./scopes";
export type {
  FormatAuthorOptions, FormattedAuthor, GroupScopesOptions, NameResolution, ScopeGroup, ScopeGroups, ScopeGroupState, ScopeLabel, ScopeLabelPart,
  ScopeNameResolvers, VisibleScopes, VisibleScopesOptions,
} from "./scopes";
export {
  KEY_MAX_LENGTH, formatBytes, formatRelativeTime, formatSizeDelta, formatTimestamp, hashSlot, keyErrorText, languageForContentType, nextSort, orderText, secretRejectedField, utf8Bytes, validateKey,
} from "./format";
export type { KeyErrorCode, SortState } from "./format";
export { defaultMessages, formatMessage, messageOr, resolveMessages } from "./messages";
export type { MemoryViewMessageKey, MemoryViewMessages } from "./messages";
export { useVirtualRows } from "./hooks";
export { MemorySortMenu } from "./MemorySortMenu";
export type { MemorySortMenuProps } from "./MemorySortMenu";
