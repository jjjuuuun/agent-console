import type { ShortcutDef } from "@agent-console/ui";

/**
 * 라우트 설정 한 항목(`docs/design/screens.md` 2.2). 사이드바·빠른 이동·도움말의 `g` 단축키 표·문서 제목이
 * 모두 이 배열에서 생성된다. 화면 컴포넌트와의 연결은 `routes.tsx`의 `routeId → 페이지` 표 하나뿐이다.
 */
export interface RouteDef {
  id: string;
  /** 시작 경로. 하위 경로도 이 항목을 활성으로 본다(접두 일치) */
  path: string;
  /** `messages`의 점 표기 키 → 사이드바 라벨·문서 제목·페이지 헤더 제목 */
  titleKey: string;
  /** 아이콘 레지스트리 이름 */
  icon: string;
  /** 빈 상태 스팟에 쓸 아이콘 이름(없으면 `icon`) */
  emptyIcon?: string;
  /** 배지 값을 주는 소스 이름 또는 null. 소스 이름 → 숫자는 `useBadgeSources`가 안다 */
  badgeSource: string | null;
  /** `g` 다음에 누를 한 글자(기본값. 설정 `ui.keybindings`가 덮어쓴다) */
  gotoKey: string | null;
  /**
   * `main` = 사이드바 주 메뉴, `footer` = 주 메뉴 아래 고정 줄(글자 있는 목적지, 예: 설정),
   * `bottom` = 하단 도구줄(아이콘만, 접힘 상태와 같은 모양).
   */
  position: "main" | "footer" | "bottom";
  /** 사이드바 묶음 id(`RouteGroupDef.id`). 비었거나 모르는 값이면 제목 없는 맨 앞 묶음 */
  group?: string;
  /** 로고 클릭·`/` 진입의 첫 화면. 여럿이면 앞의 것, 없으면 첫 `main` 항목 */
  home?: boolean;
  /** 이전 경로(북마크 호환). 하위 경로는 그대로 이어 붙여 옮긴다 */
  redirects?: readonly string[];
  /** 이 라우트 안의 하위 화면이 쓰는 단축키 범위(도움말이 `id`와 함께 보여 준다) */
  shortcutScopes?: readonly string[];
  /**
   * 이 라우트가 맡은 역할(예: `definition:graph`, `runs`). 기능 코드는 라우트 id가 아니라 역할로 화면을 찾는다
   * (`routeServing`). id를 바꾸거나 다른 라우트로 역할을 옮겨도 링크가 깨지지 않는다.
   */
  serves?: string;
  /**
   * 이 화면이 켜져 있으려면 서버에서 켜져 있어야 하는 모듈 id 또는 역할(모두 만족해야 한다, 비면 항상 켜짐).
   * 만족하지 못하면 사이드바·빠른 이동·`g` 단축키에서 빠지고, 주소로 들어오면 안내 화면이 나온다.
   * 모듈이 바뀌어도 화면 규칙이 안 바뀌도록 모듈 id보다 역할을 쓰는 것이 좋다(`docs/design/screen-modules.md` 1.3).
   */
  requires?: readonly string[];
}

/** 사이드바 묶음 한 종류(제목은 `messages` 점 표기 키). 순서 = 사이드바 표시 순서. */
export interface RouteGroupDef {
  id: string;
  titleKey: string;
}

/** 기본 묶음 3개. 이것도 데이터다(라우트의 `group`이 id로 가리킨다). */
export const DEFAULT_ROUTE_GROUPS: readonly RouteGroupDef[] = [
  { id: "config", titleKey: "nav.groups.config" },
  { id: "run", titleKey: "nav.groups.run" },
  { id: "observe", titleKey: "nav.groups.observe" },
];

/** 역할을 맡은 첫 라우트. 없으면 undefined. */
export function routeServing(routes: readonly RouteDef[], role: string): RouteDef | undefined {
  return routes.find((r) => r.serves === role);
}

/** 기본 라우트 9개. 이것도 데이터이며 사용자가 다르게 원하면 이 배열만 고친다. */
export const DEFAULT_ROUTES: readonly RouteDef[] = [
  { id: "chat", serves: "conversations", requires: ["conversations"], path: "/chat", titleKey: "nav.chat", icon: "chat", badgeSource: "pendingInteractions", gotoKey: "c", position: "main", group: "run", home: true },
  { id: "teams", serves: "definition:graph", requires: ["definitions:graph"], path: "/teams", titleKey: "nav.teams", icon: "teams", badgeSource: null, gotoKey: "t", position: "main", group: "config", redirects: ["/graphs"] },
  { id: "agents", serves: "definition:agent", requires: ["definitions:agent"], path: "/agents", titleKey: "nav.agents", icon: "agents", badgeSource: null, gotoKey: "a", position: "main", group: "config" },
  { id: "resources", serves: "definition:resource", requires: ["definitions:resource"], path: "/resources", titleKey: "nav.resources", icon: "resources", badgeSource: null, gotoKey: "r", position: "main", group: "config" },
  { id: "runs", serves: "runs", requires: ["runs"], path: "/runs", titleKey: "nav.runs", icon: "runs", badgeSource: null, gotoKey: "h", position: "main", group: "run", shortcutScopes: ["run-detail"] },
  { id: "memory", serves: "memory", requires: ["memory"], path: "/memory", titleKey: "nav.memory", icon: "memory", badgeSource: null, gotoKey: "m", position: "main", group: "run" },
  { id: "usage", serves: "usage", requires: ["usage"], path: "/usage", titleKey: "nav.usage", icon: "usage", badgeSource: null, gotoKey: "u", position: "main", group: "observe" },
  { id: "logs", serves: "logs", requires: ["logs"], path: "/logs", titleKey: "nav.logs", icon: "logs", badgeSource: null, gotoKey: "l", position: "main", group: "observe", shortcutScopes: ["logs-session", "logs-search", "logs-dashboard"] },
  { id: "settings", serves: "settings", requires: [], path: "/settings", titleKey: "nav.settings", icon: "settings", badgeSource: null, gotoKey: "s", position: "bottom" },
];

/** 로고 클릭·루트(`/`) 진입 시 가는 첫 화면: `home` 표시가 있는 첫 항목, 없으면 첫 `main` 항목, 없으면 첫 항목. */
export function homeRoute(routes: readonly RouteDef[]): RouteDef | undefined {
  return routes.find((r) => r.home === true) ?? routes.find((r) => r.position === "main") ?? routes[0];
}

function underPath(pathname: string, path: string): boolean {
  return pathname === path || pathname.startsWith(path.endsWith("/") ? path : `${path}/`);
}

/** 현재 경로에 해당하는 라우트(가장 긴 접두 일치). 없으면 undefined. */
export function activeRoute(pathname: string, routes: readonly RouteDef[]): RouteDef | undefined {
  let best: RouteDef | undefined;
  for (const r of routes) if (underPath(pathname, r.path) && (best === undefined || r.path.length > best.path.length)) best = r;
  return best;
}

/** `g` 단축키 명령 id. 설정 `ui.keybindings`의 키가 된다. */
export function gotoCommandId(routeId: string): string {
  return `goto.${routeId}`;
}

/** 명령 id가 `g` 이동 명령이면 라우트 id, 아니면 undefined. */
export function routeIdOfGoto(commandId: string): string | undefined {
  return commandId.startsWith("goto.") ? commandId.slice("goto.".length) : undefined;
}

/** `gotoKey`가 겹치는 라우트 id 묶음(설정 시점 점검용). 한 글자가 아닌 값도 문제로 본다. */
export function gotoKeyProblems(routes: readonly RouteDef[]): { duplicates: string[][]; invalid: string[] } {
  const byKey = new Map<string, string[]>();
  const invalid: string[] = [];
  for (const r of routes) {
    if (r.gotoKey === null) continue;
    if (Array.from(r.gotoKey).length !== 1) invalid.push(r.id);
    byKey.set(r.gotoKey, [...(byKey.get(r.gotoKey) ?? []), r.id]);
  }
  return { duplicates: [...byKey.values()].filter((ids) => ids.length > 1), invalid };
}

/** 이동 단축키 정의(`g` + 글자). 핸들러는 호출자가 준다. */
export function gotoShortcuts(routes: readonly RouteDef[], go: (route: RouteDef) => void): ShortcutDef[] {
  return routes
    .filter((r): r is RouteDef & { gotoKey: string } => r.gotoKey !== null)
    .map((r) => ({
      id: gotoCommandId(r.id),
      scope: "global",
      keys: `g ${r.gotoKey}`,
      titleKey: r.titleKey,
      run: () => go(r),
    }));
}

/** 이전 경로 → 새 경로 접두 치환. 해당 없으면 undefined. */
export function redirectTarget(pathname: string, routes: readonly RouteDef[]): string | undefined {
  for (const r of routes) {
    for (const old of r.redirects ?? []) {
      if (underPath(pathname, old)) return r.path + pathname.slice(old.length);
    }
  }
  return undefined;
}
