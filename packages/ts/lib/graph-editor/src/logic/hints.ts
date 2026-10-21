/** ui_hints 해석. 해석할 수 없는 값은 undefined → 호출자가 기본 표시로 돌아간다. */

const HEX = /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const FUNC = /^(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch)\(\s*[\d\s.,%/+-]+(?:deg|turn|rad)?[\d\s.,%/+-]*\)$/i;
const VAR = /^var\(--[A-Za-z0-9_-]+\)$/;
const NAMED = /^[a-z]{3,24}$/i;

/** 안전한 CSS 색 문자열만 통과시킨다(스타일 주입 방지). 아니면 undefined. */
export function safeCssColor(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const v = value.trim();
  if (v === "" || v.length > 64) return undefined;
  if (HEX.test(v) || FUNC.test(v) || VAR.test(v) || NAMED.test(v)) return v;
  return undefined;
}

/** 문자열을 사용자 인식 글자(grapheme) 배열로 나눈다. */
export function graphemes(text: string): string[] {
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    return Array.from(seg.segment(text), (s) => s.segment);
  }
  return Array.from(text);
}

/** 제목 첫 글자 아바타(영문은 대문자). 비었으면 "?". */
export function firstGlyph(title: string): string {
  const first = graphemes(title.trim())[0];
  return first === undefined ? "?" : first.toLocaleUpperCase();
}

/** ui_hints.icon이 1~2자 아바타 텍스트면 그대로, 아니면 undefined. */
export function safeIconText(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const v = value.trim();
  if (v === "") return undefined;
  return graphemes(v).length <= 2 ? v : undefined;
}

export interface ResolvedHints {
  iconText: string;
  /** 디스크립터가 준 유효한 색. 없으면 undefined(분류색 사용). */
  color: string | undefined;
  dashed: boolean;
}

/** 디스크립터(노드/엣지)의 ui_hints → 표시 값. 제목 첫 글자 폴백 포함. */
export function resolveHints(
  hints: { icon?: unknown; color?: unknown; dashed?: unknown } | null | undefined,
  title: string,
): ResolvedHints {
  return {
    iconText: safeIconText(hints?.icon) ?? firstGlyph(title),
    color: safeCssColor(hints?.color),
    dashed: hints?.dashed === true,
  };
}
