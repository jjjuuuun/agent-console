import { useMemo, useState } from "react";
import { Button } from "@agent-console/ui";
import { projectMessages as t } from "./messages";

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
  /** 선택한 항목에 쓸 동작 버튼 글자(기본 "프로젝트로 이동…") */
  actionLabel?: string;
  className?: string;
}

/** 목록 위 한 줄: [선택] 토글 + (선택 모드에서) `n개 선택됨` [모두 선택] [프로젝트로 이동…]. */
export function SelectionToolbar({ selection, visibleIds, onMove, actionLabel, className }: SelectionToolbarProps) {
  const { selecting, setSelecting, selected, setAll } = selection;
  return (
    <div className={["prj-selectbar", className].filter(Boolean).join(" ")}>
      <Button size="sm" variant={selecting ? "primary" : "secondary"} aria-pressed={selecting} onClick={() => setSelecting(!selecting)}>
        {selecting ? t.move.selectModeOff : t.move.selectMode}
      </Button>
      {selecting ? (
        <>
          <span className="app-muted" role="status">{t.move.selected(selected.size)}</span>
          <Button size="sm" variant="ghost" onClick={() => setAll(visibleIds)} disabled={visibleIds.length === 0}>{t.move.selectAll}</Button>
          <Button size="sm" variant="primary" disabled={selected.size === 0} onClick={onMove}>{actionLabel ?? t.move.menu}</Button>
        </>
      ) : null}
    </div>
  );
}

/** 선택 모드의 행 표시(체크 상자 모양, 장식). 행 자체가 선택 항목이다(`aria-selected`). */
export function SelectMark({ checked }: { checked: boolean }) {
  return <span className="prj-mark" data-checked={checked ? "true" : "false"} aria-hidden="true">{checked ? "☑" : "☐"}</span>;
}
