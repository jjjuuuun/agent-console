import { useMemo, type ReactNode } from "react";
import type { Scope } from "@agent-console/projects";
import { ScopeFilter, ProjectTag } from "./ScopeControls";
import { SelectMark, SelectionToolbar, useListSelection, useProjectMove, type ListSelection } from "./useProjectMove";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";

export interface ScopedListOptions<T> {
  /** 항목의 범위(`project` 또는 `project_id`) */
  scopeOf: (item: T) => Scope;
  /** 정의 종류 이름(계약에서 읽은 값). 없으면 "프로젝트로 이동…"은 없다(대화·실행처럼 옮길 수 없는 목록) */
  kind?: string | undefined;
  idOf: (item: T) => string;
  nameOf: (item: T) => string;
}

export interface ScopedList<T> {
  /** 현재 보기 범위로 거른 항목(프로젝트 기능이 꺼져 있으면 그대로). 입력이 undefined면 undefined */
  items: T[] | undefined;
  /** 범위 밖이라 숨긴 수 */
  hiddenCount: number;
  /** 목록 머리에 끼울 줄(범위 필터 + 선택 도구). 필요 없으면 null */
  bar: ReactNode;
  /** 행에 붙일 범위 태그와 (선택 모드의) 선택 표시 */
  rowExtra: (item: T) => ReactNode;
  selection: ListSelection;
  /** 행 선택 처리: 선택 모드면 토글하고 true, 아니면 false(호출자가 평소 동작) */
  intercept: (id: string) => boolean;
  /** 화면 어디에든 한 번 그린다 */
  dialog: ReactNode;
}

/**
 * 목록 하나를 현재 프로젝트 보기로 거르고, 범위 태그·다중 선택·"프로젝트로 이동…"을 붙이는 훅(컨테이너 쪽 조립).
 * 프로젝트 기능이 꺼져 있으면 필터·태그·선택이 모두 사라진다.
 */
export function useScopedList<T>(source: readonly T[] | undefined, options: ScopedListOptions<T>): ScopedList<T> {
  const p = useProjects();
  const selection = useListSelection();
  const move = useProjectMove(() => selection.setSelecting(false));
  const { scopeOf, idOf, nameOf, kind } = options;
  const items = useMemo(() => (source === undefined ? undefined : p.filter(source, scopeOf)), [source, p, scopeOf]);
  const hiddenCount = source === undefined || items === undefined ? 0 : source.length - items.length;
  const movable = kind !== undefined && move.available;
  const visibleIds = useMemo(() => (items ?? []).map(idOf), [items, idOf]);

  const bar =
    !p.enabled || (p.current === null && !movable) ? null : (
      <div className="prj-listbar">
        <ScopeFilter />
        {p.current !== null && hiddenCount > 0 ? <span className="app-muted prj-hidden">{t.filter.hiddenCount(hiddenCount)}</span> : null}
        {movable ? (
          <SelectionToolbar
            selection={selection}
            visibleIds={visibleIds}
            onMove={() => {
              const picked = (items ?? []).filter((x) => selection.selected.has(idOf(x)));
              move.request(picked.map((x) => ({ kind: kind as string, id: idOf(x), name: nameOf(x) })));
            }}
          />
        ) : null}
      </div>
    );

  return {
    items,
    hiddenCount,
    bar,
    rowExtra: (item) => (
      <>
        {selection.selecting ? <SelectMark checked={selection.selected.has(idOf(item))} /> : null}
        <ProjectTag scope={scopeOf(item)} />
      </>
    ),
    selection,
    intercept: (id) => {
      if (!selection.selecting) return false;
      selection.toggle(id);
      return true;
    },
    dialog: move.dialog,
  };
}
