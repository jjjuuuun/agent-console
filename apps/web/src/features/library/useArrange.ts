import { useEffect, useMemo, useRef, useState } from "react";
import {
  groupItems, groupKeysOf, hasNamedGroups, loadCollapsed, loadViewState, resolveGroupBy, resolveSort, revealGroup, saveCollapsed, saveViewState, sortItems, uniqueCount, visibleGroups,
  type GroupByDef, type GroupNode, type KeyValueStorage, type SortDef, type ViewState,
} from "@agent-console/list-arrange";

export interface ArrangeOptions<T> {
  /** 보기·접힘 저장 키 접두(`ac.list.*.<listId>`) */
  listId: string;
  items: readonly T[];
  /** 묶는 기준 후보(데이터). `attribute` 같은 키 입력 기준은 호출자가 `attrKey`를 읽어 만든다. */
  groupDefs: readonly GroupByDef<T>[];
  sortDefs: readonly SortDef<T>[];
  /** 저장소(보통 localStorage). 없으면 기억하지 않는다. */
  storage?: KeyValueStorage | undefined;
  /** 처음 보기(저장값이 없을 때) */
  defaultView: Required<Pick<ViewState, "groupBy" | "sort">>;
  /** 검색 중이면 접힘을 무시하고 모두 펼친다(저장은 하지 않음). */
  searching: boolean;
  /** 선택 항목 id: 접힌 묶음 안에 있으면 그 묶음을 펼친다. */
  selectedId?: string | undefined;
  idOf: (item: T) => string;
}

export interface Arranged<T> {
  view: ViewState;
  setView: (patch: Partial<ViewState>) => void;
  /** 쓸 수 있는 기준(`usable`)을 반영한 현재 기준. 없으면 묶지 않음. */
  groupDef: GroupByDef<T> | undefined;
  sortDef: SortDef<T> | undefined;
  /** 정렬된 평면 목록(묶음 아닐 때·머리 없을 때 이것을 그린다) */
  sorted: T[];
  /** 접힘을 반영해 화면에 보일 묶음(평면이면 undefined) */
  groups: (GroupNode<T> & { collapsed: boolean })[] | undefined;
  collapsed: ReadonlySet<string>;
  toggle: (key: string, collapsed: boolean) => void;
  collapseAll: () => void;
  expandAll: () => void;
  /** 중복 없는 항목 수 */
  total: number;
}

/**
 * 목록 묶기·정렬·접힘 상태(보기 선택과 접힌 묶음은 저장소에 기억). 화면 종류를 모른다.
 * 묶음이 없으면(폴더 값이 하나도 없는 등) `groups`가 undefined라 평면으로 그리면 된다.
 */
export function useArrange<T>(o: ArrangeOptions<T>): Arranged<T> {
  const { listId, items, groupDefs, sortDefs, storage, defaultView, searching, selectedId, idOf } = o;
  const [view, setViewState] = useState<ViewState>(() => loadViewState(storage, listId, defaultView));
  const groupId = view.groupBy ?? defaultView.groupBy;
  const [collapsedSaved, setCollapsed] = useState<Set<string>>(() => loadCollapsed(storage, listId, groupId));
  const loadedFor = useRef(groupId);
  useEffect(() => {
    if (loadedFor.current === groupId) return;
    loadedFor.current = groupId;
    setCollapsed(loadCollapsed(storage, listId, groupId));
  }, [groupId, listId, storage]);

  const groupDef = useMemo(() => resolveGroupBy(groupDefs, groupId, items), [groupDefs, groupId, items]);
  const sortDef = useMemo(() => resolveSort(sortDefs, view.sort, items), [sortDefs, view.sort, items]);
  const sorted = useMemo(() => (sortDef === undefined ? [...items] : sortItems(items, sortDef)), [items, sortDef]);
  const nodes = useMemo(() => (groupDef === undefined ? [] : groupItems(sorted, groupDef)), [groupDef, sorted]);
  const named = groupDef !== undefined && hasNamedGroups(nodes);
  const collapsed = useMemo<ReadonlySet<string>>(() => (searching ? new Set<string>() : collapsedSaved), [searching, collapsedSaved]);

  const persist = (next: Set<string>) => {
    setCollapsed(next);
    saveCollapsed(storage, listId, groupId, next);
  };
  const setView = (patch: Partial<ViewState>) => {
    const next = { ...view, ...patch };
    setViewState(next);
    saveViewState(storage, listId, next);
  };

  // 선택이 바뀌면 그 항목이 든 접힌 묶음을 편다(접기 자체를 막지 않도록 선택이 바뀔 때만).
  const latest = useRef({ nodes, collapsedSaved, named });
  useEffect(() => {
    latest.current = { nodes, collapsedSaved, named };
  });
  useEffect(() => {
    if (selectedId === undefined) return;
    const { nodes: ns, collapsedSaved: cs, named: has } = latest.current;
    if (!has || cs.size === 0) return;
    let next: Set<string> = new Set(cs);
    for (const key of groupKeysOf(ns, (it) => idOf(it) === selectedId)) next = revealGroup(next, key);
    if (next.size !== cs.size) persist(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, groupId]);

  const groups = named
    ? visibleGroups(nodes, collapsed).map((g) => ({ ...g, collapsed: collapsed.has(g.key) }))
    : undefined;
  const keys = nodes.map((n) => n.key);
  return {
    view: { ...view, groupBy: groupId },
    setView,
    groupDef,
    sortDef,
    sorted,
    groups,
    collapsed,
    toggle: (key, c) => {
      const next = new Set(collapsedSaved);
      if (c) next.add(key);
      else next.delete(key);
      persist(next);
    },
    collapseAll: () => persist(new Set(keys)),
    expandAll: () => persist(new Set()),
    total: groups === undefined ? items.length : uniqueCount(nodes),
  };
}
