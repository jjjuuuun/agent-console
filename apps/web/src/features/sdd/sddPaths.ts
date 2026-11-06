import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { routePath } from "../library";
import { SDD_ROLE, SDD_TEMPLATES_ROLE } from "./sddConfig";

/** 스펙 화면 경로(라우트 `serves` 역할로 찾는다). */
export const specsPath = (): string => routePath(SDD_ROLE);
/** 한 스펙의 경로(+ 쿼리 객체). 값이 없는 쿼리는 뺀다. */
export function specPath(id: string, query: Readonly<Record<string, string | number | null | undefined>> = {}): string {
  const q = Object.entries(query)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return `${specsPath()}/${encodeURIComponent(id)}${q === "" ? "" : `?${q}`}`;
}
/** 문서 틀 화면 경로. 그 역할을 맡은 라우트가 없으면 undefined. */
export function specTemplatesPath(): string | undefined {
  return routeServing(DEFAULT_ROUTES, SDD_TEMPLATES_ROLE)?.path;
}
