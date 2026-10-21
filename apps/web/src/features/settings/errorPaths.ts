import type { FormError } from "@agent-console/schema-form";

/** 서버 422의 문서 기준 경로(`/usage/sources/0/config/x`) 중 `prefix` 아래만 골라 경로를 폼 값 기준(`/x`)으로 바꾼다. */
export function errorsUnder(errors: readonly FormError[] | undefined, prefix: string): FormError[] {
  if (errors === undefined) return [];
  return errors.filter((e) => e.path === prefix || e.path.startsWith(`${prefix}/`)).map((e) => ({ ...e, path: e.path.slice(prefix.length) }));
}

/** `prefix` 자체(폼 안쪽 필드가 아닌 항목 전체)에 붙은 오류 메시지. */
export function messagesAt(errors: readonly FormError[] | undefined, prefix: string): string[] {
  return (errors ?? []).filter((e) => e.path === prefix).map((e) => e.message);
}
