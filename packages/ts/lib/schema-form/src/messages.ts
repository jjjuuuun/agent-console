import ko from "./locales/ko.json";
import type { SchemaFormMessages } from "./types";

/** 기본 문구는 한국어(`locales/ko.json`). 영어는 `@agent-console/schema-form/locales/en`을 `messages`로 넘긴다. */
export const DEFAULT_MESSAGES: SchemaFormMessages = ko;

export function resolveMessages(partial?: Partial<SchemaFormMessages>): SchemaFormMessages {
  return { ...DEFAULT_MESSAGES, ...partial };
}
