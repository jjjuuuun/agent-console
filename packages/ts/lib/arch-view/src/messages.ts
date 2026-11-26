import { withJosa } from "./josa";
import ko from "./locales/ko.json";

/**
 * 구조도 표현 컴포넌트가 쓰는 기본 문구(한국어, `locales/ko.json`). 값은 `{n}` 같은 자리표시자를 가진 틀이다(docs/design/screen-architecture.md §12).
 * 영어는 `@agent-console/arch-view/locales/en`을 `messages`로 넘긴다.
 */
export const defaultMessages: ArchViewMessages = ko;

export type ArchViewMessages = { [K in keyof typeof ko]: string };

/**
 * 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다.
 * `{이름|으로/로}`는 값 뒤에 받침에 맞는 조사(받침 있을 때/없을 때)를 붙인다(`josa`).
 */
export function formatMessage(template: string, vars: Record<string, string | number> = {}): string {
  return template.replace(/\{(\w+)(?:\|([^{}|]+))?\}/g, (m, k: string, pair?: string) => {
    if (!(k in vars)) return m;
    const v = String(vars[k]);
    return pair ? withJosa(v, pair) : v;
  });
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Partial<ArchViewMessages>): ArchViewMessages {
  return partial ? { ...defaultMessages, ...partial } : defaultMessages;
}
