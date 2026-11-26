import ko from "./locales/ko.json";

/** 컴포넌트가 기본으로 쓰는 문구(`ChipRow`·`Tabs`·`PageHeader`·`ShortcutProvider`). 값의 `{이름}`은 자리표시자다. */
export interface UiMessages {
  /** 넘친 항목 메뉴 버튼의 이름(`Tabs`·`PageHeader`) */
  more: string;
  /** `ChipRow`의 `+N` 버튼 이름. `{n}`은 가려진 칩 수 */
  moreCount: string;
  /** 단축키 중복 경고. `{keys}`·`{first}`·`{second}` */
  shortcutConflict: string;
  /** 공급자 밖에서 훅을 썼을 때의 오류 문구 */
  needsShortcutProvider: string;
}

/** 기본 문구는 한국어(`locales/ko.json`). 영어는 `@agent-console/ui/locales/en`을 `messages`로 넘긴다. */
export const defaultUiMessages: UiMessages = ko;

/** `{이름}` 자리표시자를 채운다. 없는 값은 그대로 둔다. */
export function formatUiMessage(template: string, vars: Readonly<Record<string, string | number>>): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}
