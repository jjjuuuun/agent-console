/**
 * 위키 기능의 공개 API(다른 기능 폴더·앱 조립 층이 쓰는 것만, 가벼운 것만). 화면 컴포넌트(`WikiListScreen`·`WikiScreen`)는
 * 무거운 패키지(편집기·그래프)를 끌어오므로 여기서 다시 내보내지 않고 `shell/routes.tsx`가 지연 로딩으로 조립한다.
 * 위키 이름·페이지 경로·링크 패턴·머리말 키·규칙 id·쓰기 규칙 동작은 이 폴더에 없다(서버 데이터).
 */
export { WIKI_ROLE, WIKI_RULES_ROLE, WIKI_PARAMS, buildWikiDisplay } from "./wikiConfig";
export { wikiMessages } from "./messages";
export { wikiListPath, wikiPath, wikiPagePath, wikiRulesPath } from "./wikiPaths";
export { wikiKeys, useWikiSpace, useWikiInfo, useWikiList, useWikiView, usePageList, usePage, useWikiLive, useInvalidateWiki } from "./useWikiApi";
export { useWikiContext, type WikiContext } from "./useWikiContext";
export { classifyWikiError, type WikiFailure } from "./wikiErrors";
export type { WikiTabProps, WikiTabPanels, NewPagePrefill } from "./wikiTabs";
export { useNewWikiDialog, useImportDialog, useExportDialog, useDeleteWikiDialog, useRulesScreenOn } from "./wikiDialogs";
export { NewPageDialog, type NewPageDialogProps } from "./PageDialogs";
