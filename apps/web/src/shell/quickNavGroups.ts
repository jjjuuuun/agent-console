import type { RestClient } from "@agent-console/api-client";
import type { CommandGroup, CommandItem } from "@agent-console/ui";
import { lookupMessage } from "../app/messages";
import { messages as m } from "../app/messages";
import type { CommandDef } from "./commands";
import { ROUTE_ROLES } from "../features/library/paths";
import type { RouteDef } from "./routeConfig";

/** 빠른 이동의 목록 그룹 한 종류. 라우트 id로 이동 경로를 정하고, 행 모양은 `toItem`이 만든다. */
export interface QuickGroupSource<T = unknown> {
  id: string;
  /** `messages` 점 표기 키(그룹 제목) */
  titleKey: string;
  /** 항목을 열 라우트의 역할(라우트 설정의 `serves`). 맡은 라우트가 없으면 그룹을 숨긴다 */
  serves: string;
  /** 질의 키에 쓰는 이름(화면의 같은 목록과 캐시를 공유하려면 같은 이름·인자를 쓴다) */
  listName: string;
  load: (rest: RestClient) => Promise<readonly T[]>;
  toItem: (row: T) => { id: string; label: string; hint?: string; pending?: number };
}

function source<T>(s: QuickGroupSource<T>): QuickGroupSource {
  return s as unknown as QuickGroupSource;
}

/** 목록 그룹 표. 새 목록(예: 위키)은 한 줄을 더하면 된다. */
export const QUICK_GROUP_SOURCES: readonly QuickGroupSource[] = [
  source({
    id: "conversations",
    titleKey: "palette.groups.conversations",
    serves: ROUTE_ROLES.conversations,
    listName: "conversations",
    load: (rest) => rest.listConversations({ archived: false }),
    toItem: (c) => ({ id: c.id, label: c.title !== undefined && c.title !== "" ? c.title : c.id, ...(c.pending_interactions ? { pending: c.pending_interactions } : {}) }),
  }),
  source({
    id: "teams",
    titleKey: "palette.groups.teams",
    serves: ROUTE_ROLES.graph,
    listName: "graphs",
    load: (rest) => rest.listGraphs(),
    toItem: (g) => ({ id: g.id, label: g.name, hint: g.id }),
  }),
  source({
    id: "agents",
    titleKey: "palette.groups.agents",
    serves: ROUTE_ROLES.agent,
    listName: "agents",
    load: (rest) => rest.listAgents(),
    toItem: (a) => ({ id: a.id, label: a.name, ...(a.role ? { hint: a.role } : {}) }),
  }),
  source({
    id: "resources",
    titleKey: "palette.groups.resources",
    serves: ROUTE_ROLES.resource,
    listName: "resources",
    load: (rest) => rest.listResources(),
    toItem: (r) => ({ id: r.id, label: r.name, hint: r.type }),
  }),
  source({
    id: "runs",
    titleKey: "palette.groups.runs",
    serves: ROUTE_ROLES.runs,
    listName: "runs",
    load: (rest) => rest.listRuns({ limit: 20 }),
    toItem: (r) => ({ id: r.id, label: r.id, hint: r.status }),
  }),
];

export interface QuickGroupResult {
  source: QuickGroupSource;
  rows: readonly unknown[] | undefined;
  loading: boolean;
}

export interface BuildGroupsArgs {
  routes: readonly RouteDef[];
  results: readonly QuickGroupResult[];
  commands: readonly CommandDef[];
  recent: readonly { path: string; label: string }[];
  query: string;
  go: (path: string) => void;
  icon?: (name: string) => CommandItem["icon"];
}

/**
 * 빠른 이동 그룹을 만든다(순수). 화면(라우트 데이터) → 대화·팀 구성·에이전트·리소스·실행(목록 API) → 동작(등록된 명령).
 * 질의가 비면 "최근 이동"을 맨 앞에 둔다. 목록이 실패한 그룹(rows 없음)은 생략한다.
 */
export function buildQuickGroups(args: BuildGroupsArgs): CommandGroup[] {
  const { routes, results, commands, recent, query, go, icon } = args;
  const groups: CommandGroup[] = [];
  if (query.trim() === "" && recent.length > 0) {
    groups.push({ id: "recent", title: m.palette.groups.recent, items: recent.slice(0, 5).map((r) => ({ id: `recent:${r.path}`, label: r.label, hint: r.path, run: () => go(r.path) })) });
  }
  groups.push({
    id: "screens",
    title: m.palette.groups.screens,
    items: routes.map((r) => ({ id: `screen:${r.id}`, label: lookupMessage(r.titleKey), ...(icon ? { icon: icon(r.icon) } : {}), run: () => go(r.path) })),
  });
  for (const res of results) {
    const route = routes.find((r) => r.serves === res.source.serves);
    if (route === undefined || res.rows === undefined) continue;
    const items = res.rows
      .map((row) => res.source.toItem(row))
      .sort((a, b) => (b.pending ?? 0) - (a.pending ?? 0))
      .map<CommandItem>((it) => ({
        id: `${res.source.id}:${it.id}`,
        label: it.label,
        ...(it.hint === undefined ? {} : { hint: it.hint }),
        ...(it.pending ? { badge: m.palette.pending } : {}),
        run: () => go(`${route.path}/${encodeURIComponent(it.id)}`),
      }));
    groups.push({ id: res.source.id, title: lookupMessage(res.source.titleKey), items });
  }
  if (commands.length > 0) {
    groups.push({
      id: "actions",
      title: m.palette.groups.actions,
      items: commands.map((c) => ({ id: `action:${c.id}`, label: lookupMessage(c.titleKey), ...(c.shortcut === undefined ? {} : { shortcut: c.shortcut }), run: c.run })),
    });
  }
  return groups;
}
