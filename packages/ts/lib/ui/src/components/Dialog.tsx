import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";
import { FOCUSABLE_SELECTOR as FOCUSABLE, trapTabKey, useModalBackdrop } from "./modal";

export interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children?: ReactNode;
  /** 하단 버튼 영역 */
  actions?: ReactNode;
  /** 열릴 때 포커스를 줄 요소. 없으면 첫 포커스 가능 요소 */
  initialFocus?: RefObject<HTMLElement | null>;
  /** 폭: sm 400 / md 480(기본) / lg 720 / xl 960px (`--ac-dialog-w-*`, 모두 94vw 이하). */
  size?: DialogSize;
  /** @deprecated `size="lg"`와 같다. */
  wide?: boolean;
}

export type DialogSize = "sm" | "md" | "lg" | "xl";

/**
 * 모달 다이얼로그: `role="dialog"`, Esc로 닫기, 포커스 가둠, 닫으면 열기 전 요소로 포커스 복귀.
 * 3행 그리드: 제목(고정) / 본문(스크롤) / `actions`(고정, 하단). 버튼은 반드시 `actions` 슬롯에 둔다(본문 안 버튼 줄 금지).
 * 본문의 `fieldset`은 테두리가 없고, 라디오·체크 한 줄은 `.ac-choice`로 정렬한다.
 */
export function Dialog({ open, title, onClose, children, actions, initialFocus, size, wide }: DialogProps) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useModalBackdrop(open, backdropRef);

  useEffect(() => {
    if (!open) return;
    const root = ref.current;
    // 본문 스크롤 영역(tabIndex=0)은 첫 포커스 대상에서 뺀다. 안에 포커스 요소가 없을 때만 본문이 받는다.
    const items = Array.from(root?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    const target = initialFocus?.current ?? items.find((el) => !el.classList.contains("ac-dialog-body")) ?? items[0] ?? root;
    target?.focus();
  }, [open, initialFocus]);

  if (!open) return null;

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCloseRef.current();
      return;
    }
    trapTabKey(event, ref.current);
  };

  return createPortal(
    <div ref={backdropRef} className="ac-dialog-backdrop">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="ac-dialog"
        data-size={size ?? (wide ? "lg" : "md")}
        data-has-actions={actions === undefined ? undefined : "true"}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId} className="ac-dialog-title">
          {title}
        </h2>
        <div className="ac-dialog-body" tabIndex={0} role="region" aria-labelledby={titleId}>{children}</div>
        {actions === undefined ? null : <div className="ac-dialog-actions">{actions}</div>}
      </div>
    </div>,
    document.body,
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** 본문(설명). */
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** true면 확인 버튼이 danger 스타일이고 기본 포커스는 취소 버튼. */
  danger?: boolean;
}

/** 확인/취소 다이얼로그. 문구는 호출자가 넘긴다. */
export function ConfirmDialog({ open, title, children, confirmLabel, cancelLabel, onConfirm, onCancel, danger = false }: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onCancel}
      initialFocus={danger ? cancelRef : undefined}
      actions={
        <>
          <Button ref={cancelRef} onClick={onCancel}>{cancelLabel}</Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>{confirmLabel}</Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
