import type { KeyboardEvent } from "react";

export interface ViewTab {
  id: string;
  label: string;
}

export interface ViewTabsProps {
  tabs: readonly ViewTab[];
  value: string;
  onChange(id: string): void;
  /** 탭 목록 접근성 이름 */
  label: string;
  /** DOM id 접두어(`<prefix>-<tab id>`가 탭 단추 id) */
  idPrefix: string;
}

/**
 * 뷰 탭 줄(`role="tablist"`): 활성 탭만 `tabindex=0`, `←→`로 이동·`Home`/`End`. 탭이 둘 미만이면 그리지 않는다(탭 하나뿐인 줄은 소음이다).
 * 선택은 밑줄(`--ac-accent`)과 `aria-selected`로 보인다(색 단독 아님).
 */
export function ViewTabs({ tabs, value, onChange, label, idPrefix }: ViewTabsProps) {
  if (tabs.length < 2) return null;
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = tabs.findIndex((x) => x.id === value);
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const target = tabs[(next + tabs.length) % tabs.length];
    if (target === undefined) return;
    onChange(target.id);
    requestAnimationFrame(() => document.getElementById(`${idPrefix}-${target.id}`)?.focus());
  };
  return (
    <div role="tablist" aria-label={label} className="logs-viewtabs ac-tabs-list" onKeyDown={onKey}>
      {tabs.map((x) => (
        <button key={x.id} type="button" role="tab" id={`${idPrefix}-${x.id}`} aria-selected={value === x.id} tabIndex={value === x.id ? 0 : -1} className="ac-tab" onClick={() => onChange(x.id)}>
          {x.label}
        </button>
      ))}
    </div>
  );
}
