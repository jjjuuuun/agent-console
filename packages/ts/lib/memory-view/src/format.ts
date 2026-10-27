import { formatMessage, type MemoryViewMessages } from "./messages";

const encoder = new TextEncoder();

/** UTF-8 바이트 수(문자 수가 아니다). 서버 한도와 같은 기준. */
export function utf8Bytes(text: string): number {
  return encoder.encode(text).length;
}

/** `1.2 KiB`처럼 사람이 읽는 크기. 1024 미만은 바이트. */
export function formatBytes(bytes: number, messages: Pick<MemoryViewMessages, "size.b" | "size.kib" | "size.mib">): string {
  const trim = (n: number) => n.toFixed(1).replace(/\.0$/, "");
  if (bytes < 1024) return formatMessage(messages["size.b"], { n: bytes });
  if (bytes < 1024 * 1024) return formatMessage(messages["size.kib"], { n: trim(bytes / 1024) });
  return formatMessage(messages["size.mib"], { n: trim(bytes / (1024 * 1024)) });
}

/** 버전 사이 크기 변화: `+40 B` / `−12 B` / `+0 B`. */
export function formatSizeDelta(delta: number): string {
  return `${delta < 0 ? "−" : "+"}${Math.abs(delta)} B`;
}

/** 상대 시각(`방금`·`3분 전`·`2일 전`). 30일이 넘으면 절대 시각. 시각은 Unix epoch 초. */
export function formatRelativeTime(at: number | null | undefined, now: number, messages: MemoryViewMessages): string {
  if (at === null || at === undefined) return messages["time.never"];
  const diff = Math.max(0, now - at);
  if (diff < 60) return messages["time.now"];
  if (diff < 3600) return formatMessage(messages["time.minutes"], { n: Math.floor(diff / 60) });
  if (diff < 86_400) return formatMessage(messages["time.hours"], { n: Math.floor(diff / 3600) });
  if (diff < 30 * 86_400) return formatMessage(messages["time.days"], { n: Math.floor(diff / 86_400) });
  return formatTimestamp(at);
}

const two = (n: number) => String(n).padStart(2, "0");

/** 절대 시각 `MM/DD HH:mm`(실행 환경의 시간대). */
export function formatTimestamp(at: number): string {
  const d = new Date(at * 1000);
  return `${two(d.getMonth() + 1)}/${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

/** 키 검사 결과 코드. 서버 검사(`memory.invalid_key`)가 최종이고 이것은 입력 중 안내용이다. */
export type KeyErrorCode = "empty" | "emptySegment" | "edgeSlash" | "dotSegment" | "control" | "tooLong";

/** 키 최대 길이(글자 수). 계약 `MemoryEntry.key` 설명과 같다. */
export const KEY_MAX_LENGTH = 256;

/** 키 글자 규칙: 빈 입력·256자 초과·제어 문자·앞뒤 `/`·빈 마디·`.`/`..` 마디. 문제가 없으면 null. */
export function validateKey(key: string): KeyErrorCode | null {
  if (key.length === 0) return "empty";
  if ([...key].length > KEY_MAX_LENGTH) return "tooLong";
  // eslint-disable-next-line no-control-regex -- 제어 문자 검사가 목적이다
  if (/[\u0000-\u001f\u007f]/.test(key)) return "control";
  if (key.startsWith("/") || key.endsWith("/")) return "edgeSlash";
  const parts = key.split("/");
  if (parts.some((p) => p === "")) return "emptySegment";
  if (parts.some((p) => p === "." || p === "..")) return "dotSegment";
  return null;
}

/** 키 오류 코드를 문구로. `tooLong`은 `{n}/256자`. */
export function keyErrorText(code: KeyErrorCode, key: string, messages: MemoryViewMessages): string {
  const text = messages[`key.error.${code}`] ?? code;
  return formatMessage(text, { n: [...key].length });
}

/**
 * `content_type`(열린 문자열)에서 text-editor의 언어 어휘를 정한다: 슬래시 뒤가 `markdown`·`html`·`json`(또는 `+json`)이면 그 언어, 그 밖은 `text`.
 * 이 대응은 편집기 언어 어휘일 뿐 범위·도구와 무관하다.
 */
export function languageForContentType(contentType: string | null | undefined): string {
  const tail = (contentType ?? "").split(";")[0]?.trim().toLowerCase().split("/")[1] ?? "";
  if (tail === "markdown") return "markdown";
  if (tail === "html") return "html";
  if (tail === "json" || tail.endsWith("+json")) return "json";
  return "text";
}

/** 문자열을 1..n 슬롯 번호로 고르게 나눈다(에이전트 아바타 색 `--ac-cat-N`). 같은 입력은 항상 같은 번호. */
export function hashSlot(text: string, slots: number): number {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (Math.imul(h, 31) + text.charCodeAt(i)) >>> 0;
  return (h % slots) + 1;
}

/** 비밀 거부(422)가 알려 주는 위치 필드. 계약 `MemorySecretRejectedDetails.field`의 세 값이 아니거나 null이면 null(위치를 빼고 일반 문구). */
export function secretRejectedField(field: unknown): "content" | "key" | "tags" | null {
  return field === "content" || field === "key" || field === "tags" ? field : null;
}

/** 정렬 상태: 서버 정렬 값(`MEMORY_ENTRY_SORTS` 중 하나)과 방향. null = 기본 순서. */
export interface SortState {
  key: string;
  order: "asc" | "desc";
}

/** 열 머리를 눌렀을 때 다음 정렬: 다른 열이면 desc → 같은 열 desc면 asc → asc면 기본(null). */
export function nextSort(current: SortState | null, key: string): SortState | null {
  if (current?.key !== key) return { key, order: "desc" };
  return current.order === "desc" ? { key, order: "asc" } : null;
}

/** 상태 줄 순서 문구. `sort`가 없으면 기본(최신순). 문구 표에 조합이 없으면 `sort.*` 라벨을 이어 쓴다. */
export function orderText(sort: SortState | null | undefined, messages: MemoryViewMessages): string {
  if (!sort) return messages["table.order.latest"];
  const direct = messages[`table.order.${sort.key}.${sort.order}`];
  if (direct) return direct;
  return formatMessage(messages["table.order.fallback"], { sort: messages[`sort.${sort.key}`] ?? sort.key, order: messages[`sort.${sort.order}`] ?? sort.order });
}
