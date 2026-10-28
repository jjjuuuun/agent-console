/**
 * 메모리 화면의 주소 상태(`/memory?scope=<kind>:<id>&entry=&q=&tag=&author_run=&author_kind=&archived=1&deleted=1&sort=&order=`).
 * 선택·필터가 주소에 있고 이 파일의 순수 함수만 읽고 쓴다. 모르는 인자(`prj` 등)는 그대로 보존한다.
 */
import type { MemoryScopeRef } from "@agent-console/contracts/memory";
import type { SortState } from "@agent-console/memory-view";
import { DEFAULT_SORT, ENTRY_SORTS, MEMORY_PARAMS as P } from "./memoryConfig";

export interface MemoryViewState {
  scope: MemoryScopeRef | null;
  entry: string | null;
  q: string;
  tag: string | null;
  authorRun: string | null;
  authorKind: string | null;
  includeArchived: boolean;
  includeDeleted: boolean;
  /** 사용자가 고른 정렬. null = 서버 기본 순서 */
  sort: SortState | null;
}

export const EMPTY_VIEW: MemoryViewState = {
  scope: null, entry: null, q: "", tag: null, authorRun: null, authorKind: null, includeArchived: false, includeDeleted: false, sort: null,
};

/** `<종류>:<id>` → 범위. 첫 콜론으로 나눈다(id에 콜론이 있어도 된다). 콜론이 없거나 종류가 비면 null. */
export function parseScopeParam(text: string | null): MemoryScopeRef | null {
  if (text === null) return null;
  const at = text.indexOf(":");
  if (at <= 0) return null;
  return { kind: text.slice(0, at), id: text.slice(at + 1) };
}

export function scopeParam(scope: MemoryScopeRef): string {
  return `${scope.kind}:${scope.id ?? ""}`;
}

const orNull = (v: string | null): string | null => (v === null || v === "" ? null : v);

export function parseView(params: URLSearchParams): MemoryViewState {
  const sortKey = params.get(P.sort);
  const order = params.get(P.sortOrder);
  const sort: SortState | null = sortKey !== null && ENTRY_SORTS.includes(sortKey) ? { key: sortKey, order: order === "asc" ? "asc" : "desc" } : null;
  return {
    scope: parseScopeParam(params.get(P.scope)),
    entry: orNull(params.get(P.entry)),
    q: params.get(P.q) ?? "",
    tag: orNull(params.get(P.tag)),
    authorRun: orNull(params.get(P.authorRun)),
    authorKind: orNull(params.get(P.authorKind)),
    includeArchived: params.get(P.archived) === "1",
    includeDeleted: params.get(P.deleted) === "1",
    sort,
  };
}

/** 상태를 주소 인자에 반영한 새 인자(기본값은 생략하고, 모르는 인자는 그대로 둔다). */
export function writeView(base: URLSearchParams, view: MemoryViewState): URLSearchParams {
  const next = new URLSearchParams(base);
  const set = (name: string, value: string | null) => {
    if (value === null || value === "") next.delete(name);
    else next.set(name, value);
  };
  set(P.scope, view.scope === null ? null : scopeParam(view.scope));
  set(P.entry, view.entry);
  set(P.q, view.q.trim() === "" ? null : view.q);
  set(P.tag, view.tag);
  set(P.authorRun, view.authorRun);
  set(P.authorKind, view.authorKind);
  set(P.archived, view.includeArchived ? "1" : null);
  set(P.deleted, view.includeDeleted ? "1" : null);
  // 기본 정렬(수정 내림차순)과 같게 고른 값도 "고른 값"이라 그대로 쓴다(서버 기본과 구분: 아무것도 안 고르면 sort 인자 없음)
  set(P.sort, view.sort?.key ?? null);
  set(P.sortOrder, view.sort === null ? null : view.sort.order);
  return next;
}

/** 서버 질의에 보낼 정렬 인자(고르지 않았으면 둘 다 없음). */
export function sortParams(sort: SortState | null): { sort?: string; order?: "asc" | "desc" } {
  return sort === null ? {} : { sort: sort.key, order: sort.order };
}

/** 필터(검색어·태그·쓴 주체·보관/지움 포함)가 하나라도 있는가. 범위·선택 항목·정렬은 필터가 아니다. */
export function hasFilters(view: MemoryViewState): boolean {
  return view.q.trim() !== "" || view.tag !== null || view.authorRun !== null || view.authorKind !== null || view.includeArchived || view.includeDeleted;
}

/** 정렬 상태가 서버 기본(수정 내림차순)과 같은가. */
export function isDefaultSort(sort: SortState | null): boolean {
  return sort === null || (sort.key === DEFAULT_SORT && sort.order === "desc");
}
