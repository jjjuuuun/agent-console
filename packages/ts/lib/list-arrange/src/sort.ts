import type { GroupByDef, SortDef, Usable } from "./types";

/** 로케일 문자열 비교기(숫자는 자연 정렬). */
export function textCompare(locale = "ko"): (a: string, b: string) => number {
  const collator = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  return (a, b) => collator.compare(a, b);
}

/** 문자열 필드(읽기 함수)로 비교하는 `compare`를 만든다. */
export function byText<T>(read: (item: T) => string, locale = "ko"): (a: T, b: T) => number {
  const cmp = textCompare(locale);
  return (a, b) => cmp(read(a), read(b));
}

/** 숫자 필드 비교(내림차순이면 `desc`). 없는 값은 맨 뒤. */
export function byNumber<T>(read: (item: T) => number | undefined, desc = false): (a: T, b: T) => number {
  return (a, b) => {
    const x = read(a);
    const y = read(b);
    if (x === undefined && y === undefined) return 0;
    if (x === undefined) return 1;
    if (y === undefined) return -1;
    return desc ? y - x : x - y;
  };
}

/** 새 배열을 안정 정렬해 돌려준다(입력은 바꾸지 않음). */
export function sortItems<T>(items: readonly T[], by: SortDef<T> | ((a: T, b: T) => number)): T[] {
  const compare = typeof by === "function" ? by : by.compare;
  return items.map((item, index) => ({ item, index })).sort((a, b) => compare(a.item, b.item) || a.index - b.index).map((e) => e.item);
}

/** 쓸 수 있는 정렬만 남긴다. */
export function availableSorts<T>(defs: readonly SortDef<T>[], items: readonly T[]): SortDef<T>[] {
  return defs.filter((d) => d.available?.(items) ?? true);
}

/** 선택 id가 쓸 수 없으면 첫 번째 쓸 수 있는 정렬로 되돌린다. 하나도 없으면 undefined. */
export function resolveSort<T>(defs: readonly SortDef<T>[], id: string | undefined, items: readonly T[]): SortDef<T> | undefined {
  const usable = availableSorts(defs, items);
  return usable.find((d) => d.id === id) ?? usable[0];
}

/** 기준의 사용 가능 여부. `usable`이 없으면 항상 가능. */
export function checkUsable<T>(def: GroupByDef<T>, items: readonly T[]): Usable {
  return def.usable?.(items) ?? { ok: true };
}

/**
 * `usable` 구현 도우미: 값을 가진 항목이 2개 이상인데 값이 모두 다르면(묶음이 항목 수만큼 생김) 불가.
 * @param reason 불가 사유(호출자 문구)
 */
export function usableUnlessAllDistinct<T>(read: (item: T) => readonly string[], reason: string): (items: readonly T[]) => Usable {
  return (items) => {
    const values = items.flatMap((item) => read(item).map((v) => v.trim()).filter((v) => v !== ""));
    if (values.length < 2) return { ok: true };
    return new Set(values).size === values.length ? { ok: false, reason } : { ok: true };
  };
}

/** 선택 id의 기준을 돌려준다. 없거나 `usable`이 아니면 undefined("묶지 않음"으로 보이게; 저장값은 지우지 않는다). */
export function resolveGroupBy<T>(defs: readonly GroupByDef<T>[], id: string | undefined, items: readonly T[]): GroupByDef<T> | undefined {
  const def = defs.find((d) => d.id === id);
  return def !== undefined && checkUsable(def, items).ok ? def : undefined;
}
