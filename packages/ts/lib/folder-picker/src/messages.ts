import ko from "./locales/ko.json";

/**
 * folder-picker 문구(docs/design/screen-projects.md §12.1, 접두 없이 원래 키 그대로). 값의 `{이름}`은 자리표시자다.
 * 모듈·기능 이름은 문구에 없다. 앱은 `messages` prop으로 일부만 덮어쓸 수 있다.
 * 기본 문구는 한국어(`locales/ko.json`). 영어는 `@agent-console/folder-picker/locales/en`을 `messages`로 넘긴다.
 */
export const defaultMessages = ko;

export type MessageKey = keyof typeof defaultMessages;
export type FolderPickerMessages = Record<MessageKey, string>;
export type MessageOverrides = Partial<Record<string, string>>;
export type Translate = (key: MessageKey | (string & {}), vars?: Record<string, string | number>) => string;

/** `{이름}` 자리표시자를 채운다. 없는 값은 그대로 둔다. */
export function formatMessage(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}

/** 기본 문구 위에 덮어쓸 문구를 얹은 번역 함수를 만든다. 키가 없으면 키 문자열을 돌려준다. */
export function createTranslate(overrides?: MessageOverrides): Translate {
  const table: Record<string, string | undefined> = { ...defaultMessages, ...overrides };
  return (key, vars) => formatMessage(table[key] ?? key, vars);
}
