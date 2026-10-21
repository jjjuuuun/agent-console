/** 부분 messages를 기본 문구에 덮어 합친다. */
export function mergeMessages<T extends object>(defaults: T, partial?: Partial<T>): T {
  return partial ? { ...defaults, ...stripUndefined(partial) } : defaults;
}

function stripUndefined<T extends object>(o: Partial<T>): Partial<T> {
  const out: Partial<T> = {};
  for (const k of Object.keys(o) as (keyof T)[]) if (o[k] !== undefined) out[k] = o[k];
  return out;
}

/** `{n}` 같은 자리표시자를 값으로 바꾼다. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in values ? String(values[k]) : m));
}

/** 초 단위 길이를 "12초", "2분 5초", "1시간 3분"으로. */
export function formatSeconds(totalSeconds: number, units = { s: "초", m: "분", h: "시간" }): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s < 60) return `${s}${units.s}`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}${units.m} ${s % 60}${units.s}` : `${m}${units.m}`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}${units.h} ${m % 60}${units.m}` : `${h}${units.h}`;
}

/** 남은 시간 카운트다운 "4:48". */
export function formatCountdown(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 문자열 → 32비트 FNV-1a 해시. 에이전트 아바타 색 번호에 쓴다. */
export function fnv1a32(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/** 에이전트 id → 분류색 번호 1..8 (`--ac-cat-N`). */
export function avatarColorIndex(agentId: string): number {
  return (fnv1a32(agentId) % 8) + 1;
}

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** 거짓 값을 걸러 클래스 문자열을 만든다. */
export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * 소요 시간 표시 규칙: 1초 미만이거나 값이 없으면 `null`(의미 없는 "0초"를 그리지 않는다), 아니면 `formatSeconds` 문자열.
 * @param ms 밀리초. 없으면 null.
 */
export function showDuration(ms: number | null | undefined, units?: { s: string; m: string; h: string }): string | null {
  if (ms == null || !Number.isFinite(ms) || ms < 1000) return null;
  return formatSeconds(ms / 1000, units);
}
