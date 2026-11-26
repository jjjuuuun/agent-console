import { flattenMessageTree, formatMessage, messageOr } from "@agent-console/markdown-doc";
import ko from "./locales/ko.json";

export { formatMessage, messageOr };

/** 나무의 경로 문자열 합집합: `{ a: { b: "x", _: "y" } }` → `"a.b" | "a"`. */
type TreePaths<T, P extends string = ""> = T extends string
  ? P
  : { [K in keyof T & string]: TreePaths<T[K], K extends "_" ? P : P extends "" ? K : `${P}.${K}`> }[keyof T & string];

export type SddViewMessageKey = TreePaths<typeof ko>;

/**
 * 문구 표. 앱이 `messages` prop으로 일부만 덮어쓴다(번역·용어 바꾸기).
 * 상태 이름·문서 종류 이름·단계 이름은 여기에 없다 — 전부 서버 데이터(`label`·`title`)다.
 * `gap.<코드>`·`source.<출처>` 같은 키는 열린 문자열 계약 값에 붙이는 선택 문구이고, 표에 없으면 값 원문을 보인다.
 * 한국어 기본 문구 표는 `locales/ko.json`을 편 것이다(점 표기 키를 나무로 편 모양, 한 키가 다른 키의 앞부분이면 값을 `_`에 둔다).
 */
export const defaultMessages = flattenMessageTree(ko) as Readonly<Record<SddViewMessageKey, string>>;

/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type SddViewMessages = { [K in SddViewMessageKey]: string } & Readonly<Record<string, string>>;

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Readonly<Record<string, string>>): SddViewMessages {
  return partial ? ({ ...defaultMessages, ...partial } as SddViewMessages) : (defaultMessages as SddViewMessages);
}
