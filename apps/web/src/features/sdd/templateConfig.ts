/** 문서 틀 화면의 주소 인자 이름과 탭 표(데이터). 선택·탭·섹션은 주소가 진실이다. */
export const TEMPLATE_PARAMS = { template: "template", tab: "tab", section: "section", file: "file" } as const;

/** 탭 id와 문구 키(`templateMessages.tabs`). 본문은 `TemplateEditor`가 id로 고른다. */
export const TEMPLATE_TABS: readonly { id: "rules" | "files" | "versions" }[] = [{ id: "rules" }, { id: "files" }, { id: "versions" }];
export type TemplateTabId = (typeof TEMPLATE_TABS)[number]["id"];

/** 틀 단건 REST의 컬렉션 경로(버전 기록 경로의 밑). 서버 `/sdd/templates`. */
export const TEMPLATES_COLLECTION = "/sdd/templates";
