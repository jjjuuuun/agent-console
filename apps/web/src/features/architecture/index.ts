/** 관측 구조도 화면 조각(5.5R.15~17): 데이터 훅·컨트롤러·패널·필터 칩. 로그 화면(`features/logs`)과 실행 상세가 함께 쓴다. */
export { LazyArchitecturePanel as ArchitecturePanel } from "./lazy";
export type { ArchitecturePanelProps } from "./ArchitecturePanel";
export { ArchitectureChips, type ArchitectureChipsProps } from "./ArchitectureChips";
export { useArchitectureController, type ArchitectureChip, type ArchitectureController, type ArchitectureControllerOptions } from "./useArchitectureController";
export { useArchitectureProfiles, useArchitectureRows, useArchitectureView, useEventMembership, type ArchitectureRows } from "./useArchitectureApi";
export { classifyArchError, observedValue, resolveTarget, targetQuery, type ArchErrorInfo, type ArchTarget, type DrillStep } from "./archLib";
export { ARCH_COUNT_METRIC, ARCH_FIT, ARCH_LIMITS, ARCH_RUN_HEIGHT, ARCH_RUN_SCOPE, ARCH_STORAGE } from "./archConfig";
export { archMessages } from "./messages";
export { ArchitectureDialog, type ArchitectureDialogProps } from "./ArchitectureDialog";
