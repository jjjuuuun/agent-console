import { useId, type KeyboardEvent, type ReactNode } from "react";
import { Button, Menu, Popover } from "@agent-console/ui";
import type { AddAction, AddMenuEntry } from "./addMenu";
import { DefinitionPicker, type DefinitionPickerProps } from "./DefinitionPicker";
import { teamMessages as t } from "./messages";

/** 열린 면: 메뉴 또는 한 종류의 정의 고르기. 닫힘 = null. */
export type AddView = { op: "menu" } | { op: "pick"; kind: string } | null;

export interface AddControlProps {
  entries: readonly AddMenuEntry[];
  view: AddView;
  onViewChange: (view: AddView) => void;
  /** 메뉴 항목을 골랐을 때(고르기는 `onViewChange`로 열고, 만들기·노드 추가는 이 콜백) */
  onAction: (action: Exclude<AddAction, { op: "pick" }>) => void;
  /** 고르기 면의 내용. 종류를 못 고르면 undefined */
  pickerProps: (kind: string) => DefinitionPickerProps | undefined;
  /** 고르기 면 위에 끼울 내용(예: 제목) */
  header?: (kind: string) => ReactNode;
  disabled?: boolean;
}

/**
 * 캔버스 도구줄의 [+ 추가 ▾]: 팝오버 하나가 메뉴와 정의 고르기를 번갈아 보인다.
 * 메뉴 안에서 숫자키 1~9로 항목을 고른다. 항목은 호출자가 데이터로 준다(`buildAddMenu`).
 */
export function AddControl({ entries, view, onViewChange, onAction, pickerProps, header, disabled = false }: AddControlProps) {
  const uid = useId();
  const choose = (entry: AddMenuEntry) => {
    if (entry.action.op === "pick") onViewChange({ op: "pick", kind: entry.action.kind });
    else {
      onViewChange(null);
      onAction(entry.action);
    }
  };
  const onMenuKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (!/^[1-9]$/.test(e.key) || e.ctrlKey || e.metaKey || e.altKey) return;
    const entry = entries[Number(e.key) - 1];
    if (entry === undefined) return;
    e.preventDefault();
    e.stopPropagation();
    choose(entry);
  };
  const picking = view?.op === "pick" ? view.kind : null;
  const pick = picking === null ? undefined : pickerProps(picking);
  return (
    <Popover
      open={view !== null}
      onOpenChange={(open) => onViewChange(open ? { op: "menu" } : null)}
      panelRole={picking !== null ? "dialog" : "menu"}
      panelLabel={t.add.menuLabel}
      panelClassName={picking !== null ? "team-add-panel team-add-panel--pick" : "team-add-panel"}
      renderTrigger={(p) => (
        <Button {...p} size="sm" variant="primary" disabled={disabled || entries.length === 0} title={t.add.buttonTitle} aria-keyshortcuts="Alt+N" data-testid="add-button">
          + {t.add.button} <span aria-hidden="true">▾</span>
        </Button>
      )}
    >
      {pick !== undefined && picking !== null ? (
        <div id={`${uid}-pick`}>
          {header?.(picking)}
          <DefinitionPicker {...pick} />
        </div>
      ) : (
        <div onKeyDown={onMenuKeyDown}>
          <Menu
            items={entries.map((entry, i) => ({
              id: entry.id,
              label: (
                <>
                  <span className="team-add-num" aria-hidden="true">{i + 1}</span> {entry.label}
                </>
              ),
              title: entry.label,
              onSelect: () => choose(entry),
            }))}
          />
        </div>
      )}
    </Popover>
  );
}
