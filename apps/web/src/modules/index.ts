/** 서버 기능 모듈 목록으로 화면을 조립하는 공용 층(`docs/design/screen-modules.md`). 모듈 id·역할 이름을 모른다. */
export { ModulesProvider, useModules, useModuleList, useModule, useRequires, useRequiresPartition, partitionByRequires, evaluateRequires, loadModules, MODULES_QUERY_KEY } from "./ModulesContext";
export type { ModulesState, ModulesValue, ModulesProviderProps, RequiresState, ModuleLookup } from "./ModulesContext";
export { LinkPart, LinkPartsProvider, useLinkPart, useLinkPartDefs } from "./LinkParts";
export type { LinkPartDef, LinkPartState, LinkPartProps } from "./LinkParts";
export { RouteGate } from "./RouteGate";
export type { RouteGateProps } from "./RouteGate";
export { FeatureOffScreen, enableSnippet } from "./FeatureOffScreen";
export type { FeatureOffScreenProps } from "./FeatureOffScreen";
export { ModuleStatusChip, moduleStatusLabel } from "./ModuleStatusChip";
export { resolveRequires, worstSeverity, problemModules, isProblemStatus, modulesSignature, modulesFor, moduleAffects, moduleMatchesText, namesOf, MODULE_STATUS } from "./resolve";
export type { RequiresResult, UnmetItem, Severity } from "./resolve";
export { LINK_PART_IDS } from "./linkPartIds";
export { ModuleNotices } from "./ModuleNotices";
