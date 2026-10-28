import type { Formatters } from "./types";

const pad = (n: number, w = 2) => String(Math.trunc(n)).padStart(w, "0");

/** 상대 시각: `+1:23.456`, 1시간 이상이면 `+1:02:03.4`. 음수는 `-`. */
export function formatRelativeTime(ms: number): string {
  const sign = ms < 0 ? "-" : "+";
  const abs = Math.abs(ms);
  const totalSec = Math.floor(abs / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h >= 1) return `${sign}${h}:${pad(m)}:${pad(s)}.${Math.floor((abs % 1000) / 100)}`;
  return `${sign}${m}:${pad(s)}.${pad(abs % 1000, 3)}`;
}

/** 절대 시각(브라우저 로컬 시간대) `HH:mm:ss.SSS`. */
export function formatAbsoluteTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

/** 날짜 포함 절대 시각(브라우저 로컬 시간대) `YYYY-MM-DD HH:mm:ss`. */
export function formatDateTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return `${pad(d.getFullYear(), 4)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 소요 시간: `<1초` ms, `<60초` 소수 1자리 초, 그 외 `분 초`. */
export function formatDurationMs(ms: number, units = { ms: "ms", s: "초", m: "분" }): string {
  if (ms < 1000) return `${Math.round(ms)}${units.ms}`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}${units.s}`;
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}${units.m} ${pad(total % 60)}${units.s}`;
}

/** 토큰 약식: 1,000 미만은 그대로, `4.1k`, `1.2M`. */
export function formatTokensShort(n: number): string {
  const abs = Math.abs(n);
  if (abs < 1000) return String(n);
  if (abs < 1_000_000) return `${trim(n / 1000)}k`;
  return `${trim(n / 1_000_000)}M`;
}

function trim(v: number): string {
  const s = v.toFixed(1);
  return s.endsWith(".0") ? s.slice(0, -2) : s;
}

export function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

export const defaultFormatters: Formatters = {
  relativeTime: formatRelativeTime,
  absoluteTime: formatAbsoluteTime,
  dateTime: formatDateTime,
  duration: (ms) => formatDurationMs(ms),
  tokens: formatTokensShort,
  number: formatNumber,
};

export function mergeFormatters(partial?: Partial<Formatters>): Formatters {
  return partial ? { ...defaultFormatters, ...partial } : defaultFormatters;
}

/** 세션 id 등 긴 id의 앞 8자(전체 id는 툴팁으로). */
export function shortId(id: string, n = 8): string {
  return id.length > n ? id.slice(0, n) : id;
}

/** 경로 가운데 말줄임: 마지막 두 폴더(항목)를 우선 보인다. 구분자는 `/`와 `\`를 모두 본다. 절대 경로를 만들어 붙이지 않는다. */
export function shortPath(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  if (parts.length <= 3) return path;
  return `…/${parts.slice(-2).join("/")}`;
}

/** 브라우저 시간대 이름(예 `Asia/Seoul`). 알 수 없으면 빈 문자열. */
function zoneName(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  } catch {
    return "";
  }
}

/** epoch 초 -> 로컬 시각 전체 + 시간대 + ISO 원문(툴팁용). 예: `2026. 10. 28. 오전 11:42:07 Asia/Seoul (2026-10-28T02:42:07.000Z)` */
export function fullTimeTitle(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  const zone = zoneName();
  return `${d.toLocaleString()}${zone ? ` ${zone}` : ""} (${d.toISOString()})`;
}
