import { useState, type ReactNode } from "react";
import { Menu, Popover, type MenuItemDef } from "@agent-console/ui";

export interface MenuPopoverProps {
  /** 패널 접근성 이름 */
  label: string;
  items: readonly MenuItemDef[];
  /** 트리거 버튼 내용 */
  children: ReactNode;
  /** 트리거 접근성 이름(내용이 글자가 아닐 때) */
  triggerLabel?: string | undefined;
  triggerClassName?: string;
  /** 막힘: 열리지 않고 `aria-disabled` + 이유 툴팁 */
  blockedReason?: string | undefined;
  align?: "start" | "end";
}

/** 버튼 하나가 여는 메뉴(제어 상태를 안에 둔다). 막힘이면 열지 않고 이유를 툴팁으로 준다. */
export function MenuPopover({ label, items, children, triggerLabel, triggerClassName = "ac-btn", blockedReason, align = "end" }: MenuPopoverProps) {
  const [open, setOpen] = useState(false);
  const blocked = blockedReason !== undefined || items.length === 0;
  return (
    <Popover
      open={open && !blocked}
      onOpenChange={setOpen}
      panelRole="menu"
      panelLabel={label}
      align={align}
      renderTrigger={(tp) => (
        <button
          {...tp}
          type="button"
          className={triggerClassName}
          data-variant={triggerClassName === "ac-btn" ? "secondary" : undefined}
          data-size={triggerClassName === "ac-btn" ? "sm" : undefined}
          aria-label={triggerLabel}
          aria-disabled={blocked ? "true" : undefined}
          title={blockedReason}
          onClick={() => {
            if (!blocked) tp.onClick();
          }}
        >
          {children}
        </button>
      )}
    >
      {({ close }) => <Menu items={items} onClose={close} />}
    </Popover>
  );
}
