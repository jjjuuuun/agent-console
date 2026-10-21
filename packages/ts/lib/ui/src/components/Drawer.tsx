import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { IconButton } from "./Button";
import { FOCUSABLE_SELECTOR, trapTabKey, useModalBackdrop } from "./modal";

export interface DrawerProps {
  open: boolean;
  title: string;
  /** 머리 닫기 버튼과 Esc가 부른다. 입력이 있으면 확인을 거치는 일은 호출자가 한다. */
  onClose: () => void;
  /** 머리 아래 한 줄 안내(muted) */
  description?: ReactNode;
  children?: ReactNode;
  /** 하단 고정 버튼 영역 */
  actions?: ReactNode;
  /** 닫기 버튼 접근성 이름(문구는 호출자가 준다) */
  closeLabel: string;
  /** 열릴 때 포커스를 줄 요소. 없으면 본문의 첫 입력 */
  initialFocus?: RefObject<HTMLElement | null>;
  /** 폭(px). 화면보다 넓으면 100vw. 기본 560 */
  width?: number;
  /** `data-testid`(테스트·E2E 선택자) */
  testId?: string;
}

/**
 * 오른쪽 모달 서랍: `role="dialog"`, 머리(제목·닫기) / 스크롤 본문 / 하단 고정 `actions` 3행.
 * Esc로 닫기, Tab 순환, 배경 inert, 닫으면 열기 전 요소로 포커스 복귀. 제어형이라 닫아도 호출자 상태(편집 중인 문서)는 그대로다.
 */
export function Drawer({ open, title, onClose, description, children, actions, closeLabel, initialFocus, width = 560, testId }: DrawerProps) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });
  useModalBackdrop(open, layerRef);
  useEffect(() => {
    if (!open) return;
    const root = ref.current;
    const target = initialFocus?.current ?? root?.querySelector<HTMLElement>(".ac-drawer-body input, .ac-drawer-body select, .ac-drawer-body textarea") ?? root?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? root;
    target?.focus();
  }, [open, initialFocus]);
  if (!open) return null;
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      closeRef.current();
      return;
    }
    trapTabKey(event, ref.current);
  };
  return createPortal(
    <div ref={layerRef} className="ac-drawer-layer">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="ac-drawer"
        data-has-actions={actions === undefined ? undefined : "true"}
        data-testid={testId}
        style={{ width: `min(${width}px, 100vw)` }}
        onKeyDown={onKeyDown}
      >
        <div className="ac-drawer-head">
          <h2 id={titleId} className="ac-drawer-title ac-ellipsis">{title}</h2>
          <IconButton label={closeLabel} icon={<span aria-hidden="true">✕</span>} onClick={onClose} />
        </div>
        {description === undefined ? null : <p className="ac-drawer-note">{description}</p>}
        <div className="ac-drawer-body">{children}</div>
        {actions === undefined ? null : <div className="ac-drawer-actions">{actions}</div>}
      </div>
    </div>,
    document.body,
  );
}
