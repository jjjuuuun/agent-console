/**
 * @agent-console/folder-picker — 폴더 경로 입력·확인 결과·찾아보기 패널(가상 목록)·가운데 줄임 경로.
 * 서버(api-client)를 모른다. `check`·`list`·`createFolder`를 콜백 props로 받는다. 스타일은 `@agent-console/folder-picker/styles.css`.
 */
export { FolderPicker } from "./FolderPicker";
export type { FolderPickerProps } from "./FolderPicker";
export { FolderPathInput } from "./FolderPathInput";
export type { FolderPathInputProps } from "./FolderPathInput";
export { FolderCheckResult } from "./FolderCheckResult";
export type { FolderCheckResultProps } from "./FolderCheckResult";
export { FolderBrowser } from "./FolderBrowser";
export type { FolderBrowserProps } from "./FolderBrowser";
export { FolderPickStatusLine } from "./FolderPickStatus";
export type { FolderPickStatusProps, FolderSelectPhase } from "./FolderPickStatus";
export { SelectedFolder } from "./SelectedFolder";
export type { SelectedFolderProps } from "./SelectedFolder";
export { MiddleEllipsisPath } from "./MiddleEllipsisPath";
export type { MiddleEllipsisPathProps } from "./MiddleEllipsisPath";

export { useFolderCheck } from "./useFolderCheck";
export type { UseFolderCheck, UseFolderCheckOptions } from "./useFolderCheck";
export { useElementCells } from "./useElementCells";

export { browseStartPath, checkingState, deriveCheckState, errorState, IDLE_STATE } from "./checkState";
export type { CheckGroup, CheckStateId, CheckTone, DeriveOptions, FolderCheckState } from "./checkState";
export { CELL_WIDTH_PX, cells, cellsForWidth, middleEllipsis } from "./middleEllipsis";
export { collapseCrumbs, splitPath } from "./pathSegments";
export type { PathSegment } from "./pathSegments";
export { createTranslate, defaultMessages, formatMessage } from "./messages";
export type { FolderPickerMessages, MessageKey, MessageOverrides, Translate } from "./messages";
export type {
  FolderCapabilitiesData, FolderCheckData, FolderCheckFn, FolderCheckOutcome, FolderCheckRequest, FolderCreateFn, FolderCreateRequest, FolderCreateResult,
  FolderEntryData, FolderListFn, FolderListRequest, FolderListingData, FolderManifestInfo, FolderPickFn, FolderPickOutcome, FolderPickStatus, FolderRootData,
} from "./types";
