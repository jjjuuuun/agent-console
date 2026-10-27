/** 프로젝트 UI의 공개 API(다른 기능 폴더는 이 파일로만 import한다). 프로젝트 기능이 꺼져 있으면 모든 부품이 아무것도 그리지 않는다. */
import "./projects.css";
export { ProjectsProvider, useProjects, PROJECTS_QUERY_KEY, SCOPE_VIEW_STORAGE_KEY, type ProjectsValue } from "./ProjectsContext";
export { SidebarProjectSwitcher } from "./SidebarProjectSwitcher";
export { ProjectSwitcher, type ProjectSwitcherProps } from "./ProjectSwitcher";
export { ProjectsSection } from "./ProjectsSection";
export { ProjectField, ProjectTag, ScopeFilter, useNewScope, type NewScope } from "./ScopeControls";
export { useScopedList, type ScopedList, type ScopedListOptions } from "./useScopedList";
export { MoveToProjectDialog, type MoveItem } from "./MoveToProjectDialog";
export { SelectMark, SelectionToolbar, useListSelection, useProjectMove } from "./useProjectMove";
export { PROJECT_SHORTCUT_DEFS } from "./shortcuts";
export { PROJECTS_SECTION_ID, SETTINGS_PROJECTS_HASH } from "./sectionId";
export { projectMessages } from "./messages";
export { ScopeIssuesList, useMoveIssueToShared, type MoveIssueToShared } from "./ScopeIssues";
export { AccountWideNote, LogProjectNote } from "./AccountAndLogs";
export { projectBody, useProjectId } from "./useProjectId";
export { useProjectScopeFilter } from "./useProjectScopeFilter";
