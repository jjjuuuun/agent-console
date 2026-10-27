import type { LogSettings } from "@agent-console/contracts";

/** 객체에서 키를 지운 새 객체(값이 `undefined`로 남지 않게). */
export function without<T extends object>(obj: T, key: keyof T | string): T {
  const copy = { ...obj } as Record<string, unknown>;
  delete copy[key as string];
  return copy as T;
}

/** `logs` 설정을 부분 갱신한 새 `logs` 값(`undefined` 값은 키를 지운다). 다른 키(대시보드 등)는 그대로 둔다. */
export function patchLogs(logs: LogSettings | null | undefined, patch: Record<string, unknown>): LogSettings {
  const next: Record<string, unknown> = { ...(logs ?? {}) };
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined) delete next[k];
    else next[k] = v;
  }
  return next as LogSettings;
}

/** http/https만 링크로 쓴다(그 밖의 스킴은 텍스트). */
export function isHttpUrl(url: string | null | undefined): url is string {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}
