import ko from "./locales/ko.json";

/** 문구 나무(JSON 모양). 값은 문자열이거나 하위 나무다. */
export interface MessageTree {
  readonly [key: string]: string | MessageTree;
}

/** 나무의 경로 문자열 합집합: `{ a: { b: "x", _: "y" } }` → `"a.b" | "a"`. */
type TreePaths<T, P extends string = ""> = T extends string
  ? P
  : { [K in keyof T & string]: TreePaths<T[K], K extends "_" ? P : P extends "" ? K : `${P}.${K}`> }[keyof T & string];

/** 문구 나무를 점 표기 키 표로 편다. 이름이 `_`인 값은 부모 키가 된다. */
export function flattenMessageTree(tree: MessageTree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(tree)) {
    const path = key === "_" ? prefix : prefix === "" ? key : `${prefix}.${key}`;
    if (typeof value === "string") out[path] = value;
    else Object.assign(out, flattenMessageTree(value, path));
  }
  return out;
}

export type MarkdownDocMessageKey = TreePaths<typeof ko>;

/**
 * 문구 표. 앱이 `messages` prop으로 일부만 덮어쓴다(번역·용어 바꾸기).
 * `source.<출처>` 같은 키는 열린 문자열 계약 값에 붙이는 선택 문구이고, 표에 없으면 값 원문을 보인다.
 * 한국어 기본 문구 표는 `locales/ko.json`을 편 것이다(점 표기 키를 나무로 편 모양, 한 키가 다른 키의 앞부분이면 값을 `_`에 둔다).
 */
export const defaultMessages = flattenMessageTree(ko) as Readonly<Record<MarkdownDocMessageKey, string>>;

/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type MarkdownDocMessages = { [K in MarkdownDocMessageKey]: string } & Readonly<Record<string, string>>;

/** 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다. */
export function formatMessage(template: string, vars: Readonly<Record<string, string | number>> = {}): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Readonly<Record<string, string>>): MarkdownDocMessages {
  return partial ? ({ ...defaultMessages, ...partial } as MarkdownDocMessages) : (defaultMessages as MarkdownDocMessages);
}

/** 키로 문구를 찾는다. 없으면 `fallback`(보통 모르는 계약 어휘 원문). */
export function messageOr(messages: Readonly<Record<string, string>>, key: string, fallback: string): string {
  return messages[key] ?? fallback;
}
