import { useMemo, useState, type ReactNode } from "react";
import { checkUsable, loadViewState, type GroupByDef, type KeyValueStorage, type SortDef } from "@agent-console/list-arrange";
import { ListViewMenu, type ListViewOption } from "@agent-console/ui";
import { useArrange, type Arranged } from "./useArrange";
import type { ArrangeMessages } from "./arrangeMessages";

/** "묶지 않음"을 뜻하는 저장 id. */
export const GROUP_NONE = "none";
/** 속성 키로 묶는 기준 id(키는 보기 상태의 `attrKey`). */
export const GROUP_ATTRIBUTE = "attribute";

/** 브라우저 저장소(없거나 막히면 undefined → 기억하지 않음). */
export const browserStorage = (): KeyValueStorage | undefined => {
  try {
    return typeof localStorage === "undefined" ? undefined : localStorage;
  } catch {
    return undefined;
  }
};

export interface ListViewOptions<T> {
  /** 저장 키 접두(`ac.list.*.<listId>`) */
  listId: string;
  items: readonly T[];
  /** 묶는 기준(데이터). 속성 키 기준이 있으면 현재 키를 받아 만든다. */
  groupDefs: readonly GroupByDef<T>[] | ((attrKey: string) => readonly GroupByDef<T>[]);
  sortDefs: readonly SortDef<T>[];
  defaultView: { groupBy: string; sort: string };
  messages: Pick<ArrangeMessages, "viewLabel" | "groupTitle" | "sortTitle" | "collapseAll" | "expandAll" | "none" | "groupNames" | "summaryGroup" | "noneLabels" | "sortNames" | "sortSummaries" | "attrKey" | "attrKeyPlaceholder">;
  searching: boolean;
  selectedId?: string | undefined;
  idOf: (item: T) => string;
  /** 보기 단추를 그릴지(목록이 비었거나 로딩 중이면 false) */
  showMenu: boolean;
  /** 속성 키 기준의 자동완성 후보 */
  attributeKeys?: readonly string[];
  /** 묶음 머리에 보일 이름을 바꾼다(예: 종류 id → 종류 제목). 없으면 묶음 값 그대로. */
  groupLabel?: (groupId: string, key: string, name: string) => string;
}

export interface ListView<T> {
  arranged: Arranged<T>;
  /** 보기 단추(`ListPane`의 `belowTop` 등에 끼운다). 그릴 필요가 없으면 null */
  menu: ReactNode;
  openMenu: () => void;
  /** 묶음 머리의 "없음" 묶음 이름 */
  noneLabel: string;
  /** `ListPane`의 `groups` 입력. 평면이면 undefined */
  paneGroups:
    | { key: string; label: string; title?: string; count: number; depth: number; collapsed: boolean; items: T[] }[]
    | undefined;
  /** 현재 기준 id(`GROUP_NONE` 포함) */
  groupId: string;
}

/**
 * 목록 "보기"(묶는 기준·정렬·접기) 연결 훅: `useArrange` + `ListViewMenu` 옵션 조립. 에이전트·팀·리소스 목록이 함께 쓴다(5.2R.63).
 * 기준·정렬 이름은 `messages`의 표에서 `titleKey`로 찾으므로 화면 코드에 필드명 분기가 없다.
 */
export function useListView<T>(o: ListViewOptions<T>): ListView<T> {
  const { listId, items, sortDefs, defaultView, messages: m, searching, selectedId, idOf, showMenu, attributeKeys, groupLabel } = o;
  const storage = useMemo(() => browserStorage(), []);
  const [open, setOpen] = useState(false);
  const [attr, setAttr] = useState(() => loadViewState(storage, listId).attrKey ?? "");
  const { groupDefs: gd } = o;
  const groupDefs = useMemo(() => (typeof gd === "function" ? gd(attr) : gd), [gd, attr]);
  const arranged = useArrange<T>({ listId, items, groupDefs, sortDefs, storage, defaultView, searching, selectedId, idOf });

  const groupName = (k: string) => m.groupNames[k] ?? k;
  const sortName = (k: string) => m.sortNames[k] ?? k;
  const groupOptions: ListViewOption[] = [
    { id: GROUP_NONE, label: m.none },
    ...groupDefs.map((d): ListViewOption => {
      const u = checkUsable(d, items);
      return {
        id: d.id,
        label: groupName(d.titleKey),
        ...(u.ok ? {} : { disabled: true, ...(u.reason === undefined ? {} : { reason: u.reason }) }),
        ...(d.id === GROUP_ATTRIBUTE
          ? { input: { label: m.attrKey, placeholder: m.attrKeyPlaceholder, value: attr, suggestions: [...(attributeKeys ?? [])], onChange: (v: string) => { setAttr(v); arranged.setView({ attrKey: v }); } } }
          : {}),
      };
    }),
  ];
  const sortOptions: ListViewOption[] = sortDefs.filter((d) => d.available?.(items) ?? true).map((d) => ({ id: d.id, label: sortName(d.titleKey) }));
  const groupSummary = arranged.groupDef === undefined ? m.none : m.summaryGroup(arranged.groupDef.id === GROUP_ATTRIBUTE && attr.trim() !== "" ? attr.trim() : groupName(arranged.groupDef.titleKey));
  const summary = `${groupSummary} · ${arranged.sortDef === undefined ? "" : (m.sortSummaries[arranged.sortDef.titleKey] ?? sortName(arranged.sortDef.titleKey))}`;
  const noneLabel = m.noneLabels[arranged.groupDef?.titleKey ?? ""] ?? "";

  const menu = !showMenu ? null : (
    <div className="lib-list-view">
      <ListViewMenu
        summary={summary}
        groupOptions={groupOptions}
        groupBy={arranged.groupDef?.id ?? GROUP_NONE}
        onGroupByChange={(id) => arranged.setView({ groupBy: id })}
        sortOptions={sortOptions}
        sort={arranged.sortDef?.id ?? ""}
        onSortChange={(id) => arranged.setView({ sort: id })}
        {...(arranged.groups === undefined ? {} : { onCollapseAll: arranged.collapseAll, onExpandAll: arranged.expandAll })}
        anyCollapsed={arranged.collapsed.size > 0}
        open={open}
        onOpenChange={setOpen}
        messages={{ menuLabel: m.viewLabel, groupTitle: m.groupTitle, sortTitle: m.sortTitle, collapseAll: m.collapseAll, expandAll: m.expandAll }}
      />
    </div>
  );
  const paneGroups = arranged.groups?.map((g) => ({ key: g.key, label: g.none ? noneLabel : (groupLabel?.(arranged.groupDef?.id ?? GROUP_NONE, g.key, g.name) ?? g.name), ...(g.none ? {} : { title: g.key }), count: g.count, depth: g.depth, collapsed: g.collapsed, items: g.items }));
  return { arranged, menu, openMenu: () => setOpen(true), noneLabel, paneGroups, groupId: arranged.groupDef?.id ?? GROUP_NONE };
}
