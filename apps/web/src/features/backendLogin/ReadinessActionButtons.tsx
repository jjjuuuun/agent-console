import { useState } from "react";
import type { ReadinessAction } from "@agent-console/contracts";
import { Button, Menu, Popover } from "@agent-console/ui";
import { loginMessages as t } from "./messages";
import { KNOWN_ACTION_KINDS } from "./types";

export interface ReadinessActionButtonsProps {
  /** 서버가 준 동작 목록(`BackendReadiness.actions`). 모르는 kind는 그리지 않는다 */
  actions: readonly ReadinessAction[] | undefined;
  onAction: (action: ReadinessAction) => void;
  size?: "sm" | "md";
}

/** 주 동작은 버튼, 나머지는 `…` 메뉴. 문구는 서버가 준 데이터. */
export function ReadinessActionButtons({ actions, onAction, size = "sm" }: ReadinessActionButtonsProps) {
  const [open, setOpen] = useState(false);
  const known = (actions ?? []).filter((a) => KNOWN_ACTION_KINDS.includes(a.kind));
  if (known.length === 0) return null;
  const primary = known.filter((a) => a.primary === true);
  const rest = known.filter((a) => a.primary !== true);
  return (
    <span className="app-readiness-actions" data-testid="readiness-actions">
      {primary.map((a) => (
        <Button key={`${a.kind}:${a.method_id ?? ""}`} size={size} variant="primary" onClick={() => onAction(a)}>
          {a.label}
        </Button>
      ))}
      {rest.length > 0 ? (
        <Popover
          open={open}
          onOpenChange={setOpen}
          panelRole="menu"
          panelLabel={t.menuLabel}
          align="end"
          renderTrigger={(props) => (
            <Button {...props} size={size} aria-label={t.menuLabel}>
              {t.menuTrigger}
            </Button>
          )}
        >
          {({ close }) => (
            <Menu
              onClose={close}
              items={rest.map((a) => ({ id: `${a.kind}:${a.method_id ?? ""}`, label: a.label, onSelect: () => onAction(a) }))}
            />
          )}
        </Popover>
      ) : null}
    </span>
  );
}
