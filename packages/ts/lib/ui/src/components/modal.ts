import { useEffect, useState, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from "react";

/** 포커스를 받을 수 있는 요소 선택자(모달 안 `Tab` 순환·첫 포커스에 쓴다). */
export const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface UseModalBackdropOptions {
  /** false면 배경을 inert로 두지 않는다(비모달 패널). 닫을 때 포커스 복귀는 그대로다. 기본 true. */
  inert?: boolean;
}

/**
 * 모달이 열려 있는 동안 배경(백드롭 바깥의 body 직계 요소)을 inert로 만들고,
 * 닫히면 우리가 바꾼 것만 되돌리고 열기 전 요소로 포커스를 복귀한다(트리거가 사라졌으면 포커스를 두지 않는다).
 *
 * @param open 열림 여부
 * @param backdropRef 백드롭(포털로 body 직계에 붙은 요소). 이 요소는 inert로 만들지 않는다.
 */
export function useModalBackdrop(open: boolean, backdropRef: RefObject<HTMLElement | null>, options: UseModalBackdropOptions = {}): void {
  const makeInert = options.inert ?? true;
  // 열린 채 마운트되면 첫 렌더에서 트리거를 잡는다: 모달 안 자식의 autoFocus가 부모 효과보다 먼저 돌아 효과 안에서는 이미 모달 안으로 포커스가 옮겨 있다.
  const [mountOpener] = useState<HTMLElement | null>(() => (open && typeof document !== "undefined" && document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null));
  useEffect(() => {
    if (!open) return;
    const backdrop = backdropRef.current;
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // 포커스가 이미 모달 안으로 옮겨 와 있을 때만(자식 autoFocus) 마운트 때 잡아 둔 트리거를 쓴다. 다시 열린 경우는 지금 포커스가 트리거다.
    const previous = mountOpener !== null && active !== null && backdrop?.contains(active) === true ? mountOpener : active;
    const changed: Element[] = [];
    if (makeInert) {
      for (const el of Array.from(document.body.children)) {
        if (el === backdrop || el.hasAttribute("inert")) continue;
        el.setAttribute("inert", "");
        changed.push(el);
      }
    }
    return () => {
      changed.forEach((el) => el.removeAttribute("inert"));
      // inert가 풀린 뒤에야 트리거로 포커스를 돌려줄 수 있다.
      if (previous?.isConnected) previous.focus();
    };
  }, [open, backdropRef, makeInert, mountOpener]);
}

/**
 * 모달 안에서 `Tab`/`Shift+Tab`이 처음과 끝을 순환하게 한다(`onKeyDown`에서 호출).
 * @returns 순환시켰으면 true
 */
export function trapTabKey(event: ReactKeyboardEvent, root: HTMLElement | null): boolean {
  if (event.key !== "Tab" || !root) return false;
  const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  const first = items[0];
  const last = items[items.length - 1];
  if (!first || !last) return false;
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
    return true;
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
    return true;
  }
  return false;
}
