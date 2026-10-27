import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type HTMLAttributes, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { FOCUSABLE_SELECTOR } from "./modal";
import { Icon } from "./Icon";
import { joinClass } from "./Status";

/** `renderTrigger`가 트리거 버튼에 펼쳐 줘야 하는 속성. */
export interface PopoverTriggerProps {
  ref: Ref<HTMLButtonElement>;
  onClick: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  "aria-haspopup": "menu" | "dialog";
  "aria-expanded": boolean;
  "aria-controls": string | undefined;
}

export interface PopoverProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  /** 제어형 열림 상태. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 트리거를 그린다. 받은 속성을 `<button>`에 그대로 펼친다(이름은 호출자가 단다). */
  renderTrigger: (props: PopoverTriggerProps) => ReactNode;
  /** 패널 역할. 메뉴면 `menu`, 목록·설명이면 `dialog`(비모달). */
  panelRole?: "menu" | "dialog";
  /** 패널 접근성 이름. */
  panelLabel: string;
  /** 패널 정렬. 기본 `start`. */
  align?: "start" | "end";
  /** 패널 내용. 함수면 `close`를 받는다. */
  children: ReactNode | ((api: { close: () => void }) => ReactNode);
  panelClassName?: string;
}

/**
 * 트리거 아래에 뜨는 비모달 패널. Esc·바깥 클릭으로 닫고 Esc면 트리거로 포커스를 돌려준다.
 * 포털을 쓰지 않는다(다이얼로그 안에서도 가려지지 않게). 조상이 `overflow:hidden`이면 잘리므로 클립 영역 밖에 둔다.
 */
export function Popover({ open, onOpenChange, renderTrigger, panelRole = "dialog", panelLabel, align = "start", children, panelClassName, className, ...rest }: PopoverProps) {
  const id = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => onOpenChange(false), [onOpenChange]);
  const [place, setPlace] = useState<{ up: boolean; maxHeight: number } | undefined>(undefined);

  // 뷰포트의 남은 공간 기준으로 최대 높이를 정한다. 아래가 모자라고 위가 더 넓으면 위로 펼친다.
  useLayoutEffect(() => {
    if (!open) return;
    const wrap = wrapRef.current;
    const panel = panelRef.current;
    if (wrap === null || panel === null || typeof window === "undefined") return;
    const rect = wrap.getBoundingClientRect();
    const margin = 8;
    const below = window.innerHeight - rect.bottom - margin - 4;
    const above = rect.top - margin - 4;
    const need = panel.scrollHeight;
    const up = need > below && above > below;
    const room = up ? above : below;
    setPlace({ up, maxHeight: Math.max(120, Math.floor(room)) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    (panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? panel)?.focus();
    const onPointerDown = (event: PointerEvent | MouseEvent) => {
      if (event.target instanceof Node && wrapRef.current?.contains(event.target)) return;
      onOpenChange(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, onOpenChange]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (open && event.key === "Escape") {
      event.stopPropagation();
      event.preventDefault();
      onOpenChange(false);
      triggerRef.current?.focus();
    }
  };

  const triggerProps: PopoverTriggerProps = {
    ref: triggerRef,
    onClick: () => onOpenChange(!open),
    onKeyDown: (event) => {
      if (!open && event.key === "ArrowDown") {
        event.preventDefault();
        onOpenChange(true);
        return;
      }
      onKeyDown(event);
    },
    "aria-haspopup": panelRole,
    "aria-expanded": open,
    "aria-controls": open ? id : undefined,
  };

  return (
    <span {...rest} ref={wrapRef} className={joinClass("ac-pop-wrap", className)} onKeyDown={onKeyDown}>
      {renderTrigger(triggerProps)}
      {open ? (
        <div ref={panelRef} id={id} role={panelRole} aria-label={panelLabel} tabIndex={-1} className={joinClass("ac-popover", panelClassName)} data-align={align} data-side={place?.up ? "top" : undefined} style={place === undefined ? undefined : { maxHeight: place.maxHeight }}>
          {typeof children === "function" ? children({ close }) : children}
        </div>
      ) : null}
    </span>
  );
}

export interface MenuItemDef {
  id: string;
  /** 항목 내용. 문자열이 아니어도 그대로 그린다(탭 라벨 등). */
  label: ReactNode;
  /** 전체 값 툴팁. 라벨이 문자열이면 기본값이 라벨이다. */
  title?: string;
  /** 아이콘 레지스트리 이름(데이터). */
  icon?: string;
  disabled?: boolean;
  /** 위험 동작은 호버에서만 danger 색. */
  danger?: boolean;
  onSelect: () => void;
}

export interface MenuProps {
  items: readonly MenuItemDef[];
  /** 항목을 고른 뒤(onSelect 호출 후) 불린다. 보통 Popover의 close. */
  onClose?: () => void;
  className?: string;
}

/** `role=menu` 항목 목록. `↑↓ Home End` 이동(순환), Enter/Space 선택, 첫 항목만 tab 정지점. */
export function Menu({ items, onClose, className }: MenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const enabled = items.filter((i) => i.disabled !== true);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? []);
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next: number | undefined;
    if (event.key === "ArrowDown") next = (index + 1) % buttons.length;
    else if (event.key === "ArrowUp") next = (index - 1 + buttons.length) % buttons.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    if (next === undefined || buttons.length === 0) return;
    event.preventDefault();
    buttons[next]?.focus();
  };
  return (
    <div ref={ref} className={joinClass("ac-menu", className)} onKeyDown={onKeyDown}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          tabIndex={item === enabled[0] ? 0 : -1}
          disabled={item.disabled}
          className="ac-menu-item"
          data-danger={item.danger ? "true" : undefined}
          title={item.title ?? (typeof item.label === "string" ? item.label : undefined)}
          onClick={() => {
            item.onSelect();
            onClose?.();
          }}
        >
          {item.icon === undefined ? null : <Icon name={item.icon} />}
          <span className="ac-menu-label ac-ellipsis">{item.label}</span>
        </button>
      ))}
    </div>
  );
}
