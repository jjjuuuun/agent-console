import type { ReactNode } from "react";
import { Icon, IconButton, Sidebar, Tooltip, nextTheme, useTheme, type SidebarGroup, type SidebarItem } from "@agent-console/ui";
import { lookupMessage, messages as m } from "../app/messages";
import { gotoCommandId, homeRoute, type RouteDef, type RouteGroupDef } from "./routeConfig";

export interface SidebarBadge {
  count: number;
  label: string;
}

export interface AppSidebarProps {
  routes: readonly RouteDef[];
  /** 주 메뉴 묶음(순서 = 표시 순서). 항목이 없는 묶음은 그리지 않는다 */
  groups?: readonly RouteGroupDef[];
  /** 동작 id → 표시용 단축키(툴팁에 덧붙임). 없으면 툴팁은 이름만 */
  shortcutHint?: (commandId: string) => string | undefined;
  activeId: string | undefined;
  /** 라우트 id → 배지 */
  badges: Readonly<Record<string, SidebarBadge | undefined>>;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  onNavigate: (route: RouteDef) => void;
  onOpenQuickNav: () => void;
  onOpenHelp: () => void;
  /** 로고 줄 바로 아래(주 메뉴 위)에 끼울 요소. 주 메뉴 `nav` 밖이다 */
  headerSlot?: ReactNode;
  /** 서버 모듈 목록을 받기 전: 주 항목 자리에 스켈레톤을 보인다 */
  loadingItems?: boolean;
  /** 푸터 맨 위에 끼울 요소. 주 메뉴 `nav` 밖이다 */
  footerSlot?: ReactNode;
}

/** 사이드바 조립: 라우트 설정 데이터 → `Sidebar` 항목. 라우터를 모르고 콜백만 부른다. */
export function AppSidebar({ routes, groups = [], shortcutHint, activeId, badges, collapsed, onCollapsedChange, onNavigate, onOpenQuickNav, onOpenHelp, headerSlot, footerSlot, loadingItems = false }: AppSidebarProps) {
  const { theme, setTheme } = useTheme();
  const next = nextTheme(theme);
  const items: SidebarItem[] = routes.map((route) => {
    const badge = badges[route.id];
    const label = lookupMessage(route.titleKey);
    const hint = route.gotoKey === null ? undefined : shortcutHint?.(gotoCommandId(route.id));
    return {
      id: route.id,
      label,
      ...(route.group === undefined ? {} : { group: route.group }),
      ...(hint === undefined ? {} : { tooltip: m.sidebar.withShortcut(label, hint) }),
      icon: <Icon name={route.icon} />,
      href: route.path,
      position: route.position,
      ...(badge !== undefined && badge.count > 0 ? { badge } : {}),
    };
  });
  const sidebarGroups: SidebarGroup[] = groups.map((g) => ({ id: g.id, label: lookupMessage(g.titleKey) }));
  const home = homeRoute(routes);
  const withHint = (label: string, commandId: string) => {
    const hint = shortcutHint?.(commandId);
    return hint === undefined ? label : m.sidebar.withShortcut(label, hint);
  };
  return (
    <Sidebar
      items={items}
      {...(activeId === undefined ? {} : { activeId })}
      onNavigate={(id) => {
        const route = routes.find((r) => r.id === id);
        if (route !== undefined) onNavigate(route);
      }}
      collapsed={collapsed}
      onCollapsedChange={onCollapsedChange}
      groups={sidebarGroups}
      messages={{
        navLabel: m.nav.label,
        regionLabel: m.sidebar.region,
        collapse: m.sidebar.collapse,
        expand: m.sidebar.expand,
        tools: m.sidebar.tools,
        toggle: m.sidebar.toggle,
        toggleTitle: shortcutHint?.("sidebar.toggle") === undefined ? m.sidebar.toggle : m.sidebar.toggleTitle(shortcutHint("sidebar.toggle") as string),
      }}
      header={
        <>
        <div className="app-brand-row">
          <button type="button" className="app-brand" aria-label={m.sidebar.brandLink} title={m.sidebar.brandLink} onClick={() => home && onNavigate(home)}>
            <span className="app-brand-mark" aria-hidden="true">◆</span>
            <span className="app-brand-text">{m.sidebar.brand}</span>
          </button>
          <IconButton label={withHint(m.sidebar.quickNav, "palette.open")} icon={<Icon name="search" />} size="sm" onClick={onOpenQuickNav} />
        </div>
        {headerSlot}
        {loadingItems ? (
          <div className="app-nav-skeleton" role="status" aria-label={m.nav.loadingItems}>
            {Array.from({ length: 6 }, (_, i) => (
              <span key={i} className="app-nav-skeleton-row" aria-hidden="true" />
            ))}
          </div>
        ) : null}
        </>
      }
      footer={
        <div className="app-sidebar-foot">
          {footerSlot}
        </div>
      }
      tools={
        <>
          <Tooltip placement="top" align="start" content={withHint(m.shortcuts.helpOpen, "help.open")}>
            <IconButton label={m.shortcuts.helpOpen} title="" icon={<Icon name="help" />} size="md" onClick={onOpenHelp} />
          </Tooltip>
          <Tooltip placement="top" align="start" content={withHint(m.theme.toggle(m.theme.names[theme], m.theme.names[next]), "theme.cycle")}>
            <IconButton label={m.theme.toggle(m.theme.names[theme], m.theme.names[next])} title="" icon={<Icon name="theme" />} size="md" onClick={() => setTheme(next)} />
          </Tooltip>
        </>
      }
    />
  );
}
