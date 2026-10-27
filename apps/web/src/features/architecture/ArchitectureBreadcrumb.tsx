import { useState } from "react";
import { archMessages as t } from "./messages";
import { ARCH_LIMITS } from "./archConfig";

export interface ArchitectureBreadcrumbProps {
  /** 처음 항목 이름(세션 구조도면 "세션") */
  rootLabel: string;
  /** 하위 구조도 단계 이름들 */
  steps: readonly string[];
  /** `index`번째 항목으로 돌아간다(-1 = 처음). 마지막 항목은 현재 위치라 부르지 않는다. */
  onGoTo(index: number): void;
}

/** 빵 부스러기. 마지막은 현재 위치(링크 아님), 4단계 이상이면 가운데를 `…` 단추로 접는다. */
export function ArchitectureBreadcrumb({ rootLabel, steps, onGoTo }: ArchitectureBreadcrumbProps) {
  const [open, setOpen] = useState(false);
  const items = [{ index: -1, label: rootLabel }, ...steps.map((label, i) => ({ index: i, label }))];
  const fold = items.length >= ARCH_LIMITS.crumbFoldFrom;
  const shown = fold ? [items[0], items[items.length - 1]] : items;
  const hidden = fold ? items.slice(1, -1) : [];
  const last = items[items.length - 1];
  const node = (item: (typeof items)[number] | undefined) =>
    item === undefined ? null : item === last ? (
      <span className="arch-crumb-current" aria-current="page" title={item.label}>{item.label}</span>
    ) : (
      <button type="button" className="arch-crumb-link" title={item.label} onClick={() => { setOpen(false); onGoTo(item.index); }}>{item.label}</button>
    );
  return (
    <nav className="arch-crumbs" aria-label={t.breadcrumb.label}>
      <ol>
        <li>{node(shown[0])}</li>
        {fold ? (
          <li className="arch-crumb-fold">
            <span aria-hidden="true">›</span>
            <button type="button" className="arch-crumb-link" aria-expanded={open} aria-label={t.breadcrumb.folded} onClick={() => setOpen((o) => !o)}>…</button>
            {open ? (
              <ul className="arch-crumb-menu">
                {hidden.map((h) => (
                  <li key={h.index}><button type="button" className="arch-crumb-link" title={h.label} onClick={() => { setOpen(false); onGoTo(h.index); }}>{h.label}</button></li>
                ))}
              </ul>
            ) : null}
          </li>
        ) : null}
        {shown.slice(1).map((item) => (
          <li key={item?.index}>
            <span aria-hidden="true">›</span>
            {node(item)}
          </li>
        ))}
      </ol>
    </nav>
  );
}
