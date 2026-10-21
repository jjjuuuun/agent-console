import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation, type RouteObject } from "react-router";
import { lookupMessage } from "../app/messages";
import { useGraphList } from "../features/library";
import { ROUTE_ROLES } from "../features/library/paths";
import { PROJECTS_SECTION_ID, ProjectsSection } from "../features/projects";
import { RouteGate, useModules, useRequiresPartition } from "../modules";
import { lazyScreen } from "./lazyScreen";
import { NotFoundScreen } from "./NotFoundScreen";
import { PlaceholderScreen } from "./PlaceholderScreen";
import { DEFAULT_ROUTES, homeRoute, redirectTarget, routeServing, type RouteDef, type RouteGroupDef } from "./routeConfig";
import { Shell } from "./Shell";

// 화면은 모두 처음 열 때 불러온다(그래프·마크다운·타임라인·터미널 등 무거운 패키지가 첫 번들에 들어가지 않게).
const ChatScreen = lazyScreen(() => import("../features/chat/ChatScreen"), "ChatScreen");
const AgentsScreen = lazyScreen(() => import("../features/agents/AgentsScreen"), "AgentsScreen");
const ResourcesScreen = lazyScreen(() => import("../features/resources/ResourcesScreen"), "ResourcesScreen");
const TeamEditorPage = lazyScreen(() => import("../features/teams/TeamEditorPage"), "TeamEditorPage");
const TeamListPage = lazyScreen(() => import("../features/teams/TeamListPage"), "TeamListPage");
const SettingsScreen = lazyScreen(() => import("../features/settings/SettingsScreen"), "SettingsScreen");
const RunsListScreen = lazyScreen(() => import("../features/runs/RunsListScreen"), "RunsListScreen");
const RunDetailScreen = lazyScreen(() => import("../features/runs/RunDetailScreen"), "RunDetailScreen");
const UsageScreen = lazyScreen(() => import("../features/usage/UsageScreen"), "UsageScreen");
const LogsLayout = lazyScreen(() => import("../features/logs"), "LogsLayout");
const LogsIndexRedirect = lazyScreen(() => import("../features/logs"), "LogsIndexRedirect");
const SessionsPage = lazyScreen(() => import("../features/logs"), "SessionsPage");
const SessionDetailPage = lazyScreen(() => import("../features/logs"), "SessionDetailPage");
const SearchPage = lazyScreen(() => import("../features/logs"), "SearchPage");
const DashboardsPage = lazyScreen(() => import("../features/logs"), "DashboardsPage");

/** 모든 화면 번들을 미리 내려받는다(유휴 시간 선로딩, 테스트에서 첫 이동 지연 제거). */
export function preloadScreens(): Promise<unknown> {
  return Promise.all([ChatScreen, AgentsScreen, ResourcesScreen, TeamEditorPage, TeamListPage, SettingsScreen, RunsListScreen, RunDetailScreen, UsageScreen, LogsLayout, SessionsPage, SessionDetailPage, SearchPage, DashboardsPage].map((s) => s.preload()));
}

/** 라우트 id → 그 화면의 하위 라우트(라우트 경로 기준 상대 경로). 새 화면은 여기에 한 줄 등록한다. */
export type PageTable = Readonly<Record<string, (route: RouteDef) => RouteObject[]>>;

/** 목록 화면 자리표시(index + 상세 경로 하나). 실제 화면이 들어오면 이 항목을 바꾼다. */
function placeholderPages(detailParam: string): (route: RouteDef) => RouteObject[] {
  return (route) => [
    { index: true, element: <PlaceholderScreen route={route} /> },
    { path: `:${detailParam}`, element: <PlaceholderScreen route={route} detail={detailParam} /> },
  ];
}

/**
 * 기본 페이지 표.
 * - 1R.23: `teams`(목록 `/teams`, 편집기 `/teams/:id`), `agents`, `resources`
 * - 1R.24: `chat`(`/chat`, `/chat/:conversationId`)
 * - 1R.25: `runs`(`/runs`, `/runs/:id`), `usage`
 * - 4R.17: `logs`(`/logs/sessions[/:session]`, `/logs/search`, `/logs/dashboards[/:id]`; `/logs`는 마지막에 본 탭으로 이동)
 */
/** 설정 화면에서 본문을 다른 기능이 그리는 섹션(프로젝트 관리). 해당 섹션은 서버에서 그 기능이 꺼지면 목록에서 사라진다. */
const SETTINGS_SECTION_RENDERERS: Readonly<Record<string, () => ReactNode>> = {
  [PROJECTS_SECTION_ID]: () => <ProjectsSection />,
};

export const DEFAULT_PAGES: PageTable = {
  // 목록과 상세가 한 화면이라 하나의 선택적 경로로 둔다(이동해도 목록 상태가 유지된다)
  chat: () => [{ path: ":conversationId?", element: <ChatScreen /> }],
  teams: (route) => [
    { index: true, element: <TeamListPage basePath={route.path} /> },
    { path: ":id", element: <TeamEditorPage basePath={route.path} /> },
  ],
  agents: (route) => [{ path: ":id?", element: <AgentsScreen basePath={route.path} /> }],
  resources: (route) => [{ path: ":id?", element: <ResourcesScreen basePath={route.path} /> }],
  runs: () => [
    { index: true, element: <RunsListScreen /> },
    { path: ":id", element: <RunDetailScreen /> },
  ],
  usage: () => [{ index: true, element: <UsageScreen /> }],
  // 하위 화면 셋은 한 층(수집 알림 구독 하나)을 공유한다. 탭 줄·헤더는 각 화면이 `LogsPageFrame`으로 그린다.
  logs: () => [
    {
      element: <LogsLayout />,
      children: [
        { index: true, element: <LogsIndexRedirect /> },
        { path: "sessions", element: <SessionsPage /> },
        { path: "sessions/:session", element: <SessionDetailPage /> },
        { path: "search", element: <SearchPage /> },
        { path: "dashboards/:id?", element: <DashboardsPage /> },
      ],
    },
  ],
  settings: () => [{ index: true, element: <SettingsScreen sectionRenderers={SETTINGS_SECTION_RENDERERS} /> }],
};

/** 이전 경로(`/graphs/…`)를 새 경로로 옮긴다(하위 경로·쿼리·해시 유지). */
function RedirectPrefix({ routes }: { routes: readonly RouteDef[] }) {
  const { pathname, search, hash } = useLocation();
  const target = redirectTarget(pathname, routes);
  return target === undefined ? <NotFoundScreen homePath={homeRoute(routes)?.path ?? "/"} /> : <Navigate to={`${target}${search}${hash}`} replace />;
}

/** 설정 화면의 기능 모듈 섹션 주소(안내 화면의 [기능 목록 보기]). 설정을 맡은 라우트가 없으면 undefined. */
function modulesHref(routes: readonly RouteDef[]): string | undefined {
  const settings = routeServing(routes, ROUTE_ROLES.settings);
  return settings === undefined ? undefined : `${settings.path}#modules`;
}

/**
 * 라우트 하나의 문지기: 서버 모듈이 `requires`를 만족하면 화면(`Outlet`), 아니면 꺼진 기능 안내 화면.
 * 주소는 그대로 둔다(리다이렉트하지 않음).
 */
function RouteLayout({ route, routes }: { route: RouteDef; routes: readonly RouteDef[] }) {
  const { met } = useRequiresPartition(routes);
  const home = homeRoute(met.filter((r) => r.id !== route.id));
  return (
    <RouteGate requires={route.requires ?? []} screenTitle={lookupMessage(route.titleKey)} modulesHref={modulesHref(routes) ?? "/"} home={home === undefined ? undefined : { title: lookupMessage(home.titleKey), path: home.path }}>
      <Outlet />
    </RouteGate>
  );
}

/**
 * `/` 진입: 켜진 첫 화면으로 보낸다. 팀 구성이 0개이고 구성 역할(`definition:graph`) 화면이 켜져 있으면 그 화면으로 보낸다(첫 팀 만들기).
 * 모듈 목록·팀 구성 목록을 받기 전에는 아무것도 그리지 않는다(켜졌다 꺼지는 화면으로, 또는 채팅으로 잘못 갔다 돌아오지 않게).
 * 목록을 못 받으면(오류) 팀 수를 모르므로 기본 첫 화면으로 간다.
 */
function HomeRedirect({ routes }: { routes: readonly RouteDef[] }) {
  const { state } = useModules();
  const { met } = useRequiresPartition(routes);
  const graphs = useGraphList();
  if (state.phase === "loading") return null;
  const home = homeRoute(met);
  const builder = routeServing(met, ROUTE_ROLES.graph);
  if (builder !== undefined && graphs.isPending) return null;
  const noTeams = graphs.data !== undefined && graphs.data.length === 0;
  const target = noTeams && builder !== undefined ? builder : home;
  return target === undefined ? <NotFoundScreen homePath="/" /> : <Navigate to={target.path} replace />;
}

export interface BuildRoutesOptions {
  routes?: readonly RouteDef[];
  /** 사이드바 묶음(기본: `DEFAULT_ROUTE_GROUPS`) */
  groups?: readonly RouteGroupDef[];
  pages?: PageTable;
  platform?: "mac" | "other";
}

/** 앱의 라우트 설정(브라우저/메모리 라우터가 공유). 라우트 설정 데이터와 페이지 표에서 만든다. */
export function buildAppRoutes({ routes = DEFAULT_ROUTES, groups, pages = DEFAULT_PAGES, platform }: BuildRoutesOptions = {}): RouteObject[] {
  const home = homeRoute(routes);
  const redirects = routes.flatMap((r) => (r.redirects ?? []).map((old): RouteObject => ({ path: `${old.replace(/^\//, "")}/*`, element: <RedirectPrefix routes={routes} /> })));
  const screens = routes.map(
    (r): RouteObject => ({
      path: r.path.replace(/^\//, ""),
      element: <RouteLayout route={r} routes={routes} />,
      children: (pages[r.id] ?? placeholderPages("id"))(r),
    }),
  );
  return [
    {
      element: <Shell routes={routes} {...(groups ? { groups } : {})} {...(platform ? { platform } : {})} />,
      children: [
        ...(home === undefined ? [] : [{ index: true, element: <HomeRedirect routes={routes} /> } satisfies RouteObject]),
        ...redirects,
        ...screens,
        { path: "*", element: <NotFoundScreen homePath={home?.path ?? "/"} /> },
      ],
    },
  ];
}
