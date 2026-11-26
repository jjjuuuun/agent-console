import { flattenMessageTree } from "@agent-console/markdown-doc";
import ko from "./locales/ko.json";

/** 나무의 경로 문자열 합집합: `{ a: { b: "x", _: "y" } }` → `"a.b" | "a"`. */
type TreePaths<T, P extends string = ""> = T extends string
  ? P
  : { [K in keyof T & string]: TreePaths<T[K], K extends "_" ? P : P extends "" ? K : `${P}.${K}`> }[keyof T & string];

export type WikiViewMessageKey = TreePaths<typeof ko>;

/**
 * 문구 표. 앱이 `messages` prop으로 일부만 덮어쓴다(번역·용어 바꾸기). `{이름}` 자리는 `formatMessage`가 채운다.
 * 이 표에는 위키 이름·페이지 경로·링크 패턴·규칙 id 같은 사용자 데이터가 없다. 열린 문자열 값(동작·종류·심각도)의 이름은 `WikiDisplay`가 준다.
 * 한국어 기본 문구 표는 `locales/ko.json`을 편 것이다(점 표기 키를 나무로 편 모양, 한 키가 다른 키의 앞부분이면 값을 `_`에 둔다).
 */
export const defaultMessages = flattenMessageTree(ko) as Readonly<Record<WikiViewMessageKey, string>>;

/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type WikiViewMessages = { [K in WikiViewMessageKey]: string } & Readonly<Record<string, string>>;

/** 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다. */
export function formatMessage(template: string | undefined, vars: Readonly<Record<string, string | number>> = {}): string {
  return (template ?? "").replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Readonly<Record<string, string>>): WikiViewMessages {
  return partial ? ({ ...defaultMessages, ...partial } as WikiViewMessages) : (defaultMessages as WikiViewMessages);
}
