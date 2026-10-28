import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { Button, Dialog, ShortcutProvider, nextTheme, splitKeySequence, useEffectiveShortcuts, useTheme, type KeyPlatform, type ShortcutDef, useToast, formatKeyCombo } from "@agent-console/ui";
import { useApi } from "../app/ApiContext";
import { useConnectionStatus } from "../app/useConnectionStatus";
import { resetHints } from "../app/hints";
import { lookupMessage, messages as m } from "../app/messages";
import { useWorkspaceSettings } from "../app/queries";
import { readJson } from "../app/storage";
import { useStorage } from "../app/StorageContext";
import { UnsavedProvider, useHasUnsaved } from "../definition/unsaved";
import { detectPlatform } from "../lib/keybindings";
import { usePwaUpdate } from "../pwa/PwaContext";
import { AppSidebar, type SidebarBadge } from "./AppSidebar";
import { CommandsProvider, useRegisterCommands, type CommandDef } from "./commands";
import { EscapeProvider, useEscapeLayer } from "./escapeStack";
import { ConnectionBanner } from "./ConnectionBanner";
import { useConnectionBanner } from "../app/connectionBanner";
import { GlobalBanners } from "./GlobalBanners";
import { HelpDialog } from "./HelpDialog";
import { StartGuideDialog } from "../features/start";
import { UsageIndicator, INDICATOR_HOSTS } from "../features/usage";
import { createBrowserPorts, NotificationsProvider, type NotificationPorts } from "../features/notifications";
import { isViewingTarget, targetPath, type TargetRoutes } from "../features/notifications/routing";
import { ROUTE_ROLES } from "../features/library/paths";
import { PROJECT_SHORTCUT_DEFS, ProjectsProvider, SETTINGS_PROJECTS_HASH, SidebarProjectRegion, useProjects } from "../features/projects";
import { LINK_PART_IDS, ModuleNotices, useLinkPart, useModules, useRequiresPartition } from "../modules";
import { routeServing } from "./routeConfig";
import { PendingInteractionsProvider, usePendingInteractions } from "./pending";
import { ShortcutEnvironmentContext } from "./shortcutDefaults";
import { QuickNav } from "./QuickNav";
import { activeRoute, DEFAULT_ROUTE_GROUPS, gotoCommandId, gotoShortcuts, type RouteDef, type RouteGroupDef } from "./routeConfig";
import { composeDocumentTitle, PageTitleProvider, usePageTitleOverride, usePageTitleSuffix } from "./titles";
import { useSidebarState } from "./useSidebarState";

const RECENT_KEY = "ac.recent";
const RECENT_MAX = 5;
/** 닫을 때까지 남는 토스트(타이머 한도 안의 큰 값) */
const TOAST_FOREVER_MS = 2_000_000_000;

export interface ShellProps {
  /** 라우트 설정 데이터(사이드바·빠른 이동·`g` 단축키·문서 제목의 원천) */
  routes: readonly RouteDef[];
  /** 사이드바 묶음 데이터(기본: `DEFAULT_ROUTE_GROUPS`) */
  groups?: readonly RouteGroupDef[];
  /** 키 표기 플랫폼(기본: 브라우저에서 판별) */
  platform?: KeyPlatform;
  /** 브라우저 알림·소리 포트(테스트 주입용). 기본: 실제 브라우저 */
  notificationPorts?: NotificationPorts;
}

/**
 * 앱 셸: 사이드바(라우트 설정 데이터) + 전역 배너 + 본문(`Outlet`) + 빠른 이동 + 도움말 + 전역 단축키.
 * 상단바·하단 도크는 없다. 화면별 로직은 모르며 `Outlet`에 라우트가 끼워진다.
 */
export function Shell({ routes, groups = DEFAULT_ROUTE_GROUPS, platform, notificationPorts }: ShellProps) {
  const { ws } = useApi();
  const ports = useMemo(() => notificationPorts ?? createBrowserPorts(), [notificationPorts]);
  // 상호작용 연동 부분이 꺼져 있으면 전역 상호작용 구독(배지·문서 제목·알림 원천)도 만들지 않는다.
  const interactions = useLinkPart(LINK_PART_IDS.chatInteractionCard);
  return (
    <UnsavedProvider>
      <EscapeProvider>
        <CommandsProvider>
          <PageTitleProvider>
            <ProjectsProvider>
              <PendingInteractionsProvider ws={ws} enabled={interactions.visible}>
                <ShellInner routes={routes} groups={groups} ports={ports} platform={platform ?? detectPlatform(typeof navigator === "undefined" ? undefined : navigator.platform)} />
              </PendingInteractionsProvider>
            </ProjectsProvider>
          </PageTitleProvider>
        </CommandsProvider>
      </EscapeProvider>
    </UnsavedProvider>
  );
}

function ShellInner({ routes, groups, platform, ports }: { routes: readonly RouteDef[]; groups: readonly RouteGroupDef[]; platform: KeyPlatform; ports: NotificationPorts }) {
  const navigate = useNavigate();
  // 서버 모듈이 꺼서 쓸 수 없는 화면: 사이드바·빠른 이동에서 빼고, `g` 키는 이동 대신 안내만 한다.
  const { met: openRoutes, unmet: offRoutes } = useRequiresPartition(routes);
  const navigable = useMemo(() => routes.filter((r) => !offRoutes.includes(r)), [routes, offRoutes]);
  const interactions = useLinkPart(LINK_PART_IDS.chatInteractionCard);
  const location = useLocation();
  const { ws } = useApi();
  const targetRoutes = useMemo<TargetRoutes>(() => ({ conversations: routeServing(routes, ROUTE_ROLES.conversations)?.path, runs: routeServing(routes, ROUTE_ROLES.runs)?.path }), [routes]);
  const toast = useToast();
  const { theme, setTheme } = useTheme();
  const pending = usePendingInteractions();
  const sidebar = useSidebarState(useStorage());
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const settings = useWorkspaceSettings();
  const projects = useProjects();
  const overrides = settings.data?.value.ui?.keybindings ?? undefined;

  const pendingRoute = routes.find((r) => r.badgeSource === "pendingInteractions");
  const jumpToPending = useCallback(() => {
    if (!interactions.visible) {
      toast({ tone: "info", text: m.linkPart.interactionsOff });
      return;
    }
    const oldest = pending.items.find((i) => i.conversation_id != null);
    if (oldest === undefined || pendingRoute === undefined) {
      toast({ tone: "info", text: m.pending.none });
      return;
    }
    void navigate(`${pendingRoute.path}/${encodeURIComponent(oldest.conversation_id as string)}`);
  }, [pending.items, pendingRoute, navigate, toast, interactions.visible]);

  const cycleTheme = useCallback(() => {
    setTheme(nextTheme(theme));
  }, [theme, setTheme]);

  const openSwitcher = useCallback(() => {
    if (projects.enabled) projects.setSwitcherOpen(true);
  }, [projects]);

  const defaults = useMemo<ShortcutDef[]>(
    () => [
      { id: "palette.open", scope: "global", keys: "Mod+K", titleKey: "shortcuts.paletteOpen", modifierRequired: true, run: () => setPaletteOpen(true) },
      ...gotoShortcuts(navigable, (route) => void navigate(route.path)),
      ...gotoShortcuts(offRoutes, (route) => toast({ tone: "info", text: m.nav.disabledToast(lookupMessage(route.titleKey)), durationMs: 3000 })),
      { id: "pending.jump", scope: "global", keys: "Alt+J", titleKey: "shortcuts.pendingJump", modifierRequired: true, run: jumpToPending },
      { id: "sidebar.toggle", scope: "global", keys: "Mod+Shift+B", titleKey: "shortcuts.sidebarToggle", modifierRequired: true, run: sidebar.toggle },
      { id: "help.open", scope: "global", keys: "?", titleKey: "shortcuts.helpOpen", run: () => setHelpOpen(true) },
      // 프로젝트 전환기 단축키(키는 데이터). 프로젝트 기능이 꺼져 있으면 아무 일도 하지 않는다.
      ...(projects.enabled ? PROJECT_SHORTCUT_DEFS.map((d): ShortcutDef => ({ ...d, scope: "global", modifierRequired: true, run: openSwitcher })) : []),
    ],
    [navigable, offRoutes, navigate, toast, jumpToPending, sidebar.toggle, openSwitcher, projects.enabled],
  );

  const commands = useMemo<CommandDef[]>(
    () => [
      { id: "theme.cycle", titleKey: "palette.actions.themeCycle", run: cycleTheme },
      { id: "sidebar.toggle", titleKey: "palette.actions.sidebarToggle", run: sidebar.toggle, shortcut: formatKeyCombo("Mod+Shift+B", platform) },
      { id: "pending.jump", titleKey: "palette.actions.jumpPending", run: jumpToPending, shortcut: formatKeyCombo("Alt+J", platform) },
      ...(projects.enabled
        ? [
            { id: "project.switch", titleKey: "palette.actions.projectSwitch", run: openSwitcher, shortcut: formatKeyCombo(PROJECT_SHORTCUT_DEFS[0].keys, platform) },
            ...(projects.current === null ? [] : [{ id: "project.all", titleKey: "palette.actions.projectAll", run: () => projects.setCurrent(null) }]),
            { id: "project.manage", titleKey: "palette.actions.projectManage", run: () => void navigate(`${routeServing(routes, ROUTE_ROLES.settings)?.path ?? "/"}${SETTINGS_PROJECTS_HASH}`) },
            { id: "project.new", titleKey: "palette.actions.projectNew", run: () => projects.requestCreate() },
          ]
        : []),
    ],
    [cycleTheme, sidebar.toggle, jumpToPending, platform, projects, openSwitcher, navigate, routes],
  );
  useRegisterCommands(commands);

  const environment = useMemo(() => ({ defaultKeys: Object.fromEntries(defaults.map((d) => [d.id, d.keys])), platform }), [defaults, platform]);
  return (
    <ShortcutEnvironmentContext.Provider value={environment}>
    <NotificationsProvider
      ws={ws}
      settings={settings.data?.value.ui?.notifications}
      ports={ports}
      pathname={location.pathname}
      navigate={(path) => void navigate(path)}
      pathFor={(target) => targetPath(target, targetRoutes)}
      isViewing={(pathname, target) => isViewingTarget(pathname, target, targetRoutes)}
    >
    <ShortcutProvider defaults={defaults} {...(overrides ? { overrides } : {})} platform={platform} onWarn={import.meta.env.DEV ? undefined : null}>
      <ShellFrame
        routes={routes}
        groups={groups}
        openRoutes={openRoutes}
        offRoutes={offRoutes}
        platform={platform}
        sidebar={sidebar}
        paletteOpen={paletteOpen}
        setPaletteOpen={setPaletteOpen}
        helpOpen={helpOpen}
        setHelpOpen={setHelpOpen}
      />
    </ShortcutProvider>
    </NotificationsProvider>
    </ShortcutEnvironmentContext.Provider>
  );
}

interface FrameProps {
  routes: readonly RouteDef[];
  groups: readonly RouteGroupDef[];
  /** 서버 모듈이 켜서 쓸 수 있는 화면 */
  openRoutes: readonly RouteDef[];
  /** 서버 모듈이 꺼서 쓸 수 없는 화면 */
  offRoutes: readonly RouteDef[];
  platform: KeyPlatform;
  sidebar: ReturnType<typeof useSidebarState>;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  helpOpen: boolean;
  setHelpOpen: (open: boolean) => void;
}

function ShellFrame({ routes, groups, openRoutes, offRoutes, platform, sidebar, paletteOpen, setPaletteOpen, helpOpen, setHelpOpen }: FrameProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const storage = useStorage();
  const [startOpen, setStartOpen] = useState(false);
  const { ws } = useApi();
  const connection = useConnectionStatus(ws);
  const banner = useConnectionBanner(ws);
  const pending = usePendingInteractions();
  const pwaUpdate = usePwaUpdate();
  const hasUnsaved = useHasUnsaved();
  const titleOverride = usePageTitleOverride();
  const titleSuffix = usePageTitleSuffix();
  const mainRef = useRef<HTMLElement>(null);
  const [confirmUpdate, setConfirmUpdate] = useState(false);

  const active = activeRoute(location.pathname, routes);
  const { state: modulesState } = useModules();
  useEscapeLayer(sidebar.drawer, () => sidebar.setCollapsed(true));

  // 문서 제목: (n) 화면 · Agent Console
  const screenTitle = titleOverride ?? (active === undefined ? m.app.name : lookupMessage(active.titleKey));
  useEffect(() => {
    document.title = composeDocumentTitle({ screen: screenTitle, app: m.app.name, pending: pending.count, suffix: titleSuffix });
  }, [screenTitle, pending.count, titleSuffix]);

  // 최근 이동(빠른 이동의 빈 질의 상태)
  useEffect(() => {
    if (active === undefined || offRoutes.includes(active)) return;
    const rest = location.pathname.slice(active.path.length).replace(/^\//, "");
    const entry = { path: location.pathname, label: rest === "" ? lookupMessage(active.titleKey) : `${lookupMessage(active.titleKey)} / ${decodeURIComponent(rest)}` };
    const cur = readJson<{ path: string; label: string }[]>(storage, RECENT_KEY, []);
    storage.set(RECENT_KEY, JSON.stringify([entry, ...cur.filter((r) => r.path !== entry.path)].slice(0, RECENT_MAX)));
  }, [location.pathname, active, offRoutes, storage]);
  // 팔레트를 열 때 저장된 목록을 읽는다(꺼진 화면의 항목은 뺀다)
  const recent = useMemo(
    () => readJson<{ path: string; label: string }[]>(storage, RECENT_KEY, []).filter((r) => !offRoutes.some((off) => off === activeRoute(r.path, routes))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [storage, paletteOpen, offRoutes, routes],
  );

  const hasUnsavedRef = useRef(hasUnsaved);
  useEffect(() => {
    hasUnsavedRef.current = hasUnsaved;
  });
  // 새 버전 알림: 닫을 때까지 남는 토스트. 저장 안 된 변경이 있으면 확인을 거친다.
  const applyUpdate = pwaUpdate.apply;
  useEffect(() => {
    if (!pwaUpdate.available) return;
    toast({
      tone: "info",
      text: m.pwa.updateAvailable,
      durationMs: TOAST_FOREVER_MS,
      action: { label: m.pwa.updateNow, onClick: () => (hasUnsavedRef.current ? setConfirmUpdate(true) : applyUpdate()) },
    });
  }, [pwaUpdate.available, toast, applyUpdate]);

  const badgeSources = useMemo<Record<string, SidebarBadge>>(
    () => ({ pendingInteractions: { count: pending.count, label: m.sidebar.pendingBadge(pending.count) } }),
    [pending.count],
  );
  const badges = useMemo(() => {
    const out: Record<string, SidebarBadge | undefined> = {};
    for (const r of openRoutes) if (r.badgeSource !== null) out[r.id] = badgeSources[r.badgeSource];
    return out;
  }, [openRoutes, badgeSources]);

  const go = useCallback((path: string) => void navigate(path), [navigate]);
  const settingsRoute = routeServing(routes, ROUTE_ROLES.settings);
  const modulesHref = settingsRoute === undefined ? undefined : `${settingsRoute.path}#modules`;
  // 꺼진 화면의 `g` 이동 키는 도움말 표에서 뺀다(보이지 않는 키를 설명하지 않는다)
  const hiddenGotoIds = useMemo(() => new Set(offRoutes.map((r) => gotoCommandId(r.id))), [offRoutes]);
  // 툴팁에 덧붙일 단축키: 실제 적용 중인 키(설정이 덮어쓴 값 포함)
  const effective = useEffectiveShortcuts();
  const shortcutHint = useCallback(
    (commandId: string) => {
      const keys = effective.find((e) => e.id === commandId)?.keys;
      return keys === undefined || keys === "" ? undefined : splitKeySequence(keys).map((k) => formatKeyCombo(k, platform)).join(" ");
    },
    [effective, platform],
  );

  return (
    <div className="app-shell" data-collapsed={sidebar.collapsed ? "true" : "false"} data-drawer={sidebar.drawer ? "true" : "false"}>
      <a
        className="app-skip"
        href="#app-main"
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        {m.app.skipToMain}
      </a>
      <div className="app-sidebar-slot">
        <AppSidebar
          routes={openRoutes}
          groups={groups}
          shortcutHint={shortcutHint}
          activeId={active !== undefined && openRoutes.includes(active) ? active.id : undefined}
          loadingItems={modulesState.phase === "loading"}
          badges={badges}
          collapsed={sidebar.collapsed}
          onCollapsedChange={sidebar.setCollapsed}
          onNavigate={(route) => {
            void navigate(route.path);
            if (sidebar.drawer) sidebar.setCollapsed(true);
          }}
          onOpenQuickNav={() => setPaletteOpen(true)}
          onOpenHelp={() => setHelpOpen(true)}
          headerSlot={<UsageIndicator routes={openRoutes} host={INDICATOR_HOSTS.sidebarHeader} collapsed={sidebar.collapsed} />}
          footerSlot={
            <>
              <SidebarProjectRegion rail={sidebar.collapsed} />
              <UsageIndicator routes={openRoutes} host={INDICATOR_HOSTS.sidebarFooter} collapsed={sidebar.collapsed} />
            </>
          }
        />
      </div>
      {sidebar.drawer ? <div className="app-drawer-backdrop" aria-hidden="true" onClick={() => sidebar.setCollapsed(true)} /> : null}
      <div className="app-content">
        <ConnectionBanner view={banner.view} onRetry={banner.retry} onReload={banner.reload} />
        <GlobalBanners />
        <main id="app-main" ref={mainRef} className="app-main" aria-label={m.app.mainLabel} tabIndex={-1}>
          <PendingAnnouncer count={pending.count} />
          <Outlet />
        </main>
      </div>
      <UsageIndicator routes={openRoutes} host={INDICATOR_HOSTS.float} />
      <QuickNav open={paletteOpen} onClose={() => setPaletteOpen(false)} routes={openRoutes} recent={recent} go={go} />
      <ModuleNotices modulesHref={modulesHref} navigate={go} />
      <HelpDialog
        open={helpOpen}
        connectionNote={m.connection.line(m.connection.state[connection], m.connection.note)}
        onClose={() => setHelpOpen(false)}
        scope={active?.id}
        extraScopes={active?.shortcutScopes ?? []}
        hiddenIds={hiddenGotoIds}
        platform={platform}
        onShowStart={() => {
          setHelpOpen(false);
          setStartOpen(true);
        }}
        onReplayHints={() => {
          resetHints(storage);
          toast({ tone: "success", text: m.shortcuts.replayHintsDone });
        }}
      />
      <StartGuideDialog open={startOpen} onClose={() => setStartOpen(false)} />
      <Dialog
        open={confirmUpdate}
        title={m.pwa.updateConfirmTitle}
        onClose={() => setConfirmUpdate(false)}
        actions={
          <>
            <Button onClick={() => setConfirmUpdate(false)}>{m.common.cancel}</Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirmUpdate(false);
                applyUpdate();
              }}
            >
              {m.pwa.updateConfirmYes}
            </Button>
          </>
        }
      >
        <p className="ac-text">{m.pwa.updateConfirmBody}</p>
      </Dialog>
    </div>
  );
}

/** 응답 대기 건수 변화를 스크린리더에 알린다(polite). 화면에는 보이지 않는다. */
function PendingAnnouncer({ count }: { count: number }): ReactNode {
  return (
    <div className="ac-sr-only" role="status" aria-live="polite">
      {count > 0 ? m.pending.live(count) : ""}
    </div>
  );
}
