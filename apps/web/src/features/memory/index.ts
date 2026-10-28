/**
 * 메모리 기능의 공개 API(다른 기능 폴더·앱 조립 층이 쓰는 것만). 화면 컴포넌트는 `shell/routes.tsx`가 지연 로딩으로 조립한다.
 * 범위 종류·범위 이름·도구 이름은 이 폴더에 없다(서버 데이터).
 */
export { MemoryPage } from "./MemoryPage";
export type { MemoryPageProps } from "./MemoryPage";
export { MEMORY_ROLE, MEMORY_PARAMS, SETTINGS_SECTION } from "./memoryConfig";
export { memoryMessages } from "./messages";
export { parseView, writeView, scopeParam, parseScopeParam } from "./memoryUrl";
export type { MemoryViewState } from "./memoryUrl";
export { useMemoryKinds, useMemoryScopes, memoryKeys } from "./useMemoryApi";
export { useMemoryContext, type MemoryContext } from "./useMemoryContext";
export { MEMORY_LIMITS, IMPORTED_AUTHOR_KIND } from "./memoryConfig";
export { RunMemoryChips, type RunMemoryChipsProps } from "./RunMemoryChips";
