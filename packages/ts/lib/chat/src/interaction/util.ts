import type { KeyboardEvent } from "react";

/** 입력 요소(텍스트 입력·textarea·선택·편집 가능)에서 난 이벤트인지. 단축키를 건너뛰는 데 쓴다. */
export function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") return !["checkbox", "radio", "button"].includes((el as HTMLInputElement).type);
  return el.isContentEditable === true;
}

/** Ctrl/Cmd+Enter이면 `action`을 실행한다. IME 조합 중에는 무시. */
export function onModEnter(e: KeyboardEvent, action: () => void): void {
  if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
  const ne = e.nativeEvent as { isComposing?: boolean };
  if (ne.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  action();
}

export function str(v: unknown): string | undefined {
  return typeof v === "string" && v !== "" ? v : undefined;
}

export function prettyJson(v: unknown): string {
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2) ?? "";
  } catch {
    return String(v);
  }
}

/** JSON 문자열 파싱. 실패하면 `undefined`가 아니라 `{ok:false}`. */
export function parseJson(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}
