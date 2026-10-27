import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button, trapTabKey, useModalBackdrop } from "@agent-console/ui";
import { ARCH_FIT } from "./archConfig";
import { LazyArchitecturePanel as ArchitecturePanel } from "./lazy";
import type { ArchitecturePanelProps } from "./ArchitecturePanel";
import { archMessages as t } from "./messages";
import type { ArchitectureController } from "./useArchitectureController";

export interface ArchitectureDialogProps {
  open: boolean;
  /** 제목 줄 글(예: "구조도 · {프로필} · {범위 이름}") */
  title: string;
  onClose(): void;
  /** 열기 전 화면과 같은 컨트롤러(선택·필터가 같은 상태를 공유한다) */
  controller: ArchitectureController;
  /** 패널에 그대로 넘기는 나머지 props(빈 상태 콜백·`live` 등) */
  panelProps?: Omit<ArchitecturePanelProps, "controller" | "className" | "viewportWidth">;
  /** 그림 아래 이벤트 표 영역(높이 25%). 호출하는 쪽이 만든 표를 넣는다. */
  table?: ReactNode;
}

/** 그림·표 비율과 표 최소 높이는 `ARCH_FIT`가 정하고, CSS는 이 변수만 읽는다. */
const dialogVars = {
  "--arch-diagram-grow": ARCH_FIT.dialogSplit.diagram,
  "--arch-table-grow": ARCH_FIT.dialogSplit.table,
  "--arch-diagram-grow-narrow": ARCH_FIT.dialogSplitNarrow.diagram,
  "--arch-table-grow-narrow": ARCH_FIT.dialogSplitNarrow.table,
  "--arch-table-min": `${ARCH_FIT.dialogTableMin}px`,
} as React.CSSProperties;

/**
 * [크게 보기] 대화상자(화면 명세 §6.4): 그림 75% + 이벤트 표 25%(최소 120).
 * `Esc`는 선택(필터)이 있으면 선택만 풀고, 없으면 닫는다. 바깥 클릭으로는 닫지 않는다.
 * 닫으면 열기 전에 포커스가 있던 요소(보통 [크게 보기] 단추)로 돌아간다.
 */
export function ArchitectureDialog({ open, title, onClose, controller, panelProps, table }: ArchitectureDialogProps) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useModalBackdrop(open, backdropRef);
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  if (!open) return null;
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (controller.selection !== null) controller.select(null);
      else onClose();
      return;
    }
    trapTabKey(event, ref.current);
  };
  return createPortal(
    <div ref={backdropRef} className="ac-dialog-backdrop">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className="arch-dialog" style={dialogVars} onKeyDown={onKeyDown}>
        <div className="arch-dialog-head">
          <h2 id={titleId} className="arch-dialog-title">{title}</h2>
          <Button ref={closeRef} size="sm" aria-label={t.dialog.close} onClick={onClose}>{t.dialog.close}</Button>
        </div>
        <div className="arch-dialog-diagram">
          <ArchitecturePanel controller={controller} {...(panelProps ?? {})} />
        </div>
        {table === undefined ? null : <div className="arch-dialog-table">{table}</div>}
      </div>
    </div>,
    document.body,
  );
}
