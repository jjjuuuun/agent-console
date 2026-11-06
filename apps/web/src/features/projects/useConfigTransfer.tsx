import { useMemo, type ReactNode } from "react";
import { createProjectsText, projectAbilities } from "@agent-console/projects";
import { SelectMark, SelectionToolbar, useListSelection, type ListSelection } from "./useProjectMove";
import { useProjects } from "./ProjectsContext";
import { useSpace } from "./SpaceScope";
import { useCopyDialog } from "./useCopyDialog";

const text = createProjectsText();

/** 행 메뉴 항목(`library`의 `ActionMenu`와 `ui`의 `Menu`가 모두 받는 모양: 글자 라벨). */
export interface ConfigMenuItem {
  id: string;
  label: string;
  disabled?: boolean;
  title?: string;
  onSelect: () => void;
}

export interface ConfigTransferOptions<T> {
  /** 정의 종류 이름(계약에서 읽은 값). 없으면 가져오기·저장 동작이 없다 */
  kind: string | undefined;
  idOf: (item: T) => string;
  nameOf: (item: T) => string;
}

export interface ConfigTransfer<T> {
  /** 목록 항목(거르지 않는다: 공용 화면은 공용만, 프로젝트 사본 화면은 그 프로젝트 것만 서버가 준다) */
  items: T[] | undefined;
  /** 목록 머리에 끼울 선택 도구(동작이 없으면 null) */
  selectTool: ReactNode;
  /** 행에 붙일 선택 표시(선택 모드일 때만) */
  rowExtra: (item: T) => ReactNode;
  selection: ListSelection;
  /** 행 선택 처리: 선택 모드면 토글하고 true, 아니면 false */
  intercept: (id: string) => boolean;
  /** 행 `⋯` 메뉴 항목 하나(공용 화면 = 이 프로젝트로 가져오기, 프로젝트 사본 화면 = 공용에 저장). 동작이 없으면 null */
  menuItem: (item: T) => ConfigMenuItem | null;
  /** 화면 어디에든 한 번 그린다 */
  dialog: ReactNode;
}

/**
 * 구성 목록(팀·에이전트·리소스)의 복사 동작(screen-projects §5.2·§5.3).
 * 공용 화면에서는 현재 프로젝트로 "가져오기", 프로젝트 사본 화면(`?prj=`)에서는 공용으로 "저장"이다. 같은 복사 계획 대화상자를 쓴다.
 * 프로젝트 기능이 꺼져 있거나 프로젝트가 없으면 아무 동작도 없다(목록은 그대로 동작한다).
 */
export function useConfigTransfer<T>(source: readonly T[] | undefined, options: ConfigTransferOptions<T>): ConfigTransfer<T> {
  const p = useProjects();
  const space = useSpace();
  const selection = useListSelection();
  const copy = useCopyDialog();
  const { kind, idOf } = options;
  const toLibrary = space !== null;
  const targetId = space?.project.id ?? p.current;
  const view = targetId === null ? undefined : p.views.find((v) => v.project.id === targetId && v.project.archived !== true);
  const abilities = view === undefined ? undefined : projectAbilities(view, { recordsWritable: view.records_writable !== false });
  const ability = abilities === undefined ? undefined : toLibrary ? abilities.save_to_library : abilities.copy_in;
  const available = p.enabled && view !== undefined && kind !== undefined;
  const blocked = ability?.allowed === false && ability.reason !== null ? text(ability.reason) : undefined;
  const direction = toLibrary ? "save" : "import";
  const label = toLibrary ? text("copy.save_to_library") : text("copy.import_to_project");

  const open = (picked: readonly T[]) => {
    if (!available || targetId === null || blocked !== undefined || kind === undefined) return;
    copy.open({ direction, project: targetId, start: "plan", items: picked.map((x) => ({ kind, id: idOf(x) })) });
  };

  const items = source === undefined ? undefined : [...source];
  const visibleIds = useMemo(() => (source ?? []).map(idOf), [source, idOf]);
  const selectTool = !available ? null : (
    <SelectionToolbar
      selection={selection}
      visibleIds={visibleIds}
      actionLabel={toLibrary ? text("copy.save_to_library") : text({ key: "copy.import_selected", params: { n: selection.selected.size } })}
      onMove={() => {
        if (blocked !== undefined) return;
        open((items ?? []).filter((x) => selection.selected.has(idOf(x))));
        selection.setSelecting(false);
      }}
    />
  );

  return {
    items,
    selectTool,
    rowExtra: (item) => (selection.selecting ? <SelectMark checked={selection.selected.has(idOf(item))} /> : null),
    selection,
    intercept: (id) => {
      if (!selection.selecting) return false;
      selection.toggle(id);
      return true;
    },
    menuItem: (item) =>
      !available ? null : { id: "copy-space", label, ...(blocked === undefined ? {} : { disabled: true, title: blocked }), onSelect: () => open([item]) },
    dialog: copy.dialog,
  };
}
