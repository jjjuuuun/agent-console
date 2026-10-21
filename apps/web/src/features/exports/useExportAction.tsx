import { useState, type ReactNode } from "react";
import type { ExportSelection } from "@agent-console/contracts";
import { useRegisterCommands } from "../../shell/commands";
import { ExportDialog } from "./ExportDialog";

export interface UseExportActionOptions {
  /** 지금 화면의 정의(없으면 항목 고르기부터) */
  items: readonly ExportSelection[];
  dirty?: boolean;
  onSave?: () => void;
  infoLink?: ReactNode;
}

/**
 * 정의 화면 공용 [내보내기…] 진입점: 열기 함수 + 다이얼로그 노드 + 빠른 이동(Ctrl+K) 명령 등록.
 * 호출한 화면이 메뉴 항목에서 `open()`을 부르고 반환된 `dialog`를 그린다.
 */
export function useExportAction({ items, dirty, onSave, infoLink }: UseExportActionOptions): { open: () => void; dialog: ReactNode } {
  const [open, setOpen] = useState(false);
  useRegisterCommands([{ id: "export.current", titleKey: "palette.actions.exportCurrent", run: () => setOpen(true) }]);
  const dialog = open ? (
    <ExportDialog
      initialItems={items}
      onClose={() => setOpen(false)}
      {...(dirty === undefined ? {} : { dirty })}
      {...(onSave === undefined ? {} : { onSave })}
      {...(infoLink === undefined ? {} : { infoLink })}
    />
  ) : null;
  return { open: () => setOpen(true), dialog };
}
