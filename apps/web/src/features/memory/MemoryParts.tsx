/** 메모리 화면의 작은 조립 부품: 분리선(칸 폭 조절), 떠 있는 행 메뉴, 범위 요약, 상태 안내. */
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Button, Icon, Menu, type MenuItemDef } from "@agent-console/ui";
import type { MemoryScopeSummary } from "@agent-console/contracts/memory";
import { formatBytes } from "@agent-console/memory-view";
import { formatDateTime } from "../../lib/format";
import { sizeMessages } from "./format";
import { memoryMessages as t } from "./messages";

export interface PaneSeparatorProps {
  /** 조절되는 칸의 현재 폭 */
  size: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
  label: string;
  /** `left`: 칸이 분리선의 왼쪽에 있다(오른쪽으로 끌면 커진다). `right`: 오른쪽에 있다(왼쪽으로 끌면 커진다) */
  side: "left" | "right";
  step?: number;
}

/** 칸 폭 분리선: 포인터로 끌거나 포커스 뒤 `←→` 16px. `role="separator"` + 현재 값. */
export function PaneSeparator({ size, min, max, onChange, label, side, step = 16 }: PaneSeparatorProps) {
  const start = useRef<{ x: number; size: number } | null>(null);
  const clamp = (n: number) => Math.min(max, Math.max(min, n));
  const sign = side === "left" ? 1 : -1;
  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    start.current = { x: e.clientX, size };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (start.current !== null) onChange(clamp(start.current.size + sign * (e.clientX - start.current.x)));
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const grow = (e.key === "ArrowRight") === (side === "left");
    onChange(clamp(size + (grow ? step : -step)));
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={size}
      tabIndex={0}
      className="mem-split"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={() => (start.current = null)}
      onPointerCancel={() => (start.current = null)}
      onKeyDown={onKey}
    />
  );
}

export interface FloatingMenuProps {
  anchor: HTMLElement;
  items: readonly MenuItemDef[];
  label: string;
  onClose: () => void;
}

/** 앵커 요소 아래에 뜨는 메뉴(행 메뉴 키 `Shift+F10`용). 바깥 클릭·Esc로 닫고 닫으면 앵커로 포커스가 돌아간다. */
export function FloatingMenu({ anchor, items, label, onClose }: FloatingMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [place] = useState(() => {
    const r = anchor.getBoundingClientRect();
    return { top: Math.min(r.bottom, window.innerHeight - 240), left: Math.min(r.left + 24, window.innerWidth - 232) };
  });
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)')?.focus();
    const down = (e: Event) => {
      if (!(e.target instanceof Node) || !ref.current?.contains(e.target)) onClose();
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [onClose]);
  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={label}
      className="ac-popover mem-floating"
      style={{ position: "fixed", top: place.top, left: place.left, width: 220 }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
          anchor.focus();
        }
      }}
    >
      <Menu items={items} onClose={onClose} />
    </div>
  );
}

export interface ScopeSummaryPanelProps {
  summary: MemoryScopeSummary | undefined;
  label: string | null;
  onNew: () => void;
}

/** 3칸에서 항목을 고르지 않았을 때 상세 칸에 보이는 범위 요약. 범위를 고르지 않았으면 안내 한 줄. */
export function ScopeSummaryPanel({ summary, label, onNew }: ScopeSummaryPanelProps) {
  if (label === null) {
    return <p className="mem-muted mem-detail-hint">{t.detail.emptyHint}</p>;
  }
  return (
    <section className="mem-summary" aria-label={t.detail.summaryTitle}>
      <h2 className="mem-summary-title ac-ellipsis" title={label}>{label}</h2>
      <dl className="mem-summary-grid">
        <div><dt>{t.detail.summaryTitle}</dt><dd>{t.detail.scopeEntries(summary?.entries ?? 0)} · {t.detail.scopeArchived(summary?.archived ?? 0)}</dd></div>
        <div><dt>{t.detail.scopeBytes}</dt><dd>{formatBytes(summary?.bytes ?? 0, sizeMessages)}</dd></div>
        <div><dt>{t.detail.scopeUpdated}</dt><dd>{summary?.updated_at == null ? "–" : formatDateTime(summary.updated_at)}</dd></div>
      </dl>
      <Button onClick={onNew} icon={<Icon name="plus" />}>{t.actions.new}</Button>
    </section>
  );
}
