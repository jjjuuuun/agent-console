import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { FOCUSABLE_SELECTOR, IconButton, trapTabKey, useModalBackdrop } from "@agent-console/ui";
import { logsMessages as t } from "./messages";

export interface DrawerProps {
  open: boolean;
  title: string;
  onClose(): void;
  children: ReactNode;
  /** px */
  width?: number;
  /** false면 포커스를 가두지 않는 비모달 패널(`Esc`로 닫을 때만 트리거로 복귀) */
  modal?: boolean;
}

/**
 * 오른쪽 드로어. 모달이면 열릴 때 첫 입력(없으면 제목)에 포커스하고 `Tab`을 안에서 순환시키며 배경을 `inert`로 둔다.
 * 닫으면 열기 전에 포커스가 있던 요소로 돌아간다(트리거가 사라졌으면 포커스를 두지 않는다).
 */
export function Drawer({ open, title, onClose, children, width = 440, modal = true }: DrawerProps) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });
  useModalBackdrop(open, layerRef, { inert: modal });
  useEffect(() => {
    if (!open) return;
    const root = ref.current;
    (root?.querySelector<HTMLElement>("input, select, textarea") ?? root?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? root)?.focus();
  }, [open]);
  if (!open) return null;
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      closeRef.current();
      return;
    }
    if (modal) trapTabKey(e, ref.current);
  };
  return createPortal(
    <div ref={layerRef} className="logs-drawer-layer" data-modal={modal ? "true" : undefined}>
      <div ref={ref} role="dialog" aria-modal={modal ? "true" : undefined} aria-labelledby={titleId} tabIndex={-1} className="logs-drawer" style={{ width }} onKeyDown={onKey}>
        <div className="logs-drawer-head">
          <h2 id={titleId} className="app-block-title">{title}</h2>
          <IconButton label={t.dashboards.closeEditor} icon={<span aria-hidden="true">✕</span>} onClick={onClose} />
        </div>
        <div className="logs-drawer-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
