import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { routePath } from "../library";
import { RUNS_ROLE, WIKI_PARAMS, WIKI_ROLE, WIKI_RULES_ROLE } from "./wikiConfig";

type Query = Readonly<Record<string, string | number | null | undefined>>;

function queryString(query: Query): string {
  const q = Object.entries(query)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return q === "" ? "" : `?${q}`;
}

/** 위키 목록 화면 경로(라우트 `serves` 역할로 찾는다). */
export const wikiListPath = (): string => routePath(WIKI_ROLE);

/** 한 위키의 경로(+ 쿼리 객체). 값이 없는 쿼리는 뺀다. */
export function wikiPath(id: string, query: Query = {}): string {
  return `${wikiListPath()}/${encodeURIComponent(id)}${queryString(query)}`;
}

/** 위키의 페이지 하나를 여는 경로(`path=` 인코딩). */
export function wikiPagePath(id: string, path: string, query: Query = {}): string {
  return wikiPath(id, { [WIKI_PARAMS.path]: path, ...query });
}

/**
 * 위키 규칙 화면 경로(그 역할을 맡은 라우트가 없으면 undefined). `id`가 있으면 그 규칙, `projectId`가 있으면 그 프로젝트 사본(`?prj=`)을 연다.
 */
export function wikiRulesPath(id?: string, projectId?: string | null): string | undefined {
  const base = routeServing(DEFAULT_ROUTES, WIKI_RULES_ROLE)?.path;
  if (base === undefined) return undefined;
  const path = id === undefined ? base : `${base}/${encodeURIComponent(id)}`;
  return projectId === undefined || projectId === null ? path : `${path}${queryString({ prj: projectId })}`;
}

/** 실행 상세 경로(실행 화면이 없으면 undefined). */
export function runPath(runId: string): string | undefined {
  const base = routeServing(DEFAULT_ROUTES, RUNS_ROLE)?.path;
  return base === undefined ? undefined : `${base}/${encodeURIComponent(runId)}`;
}

/** 스킴 대상 열 화면(`LabelDisplayTarget`)의 모양. 링크(`WikiLink.scheme_target`)와 그래프 노드가 같다. */
export interface SchemeTargetLike {
  role: string;
  id_from: string;
  query?: string | null | undefined;
}

/**
 * 스킴 대상 → 앱 경로. 역할을 맡은 라우트가 없거나 꺼져 있으면(`routeOn`이 false) undefined.
 * `id`가 빈 문자열이면 그 화면의 목록 경로를 돌려준다. `query`의 `{value}`는 id로 바꾼다.
 */
export function schemeTargetHref(target: SchemeTargetLike, id: string, routeOn: (role: string) => boolean): string | undefined {
  const base = routeServing(DEFAULT_ROUTES, target.role)?.path;
  if (base === undefined || !routeOn(target.role)) return undefined;
  if (id === "") return base;
  const q = target.query === undefined || target.query === null || target.query === "" ? "" : `?${target.query.replace(/\{value\}/g, encodeURIComponent(id))}`;
  return `${base}/${encodeURIComponent(id)}${q}`;
}
