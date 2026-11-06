/** 강조 범위(UTF-16 오프셋) → 조각 나누기. 서로게이트 쌍 한가운데를 자르지 않는다. */
import type { WikiTextRange } from "@agent-console/contracts/wiki";

export interface TextSegment {
  text: string;
  marked: boolean;
}

function isHigh(c: number): boolean {
  return c >= 0xd800 && c <= 0xdbff;
}
function isLow(c: number): boolean {
  return c >= 0xdc00 && c <= 0xdfff;
}

/**
 * `text`를 강조 범위 기준으로 나눈다. 범위는 본문 길이로 자르고, 빈 범위·역순은 버리고, 겹치는 범위는 합친다.
 * 경계가 서로게이트 쌍(이모지 등) 안이면 쌍 전체가 들어가게 넓힌다.
 */
export function splitByMarks(text: string, marks: readonly WikiTextRange[] | undefined): TextSegment[] {
  const ranges: Array<[number, number]> = [];
  for (const m of marks ?? []) {
    if (!Number.isInteger(m.start) || !Number.isInteger(m.end)) continue;
    let s = Math.max(0, m.start);
    let e = Math.min(text.length, m.end);
    if (e <= s) continue;
    if (s > 0 && isLow(text.charCodeAt(s)) && isHigh(text.charCodeAt(s - 1))) s -= 1;
    if (e < text.length && isLow(text.charCodeAt(e)) && isHigh(text.charCodeAt(e - 1))) e += 1;
    ranges.push([s, e]);
  }
  ranges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged: Array<[number, number]> = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  const out: TextSegment[] = [];
  let at = 0;
  for (const [s, e] of merged) {
    if (s > at) out.push({ text: text.slice(at, s), marked: false });
    out.push({ text: text.slice(s, e), marked: true });
    at = e;
  }
  if (at < text.length) out.push({ text: text.slice(at), marked: false });
  return out;
}
