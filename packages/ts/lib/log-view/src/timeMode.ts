import { fullTimeTitle } from "./format";
import type { Formatters } from "./types";

/**
 * 이벤트 시각 열의 표시 방식.
 * - `datetime`: 기록된 실제 시각(날짜 포함, 브라우저 시간대)
 * - `time`: 기록된 실제 시각(시각만)
 * - `elapsed`: 기준 시각(세션 시작 등)에서 지난 시간
 */
export type TimeMode = "datetime" | "time" | "elapsed";

/** 메뉴에 보일 순서. */
export const TIME_MODES: readonly TimeMode[] = ["datetime", "time", "elapsed"];

/** 모르는 값(저장소에서 읽은 문자열)이면 `fallback`. */
export function parseTimeMode(value: string | null | undefined, fallback: TimeMode = "datetime"): TimeMode {
  return value === "datetime" || value === "time" || value === "elapsed" ? value : fallback;
}

/** 시각 열 폭(px, 머리 메뉴 단추 포함). 모드마다 글자 수가 달라 열 폭도 바뀐다. */
export function timeColumnWidth(mode: TimeMode): number {
  return mode === "datetime" ? 176 : 124;
}

export interface EventTimeText {
  text: string;
  /** 툴팁: 지역 시각 + 시간대 + ISO 원문 */
  title: string;
}

/**
 * 이벤트 시각 한 칸의 글자. 기록된 시각(`epochSeconds`)이 없으면 null이다 — 경과 시각 등으로 대신하지 않는다.
 * `elapsed`에서 기준 시각(`origin`)이 없으면 null.
 */
export function formatEventTime(mode: TimeMode, epochSeconds: number | null | undefined, origin: number | null | undefined, formatters: Pick<Formatters, "absoluteTime" | "dateTime" | "relativeTime">): EventTimeText | null {
  if (epochSeconds == null) return null;
  if (mode === "elapsed" && origin == null) return null;
  const text = mode === "datetime" ? formatters.dateTime(epochSeconds) : mode === "time" ? formatters.absoluteTime(epochSeconds) : formatters.relativeTime((epochSeconds - (origin as number)) * 1000);
  return { text, title: fullTimeTitle(epochSeconds) };
}
