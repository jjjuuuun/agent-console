import { useShortcuts, type ShortcutDef } from "@agent-console/ui";

export interface ListShortcutHandlers {
  /** 화면(라우트) id — 단축키 범위 */
  scope: string;
  onNew?: () => void;
  onSearch?: () => void;
  onRename?: () => void;
  onDelete?: () => void;
  onStartChat?: () => void;
  /** 보기 메뉴 열기(`G`) */
  onView?: () => void;
  /** 선택 항목을 폴더로 이동(`M`) */
  onMove?: () => void;
  /** 선택 항목의 라벨 편집(`L`) */
  onLabels?: () => void;
}

/**
 * 목록 화면 공용 단축키: `N` 새로 만들기, `/` 검색, `F2` 이름 바꾸기, `Delete` 삭제, `Ctrl+Enter` 대화 시작, `G` 보기 메뉴, `M` 폴더로 이동, `L` 라벨 편집.
 * 단일 문자 키는 입력창 안에서는 동작하지 않는다(공용 단축키 처리기 규칙). 핸들러가 없는 동작은 등록하지 않는다.
 */
export function useListShortcuts({ scope, onNew, onSearch, onRename, onDelete, onStartChat, onView, onMove, onLabels }: ListShortcutHandlers): void {
  const defs: ShortcutDef[] = [];
  const add = (id: string, keys: string, titleKey: string, run: (() => void) | undefined) => {
    if (run !== undefined) defs.push({ id: `${scope}.${id}`, scope, keys, titleKey, run });
  };
  add("new", "n", "shortcuts.libNew", onNew);
  add("search", "/", "shortcuts.libSearch", onSearch);
  add("rename", "F2", "shortcuts.libRename", onRename);
  add("delete", "Delete", "shortcuts.libDelete", onDelete);
  add("chat", "Mod+Enter", "shortcuts.libStartChat", onStartChat);
  add("view", "g", "shortcuts.libView", onView);
  add("move", "m", "shortcuts.libMove", onMove);
  add("labels", "l", "shortcuts.libLabels", onLabels);
  useShortcuts(defs);
}
