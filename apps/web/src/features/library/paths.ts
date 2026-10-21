import { useRequiresPartition } from "../../modules";
import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { DEFINITION_KINDS } from "./kinds";

/**
 * 라우트가 맡는 역할 이름(`RouteDef.serves`). 기능 코드는 라우트 id가 아니라 이 역할로 화면을 찾는다.
 * 정의 편집 화면의 역할은 `definition:<저장소 kind>`이며 kind는 계약에서 읽는다.
 */
export const ROUTE_ROLES = {
  conversations: "conversations",
  runs: "runs",
  settings: "settings",
  usage: "usage",
  graph: `definition:${DEFINITION_KINDS.graph}`,
  agent: `definition:${DEFINITION_KINDS.agent}`,
  resource: `definition:${DEFINITION_KINDS.resource}`,
} as const;

/** 역할을 맡은 라우트의 경로(라우트 설정 데이터에서). 맡은 라우트가 없으면 "/". 다른 화면으로 가는 링크를 만들 때 쓴다. */
export function routePath(role: string): string {
  return routeServing(DEFAULT_ROUTES, role)?.path ?? "/";
}

/** 정의 종류(저장소 kind) -> 그 정의를 편집하는 화면의 역할. 맡은 라우트가 없으면 undefined. */
export function routeRoleOfKind(kind: string): string | undefined {
  const role = `definition:${kind}`;
  return routeServing(DEFAULT_ROUTES, role) === undefined ? undefined : role;
}

/** 정의 하나를 여는 경로. 종류를 모르면 undefined. */
export function definitionPath(kind: string, id: string): string | undefined {
  const route = routeRoleOfKind(kind);
  return route === undefined ? undefined : `${routePath(route)}/${encodeURIComponent(id)}`;
}

/**
 * 설정 층의 `source`(서버 `layers[].source`)가 가리키는 편집 화면 경로.
 * `종류:id[#노드]` 형태면 그 정의를, 콜론이 없으면 `source`를 라우트 id로 본다. 모르면 undefined.
 */
export function layerSourcePath(source: string | null | undefined): string | undefined {
  if (source === null || source === undefined || source === "") return undefined;
  const colon = source.indexOf(":");
  if (colon < 0) return DEFAULT_ROUTES.some((r) => r.id === source) ? routePath(source) : undefined;
  const kind = source.slice(0, colon);
  const id = source.slice(colon + 1).split("#", 1)[0] ?? "";
  return id === "" ? undefined : definitionPath(kind, id);
}

/**
 * 역할을 맡은 라우트가 지금 켜져 있는가(서버 모듈 기준). 꺼졌으면 그 화면으로 가는 링크·단계·목록 조회를 만들지 않는다.
 * 맡은 라우트가 없거나 모듈 목록을 받기 전에는 켜진 것으로 본다(꺼진 것이 확인된 경우에만 뺀다).
 */
export function useRouteOn(role: string): boolean {
  const { unmet } = useRequiresPartition(DEFAULT_ROUTES);
  return !unmet.some((r) => r.serves === role);
}

/** `useRouteOn`을 여러 역할에 한 번에 쓴다(훅 호출 수가 고정되도록 함수 하나를 돌려준다). */
export function useRoutesOn(): (role: string) => boolean {
  const { unmet } = useRequiresPartition(DEFAULT_ROUTES);
  return (role) => !unmet.some((r) => r.serves === role);
}
