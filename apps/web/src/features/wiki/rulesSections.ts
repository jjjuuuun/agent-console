/** 규칙 탭 섹션 키(화면 구조)와 그 DOM id. 섹션 이름 문구는 `wikiTabMessages.rules.sections`, 위젯과 탭이 같은 id를 쓴다. */
export const RULES_SECTION_KEYS = ["info", "used", "instructions", "merged", "syntax"] as const;
export type RulesSectionKey = (typeof RULES_SECTION_KEYS)[number];

export const sectionDomId = (key: RulesSectionKey): string => `wiki-rules-sec-${key}`;
