import type { FocusEventHandler, ReactNode } from "react";
import { Icon } from "./Icon";
import { joinClass } from "./Status";

/** 들여쓰기에 반영하는 최대 깊이. 더 깊은 묶음은 호출자가 이름에 `/`로 이어 붙인다. */
export const GROUP_HEADER_MAX_DEPTH = 3;

export interface GroupHeaderProps {
  id?: string;
  /** 묶음 이름. 전체 경로는 `title`로. */
  label: ReactNode;
  title?: string;
  count?: number;
  depth?: number;
  collapsed: boolean;
  /** 펼친 항목 묶음의 id(`aria-controls`). 접혀서 그리지 않으면 비운다. */
  controlsId?: string;
  onToggle: () => void;
  tabIndex?: number;
  /** ListPane 이동용 식별자. */
  navKey?: string;
  onFocus?: FocusEventHandler<HTMLButtonElement>;
  className?: string;
  /** 항목을 끌어 이 머리 위에 올린 상태(점선 강조, `data-drop`). */
  dropTarget?: boolean;
}

/**
 * 목록 묶음 머리(접기 단추). 행 전체가 `button aria-expanded`다. sticky 위치·배경은 CSS(`.ac-grouphead`).
 * 표현 전용: 접힘 상태와 토글은 호출자가 가진다.
 */
export function GroupHeader({ id, label, title, count, depth = 0, collapsed, controlsId, onToggle, tabIndex, navKey, onFocus, className, dropTarget }: GroupHeaderProps) {
  const level = Math.max(0, Math.min(GROUP_HEADER_MAX_DEPTH, depth));
  return (
    <button
      id={id}
      type="button"
      className={joinClass("ac-grouphead", className)}
      aria-expanded={!collapsed}
      aria-controls={collapsed ? undefined : controlsId}
      data-nav-key={navKey}
      data-collapsed={collapsed ? "true" : undefined}
      data-drop={dropTarget === true ? "true" : undefined}
      title={title ?? (typeof label === "string" ? label : undefined)}
      tabIndex={tabIndex}
      style={{ paddingLeft: `calc(var(--ac-space-2) + ${level} * 12px)` }}
      onClick={onToggle}
      onFocus={onFocus}
    >
      <span className="ac-grouphead-arrow" aria-hidden="true"><Icon name="chevron-right" size={12} /></span>
      <span className="ac-grouphead-name ac-ellipsis">{label}</span>
      {count === undefined ? null : <span className="ac-grouphead-count">({count})</span>}
    </button>
  );
}
