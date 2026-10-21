import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { MovePlan } from "@agent-console/contracts/projects";
import { Button, useToast } from "@agent-console/ui";
import { useInvalidateLists } from "../library";
import { MoveToProjectDialog, type MoveItem } from "./MoveToProjectDialog";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";

export interface ProjectMove {
  /** 프로젝트 기능이 켜져 있고 옮길 곳(프로젝트)이 하나 이상 있는가. false면 메뉴 항목·선택 모드를 그리지 않는다 */
  available: boolean;
  /** 대화상자를 연다 */
  request: (items: readonly MoveItem[]) => void;
  /** 화면 어디에든 한 번 그린다 */
  dialog: ReactNode;
}

/**
 * "프로젝트로 이동…" 동작: 대화상자 상태와 적용 뒤 처리(목록 갱신·토스트)를 묶는다.
 * 어느 정의 종류인지는 호출자가 `MoveItem.kind`로 준다.
 */
export function useProjectMove(onDone?: (result: MovePlan) => void): ProjectMove {
  const p = useProjects();
  const toast = useToast();
  const invalidate = useInvalidateLists();
  const [items, setItems] = useState<readonly MoveItem[] | null>(null);
  const request = useCallback((next: readonly MoveItem[]) => setItems(next), []);
  const { client } = p;
  const dialog = useMemo(
    () =>
      items === null || client === undefined ? null : (
      <MoveToProjectDialog
        items={items}
        projects={p.projects}
        client={client}
        onClose={() => setItems(null)}
        onApplied={(result) => {
          setItems(null);
          const n = (result.moves ?? []).length;
          const w = (result.warnings ?? []).length;
          toast({ tone: w > 0 ? "warning" : "success", text: w > 0 ? t.move.appliedWithWarnings(n, w) : t.move.applied(n) });
          void invalidate();
          onDone?.(result);
        }}
      />
    ),
    [items, client, p.projects, toast, invalidate, onDone],
  );
  return useMemo(() => ({ available: p.enabled && p.projects.length > 0, request, dialog }), [p.enabled, p.projects.length, request, dialog]);
}

export interface ListSelection {
  selecting: boolean;
  setSelecting: (on: boolean) => void;
  selected: ReadonlySet<string>;
  toggle: (id: string) => void;
  setAll: (ids: readonly string[]) => void;
  clear: () => void;
}

/** 목록의 다중 선택 상태(선택 모드 + 선택한 id 집합). */
export function useListSelection(): ListSelection {
  const [selecting, setSelectingState] = useState(false);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  return useMemo<ListSelection>(
    () => ({
      selecting,
      setSelecting: (on) => {
        setSelectingState(on);
        if (!on) setSelected(new Set());
      },
      selected,
      toggle: (id) =>
        setSelected((cur) => {
          const next = new Set(cur);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        }),
      setAll: (ids) => setSelected(new Set(ids)),
      clear: () => setSelected(new Set()),
    }),
    [selecting, selected],
  );
}

export interface SelectionToolbarProps {
  selection: ListSelection;
  /** 지금 보이는 항목 id(모두 선택용) */
  visibleIds: readonly string[];
  onMove: () => void;
  className?: string;
}

/** 목록 위 한 줄: [선택] 토글 + (선택 모드에서) `n개 선택됨` [모두 선택] [프로젝트로 이동…]. */
export function SelectionToolbar({ selection, visibleIds, onMove, className }: SelectionToolbarProps) {
  const { selecting, setSelecting, selected, setAll } = selection;
  return (
    <div className={["prj-selectbar", className].filter(Boolean).join(" ")}>
      <Button size="sm" variant={selecting ? "secondary" : "ghost"} aria-pressed={selecting} onClick={() => setSelecting(!selecting)}>
        {selecting ? t.move.selectModeOff : t.move.selectMode}
      </Button>
      {selecting ? (
        <>
          <span className="app-muted" role="status">{t.move.selected(selected.size)}</span>
          <Button size="sm" variant="ghost" onClick={() => setAll(visibleIds)} disabled={visibleIds.length === 0}>{t.move.selectAll}</Button>
          <Button size="sm" variant="primary" disabled={selected.size === 0} onClick={onMove}>{t.move.menu}</Button>
        </>
      ) : null}
    </div>
  );
}

/** 선택 모드의 행 표시(체크 상자 모양, 장식). 행 자체가 선택 항목이다(`aria-selected`). */
export function SelectMark({ checked }: { checked: boolean }) {
  return <span className="prj-mark" data-checked={checked ? "true" : "false"} aria-hidden="true">{checked ? "☑" : "☐"}</span>;
}
