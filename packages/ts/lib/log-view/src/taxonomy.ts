import type { LogEvent, LogTaxonomy } from "@agent-console/contracts/logs";
import type { LogTaxonomyView, SlotFor, TaxonomyEntry } from "./types";

/** 분류 체계 `color`로 인정하는 슬롯 토큰(`tokens.md` 1.5): `cat-1`~`cat-8`, `neutral`. */
const COLOR_TOKEN = /^(cat-[1-8]|neutral)$/;

/** 계약 `LogTaxonomy`(없어도 됨)를 화면용 조회 객체로 바꾼다. 없는 id도 이름 = id로 돌려준다. */
export function toTaxonomyView(taxonomy?: LogTaxonomy | null): LogTaxonomyView {
  const categories = taxonomy?.categories ?? {};
  const known = Object.keys(categories);
  const order: string[] = [];
  const seen = new Set<string>();
  for (const id of taxonomy?.order ?? []) {
    if (id in categories && !seen.has(id)) {
      order.push(id);
      seen.add(id);
    }
  }
  for (const id of known.filter((k) => !seen.has(k)).sort()) order.push(id);
  const get = (id: string): TaxonomyEntry => {
    const c = Object.prototype.hasOwnProperty.call(categories, id) ? categories[id] : undefined;
    if (!c) return { id, name: id, visible: true };
    const entry: TaxonomyEntry = { id, name: c.label?.trim() ? c.label : id, visible: c.visible !== false };
    if (c.color) entry.color = c.color;
    if (c.tone) entry.tone = c.tone;
    if (c.description) entry.description = c.description;
    return entry;
  };
  return { order, get, has: (id) => Object.prototype.hasOwnProperty.call(categories, id) };
}

/**
 * 오류 이벤트 판정(한 곳). 이벤트 범주와 태그 중 하나라도 분류 체계 항목의 `tone === "danger"`이면 오류다.
 * 범주 이름 비교나 `status` 기준 경로는 없다(F-25). 분류 체계가 비면 오류 표시도 없다.
 */
export function isErrorEvent(event: Pick<LogEvent, "category" | "tags">, taxonomy: LogTaxonomyView): boolean {
  const ids = [event.category, ...(event.tags ?? [])];
  return ids.some((id) => taxonomy.has(id) && taxonomy.get(id).tone === "danger");
}

/** 칩 점·레인 틱·차트 계열 색(CSS 값). 분류 체계 색 토큰이 있으면 그것, 없으면 해시 슬롯. */
export function colorFor(key: string, taxonomy: LogTaxonomyView | undefined, slotFor: SlotFor): string {
  const token = taxonomy?.has(key) ? taxonomy.get(key).color : undefined;
  if (token && COLOR_TOKEN.test(token)) return token === "neutral" ? "var(--ac-text-muted)" : `var(--ac-${token})`;
  return slotColor(slotFor(key));
}

/** 슬롯 번호(0~7)를 `--ac-cat-N` 색으로. 범위 밖은 나머지로 접는다. */
export function slotColor(slot: number): string {
  const n = ((Math.trunc(slot) % 8) + 8) % 8;
  return `var(--ac-cat-${n + 1})`;
}

/** 이벤트 목록에서 범주별 개수. 분류 체계 `visible=false`는 `includeHidden`일 때만. */
export function countCategories(events: readonly Pick<LogEvent, "category">[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const e of events) out.set(e.category, (out.get(e.category) ?? 0) + 1);
  return out;
}

export interface CategoryItem {
  id: string;
  count: number;
  total?: number;
}

/** 칩 순서: 분류 체계 순서에 있는 범주 먼저, 나머지는 개수 내림차순(동률은 id 사전순). 개수는 `total`(세션 전체)이 있으면 그것. */
export function orderCategories<T extends { id: string; count: number; total?: number }>(items: readonly T[], taxonomy: LogTaxonomyView): T[] {
  const size = (i: T) => i.total ?? i.count;
  const pos = new Map(taxonomy.order.map((id, i) => [id, i] as const));
  const inTax = items.filter((i) => pos.has(i.id)).sort((a, b) => (pos.get(a.id) ?? 0) - (pos.get(b.id) ?? 0));
  const rest = items.filter((i) => !pos.has(i.id)).sort((a, b) => size(b) - size(a) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return [...inTax, ...rest];
}

/** 분류 체계에서 `visible=false`인 범주의 이벤트인지(기본 표에서 숨기는 대상). 분류 체계에 없는 범주는 보인다. */
export function isHiddenEvent(event: Pick<LogEvent, "category">, taxonomy: LogTaxonomyView): boolean {
  return taxonomy.has(event.category) && !taxonomy.get(event.category).visible;
}
