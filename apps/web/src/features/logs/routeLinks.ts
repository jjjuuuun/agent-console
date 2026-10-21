import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";

/** 다른 화면으로 가는 링크의 경로: 라우트 설정 데이터에서 역할(`serves`)로 찾는다. 맡은 라우트가 없으면 "/". */
export function pathForRole(role: string): string {
  return routeServing(DEFAULT_ROUTES, role)?.path ?? "/";
}

/** 링크가 가리키는 다른 화면의 역할 이름(라우트 설정의 `serves` 값). */
export const LINK_ROLES = { runs: "runs", usage: "usage", settings: "settings" } as const;
