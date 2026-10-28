import "./logs.css";
/**
 * 로그 기능의 공개 API(다른 기능 폴더·앱 조립 층이 쓰는 것만). 화면 컴포넌트는 `shell/routes.tsx`가 지연 로딩으로 조립하고,
 * 설정의 "로그 출처" 섹션과 실행 상세의 "세션 로그" 탭은 아래 컴포넌트를 가져다 쓴다.
 */
export { LogsLayout, LogsIndexRedirect } from "./LogsPageFrame";
export { SessionsPage } from "./SessionsPage";
export { SessionDetailPage } from "./SessionDetailPage";
export { SearchPage } from "./SearchPage";
export { DashboardsPage } from "./DashboardsPage";
export { useLogSources, useLogTaxonomy, useLogSchema, useLogClassifiers } from "./useLogsApi";
export { useLogScan } from "./useLogScan";
export { describeSourceStatus } from "./sourceStatus";
export { settingsLogsHref } from "./LogsEmpty";
export { logsMessages } from "./messages";
export { FILTER_KEYS, TONE_VOCABULARY, UNGROUPED_OPTIONS, UNGROUPED_PROJECT_VALUE } from "./logsConfig";
export { RunSessionLogsTab } from "./RunSessionLogsTab";
export type { RunSessionLogsTabProps } from "./RunSessionLogsTab";
export { LOGS_ROLE, LOG_TABS } from "./logsConfig";
export { slotFor } from "./slots";
export { RunArchitectureTab } from "./RunArchitectureTab";
export type { RunArchitectureTabProps } from "./RunArchitectureTab";
export { ArchitecturePopoutScreen, parseScope } from "./ArchitecturePopoutScreen";
