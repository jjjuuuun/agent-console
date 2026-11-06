/**
 * 기능 화면들이 같이 쓰는 작은 부품: 막힌 이유를 말하는 버튼, 눌러서 여는 메뉴 버튼. 데이터와 콜백은 props다(스펙·위키 화면이 같이 쓴다).
 */
import { useId, useState, type ReactNode } from "react";
import { Button, Menu, Popover, type MenuItemDef } from "@agent-console/ui";

/** 막힌 버튼은 숨기지 않고 `aria-disabled` + 이유 + 툴팁이다. 눌러도 아무 일 없고 포커스는 유지한다. */
export function GuardedButton({ blockedReason, onClick, children, variant, size = "sm", ariaLabel }: { blockedReason: string | undefined; onClick: () => void; children: ReactNode; variant?: "primary" | "secondary"; size?: "sm" | "md"; ariaLabel?: string }) {
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const reasonId = useId();
  return (
    <>
      <Button
        size={size}
        {...(variant === undefined ? {} : { variant })}
        aria-disabled={blocked || undefined}
        aria-describedby={blocked ? reasonId : undefined}
        {...(ariaLabel === undefined ? {} : { "aria-label": ariaLabel })}
        title={blocked ? blockedReason : undefined}
        onClick={() => {
          if (!blocked) onClick();
        }}
      >
        {children}
      </Button>
      {blocked ? <span id={reasonId} className="ac-sr-only">{blockedReason}</span> : null}
    </>
  );
}

/** 눌러서 여는 메뉴 버튼(`Popover` + `Menu`). 막힌 이유가 있으면 `aria-disabled`이고 열리지 않는다. 항목·라벨은 props다. */
export function MenuButton({ label, items, blockedReason, size = "sm", panelLabel, align = "end" }: { label: ReactNode; items: readonly MenuItemDef[]; blockedReason?: string | undefined; size?: "sm" | "md"; panelLabel: string; align?: "start" | "end" }) {
  const [open, setOpen] = useState(false);
  const blocked = blockedReason !== undefined && blockedReason !== "";
  return (
    <Popover
      open={open && !blocked}
      onOpenChange={(next) => setOpen(next && !blocked)}
      panelRole="menu"
      panelLabel={panelLabel}
      align={align}
      renderTrigger={(trigger) => (
        <Button size={size} {...trigger} aria-disabled={blocked || undefined} title={blocked ? blockedReason : undefined}>{label}</Button>
      )}
    >
      {({ close }) => <Menu items={items} onClose={close} />}
    </Popover>
  );
}
