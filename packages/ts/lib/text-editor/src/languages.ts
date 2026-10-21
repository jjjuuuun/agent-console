import { html } from "@codemirror/lang-html";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import type { Extension } from "@codemirror/state";

/** 구문 강조 언어 이름. 모르는 값은 `text`로 취급한다. */
export type EditorLanguage = "markdown" | "html" | "json" | "text";

const factories: Readonly<Record<string, () => Extension>> = {
  markdown: () => markdown(),
  html: () => html(),
  json: () => json(),
};

/** 언어 이름 → CodeMirror 확장. 모르는 이름·`text`는 빈 확장. */
export function resolveLanguage(name: string | undefined): Extension {
  const make = name === undefined ? undefined : Object.hasOwn(factories, name) ? factories[name] : undefined;
  return make ? make() : [];
}

/** json 본문의 파싱 오류 메시지. 비어 있거나 유효하면 undefined. 편집을 막지 않는다. */
export function jsonParseError(text: string): string | undefined {
  if (text.trim() === "") return undefined;
  try {
    JSON.parse(text);
    return undefined;
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
}

/** UTF-8 바이트 길이. */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}
