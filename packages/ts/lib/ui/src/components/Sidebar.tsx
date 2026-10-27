import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Icon } from "./Icon";
import { Tooltip } from "./Tooltip";
import { joinClass } from "./Status";

export interface SidebarItem {
  id: string;
  label: string;
  icon?: ReactNode;
  href?: string;
  /** 숫자 배지. `label`은 "응답 대기 3건"처럼 의미 문구(접근성 이름). */
  badge?: { count: number; label: string };
  /**
   * `main` = 주 메뉴 목록, `footer` = 주 메뉴 목록 아래 고정 줄(글자 있는 항목, 설정 같은 목적지),
   * `bottom` = 하단 도구줄에 아이콘만으로 그린다(항목의 `icon` 필수. 없으면 라벨 첫 글자).
   */
  position?: "main" | "footer" | "bottom";
  /** 묶음 id(`SidebarProps.groups`의 id). 비었거나 모르는 값이면 제목 없는 맨 앞 묶음 */
  group?: string;
  /** 툴팁(`title`). 없으면 라벨. 도구줄 항목은 단축키를 덧붙여 줄 때 쓴다 */
  tooltip?: string;
}

/** 사이드바 묶음 하나(주 메뉴 목록의 소제목 + 항목). */
export interface SidebarGroup {
  id: string;
  label: string;
}

/** 묶음 단위로 나눈 주 메뉴 항목. `label`이 없으면 제목 없는 묶음(맨 앞). */
export interface SidebarSection {
  id: string;
  label?: string;
  items: SidebarItem[];
}

/**
 * 항목을 묶음 순서대로 나눈다. 항목이 하나도 없는 묶음은 만들지 않는다(모듈이 꺼져 항목이 사라지면 제목도 사라진다).
 * `group`이 없거나 `groups`에 없는 항목은 제목 없는 맨 앞 묶음에 들어간다. 항목 순서는 입력 순서를 지킨다.
 */
export function groupSidebarItems(items: readonly SidebarItem[], groups: readonly SidebarGroup[] = []): SidebarSection[] {
  const known = new Set(groups.map((g) => g.id));
  const loose = items.filter((i) => i.group === undefined || !known.has(i.group));
  const out: SidebarSection[] = loose.length === 0 ? [] : [{ id: "", items: loose }];
  for (const g of groups) {
    const mine = items.filter((i) => i.group === g.id);
    if (mine.length > 0) out.push({ id: g.id, label: g.label, items: mine });
  }
  return out;
}

export interface SidebarMessages {
  /** nav 접근성 이름 */
  navLabel: string;
  /** 사이드바 전체(`aside` landmark) 접근성 이름. 없으면 이름 없는 landmark */
  regionLabel?: string;
  collapse: string;
  expand: string;
  /** 도구줄(`role=group`) 접근성 이름 */
  tools?: string;
  /** 접기 버튼의 고정 접근성 이름(상태는 `aria-expanded`). 주면 `collapse`·`expand` 대신 쓴다 */
  toggle?: string;
  /** 접기 버튼 툴팁(예: "사이드바 (Ctrl+Shift+B)"). 없으면 `toggle` */
  toggleTitle?: string;
}

export interface SidebarProps {
  items: readonly SidebarItem[];
  activeId?: string;
  onNavigate: (id: string) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  header?: ReactNode;
  footer?: ReactNode;
  /** 주 메뉴 묶음(순서 = 표시 순서). 비우면 묶음 없이 한 목록 */
  groups?: readonly SidebarGroup[];
  /** 하단 도구줄의 앞쪽(`bottom` 항목·접기 버튼 앞)에 놓을 버튼들 */
  tools?: ReactNode;
  messages: SidebarMessages;
  className?: string;
}

/** 배지 숫자 표기: 99 초과는 `99+`. */
export function formatBadgeCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

/**
 * 사이드바 내비게이션(루트는 `aside` landmark). 항목 목록은 호출자 데이터(라우트 설정). 라우터를 모르며 `onNavigate`만 호출한다.
 * `nav`(주 메뉴 landmark)는 항목 목록만 감싸고, `header`·`footer` 슬롯은 `nav` 밖(사이드바 루트 안)에 놓인다.
 * Tab은 사이드바를 한 번에 지나가고(roving tabindex) 항목 이동은 ↑↓ Home End.
 */
export function Sidebar({ items, activeId, onNavigate, collapsed, onCollapsedChange, header, footer, groups, tools, messages, className }: SidebarProps) {
  const listRef = useRef<HTMLElement>(null);
  const main = items.filter((i) => i.position !== "bottom" && i.position !== "footer");
  const pinned = items.filter((i) => i.position === "footer");
  const bottom = items.filter((i) => i.position === "bottom");
  const sections = groupSidebarItems(main, groups);
  const titleId = useId();
  // roving 대상: 활성 항목, 없으면 첫 항목(도구줄은 별도 탭 정지점이라 제외)
  const flat = [...sections.flatMap((s) => s.items), ...pinned];
  const tabStopId = flat.some((i) => i.id === activeId) ? activeId : flat[0]?.id;

  const onKeyDown = (event: KeyboardEvent) => {
    const nodes = Array.from(listRef.current?.querySelectorAll<HTMLElement>("[data-nav-item]") ?? []);
    const index = nodes.indexOf(document.activeElement as HTMLElement);
    if (index < 0) return;
    let next: number | undefined;
    if (event.key === "ArrowDown") next = (index + 1) % nodes.length;
    else if (event.key === "ArrowUp") next = (index - 1 + nodes.length) % nodes.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = nodes.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    nodes[next]?.focus();
  };

  const renderItem = (item: SidebarItem) => {
    const active = item.id === activeId;
    const content = (
      <>
        {item.icon === undefined ? null : <span className="ac-sidebar-icon" aria-hidden="true">{item.icon}</span>}
        <span className="ac-sidebar-label ac-ellipsis">{item.label}</span>
        {item.badge === undefined || item.badge.count <= 0 ? null : (
          <span className="ac-sidebar-badge" aria-label={item.badge.label}>{formatBadgeCount(item.badge.count)}</span>
        )}
        {collapsed ? <span className="ac-sidebar-tip" aria-hidden="true">{item.label}</span> : null}
      </>
    );
    const common = {
      "data-nav-item": "",
      "data-id": item.id,
      className: "ac-sidebar-item",
      "aria-current": active ? ("page" as const) : undefined,
      tabIndex: item.id === tabStopId ? 0 : -1,
      title: collapsed ? item.label : undefined,
    };
    return (
      <li key={item.id}>
        {item.href === undefined ? (
          <button type="button" {...common} onClick={() => onNavigate(item.id)}>
            {content}
          </button>
        ) : (
          <a
            href={item.href}
            {...common}
            onClick={(event) => {
              // 새 탭·수식키 클릭은 브라우저에 맡기고, 일반 클릭만 앱 내 이동으로 처리한다.
              if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
              event.preventDefault();
              onNavigate(item.id);
            }}
          >
            {content}
          </a>
        )}
      </li>
    );
  };

  const renderTool = (item: SidebarItem) => {
    const common = {
      "data-id": item.id,
      className: "ac-btn ac-icon-btn ac-sidebar-tool",
      "data-variant": "ghost",
      "data-size": "md",
      "aria-label": item.label,
      "aria-current": item.id === activeId ? ("page" as const) : undefined,
      title: item.tooltip ?? item.label,
    };
    const glyph = <span aria-hidden="true">{item.icon ?? Array.from(item.label)[0]}</span>;
    return item.href === undefined ? (
      <button key={item.id} type="button" {...common} onClick={() => onNavigate(item.id)}>{glyph}</button>
    ) : (
      <a
        key={item.id}
        href={item.href}
        {...common}
        onClick={(event) => {
          if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          onNavigate(item.id);
        }}
      >
        {glyph}
      </a>
    );
  };

  return (
    <aside ref={listRef} className={joinClass("ac-sidebar", className)} aria-label={messages.regionLabel} data-collapsed={collapsed ? "true" : "false"} onKeyDown={onKeyDown}>
      {header === undefined ? null : <div className="ac-sidebar-header">{header}</div>}
      <nav aria-label={messages.navLabel} className="ac-sidebar-nav">
        <ul className="ac-sidebar-list" data-position="main">
          {sections.map((section, index) =>
            section.label === undefined ? (
              section.items.map(renderItem)
            ) : (
              <li key={section.id} className="ac-sidebar-group" data-group={section.id}>
                {index > 0 ? <div role="separator" aria-orientation="horizontal" className="ac-sidebar-sep" /> : null}
                <span id={`${titleId}-${section.id}`} className="ac-sidebar-group-title">{section.label}</span>
                <ul className="ac-sidebar-group-list" aria-labelledby={`${titleId}-${section.id}`}>{section.items.map(renderItem)}</ul>
              </li>
            ),
          )}
        </ul>
        {pinned.length === 0 ? null : <ul className="ac-sidebar-list" data-position="footer">{pinned.map(renderItem)}</ul>}
      </nav>
      {footer === undefined ? null : <div className="ac-sidebar-footer">{footer}</div>}
      <div className="ac-sidebar-tools" role="group" aria-label={messages.tools}>
        {tools}
        {bottom.map(renderTool)}
        <Tooltip className="ac-sidebar-toggle" placement="top" align="end" content={messages.toggle === undefined ? (collapsed ? messages.expand : messages.collapse) : (messages.toggleTitle ?? messages.toggle)}>
          <button
            type="button"
            className="ac-btn ac-icon-btn"
            data-variant="ghost"
            data-size="md"
            aria-label={messages.toggle ?? (collapsed ? messages.expand : messages.collapse)}
            aria-expanded={!collapsed}
            onClick={() => onCollapsedChange(!collapsed)}
          >
            <span aria-hidden="true"><Icon name={collapsed ? "panel-left-open" : "panel-left-close"} /></span>
          </button>
        </Tooltip>
      </div>
    </aside>
  );
}
