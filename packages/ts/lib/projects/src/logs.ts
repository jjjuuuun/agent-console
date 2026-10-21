/** 프로젝트 → 로그 필터. 로그 필터 `project`는 묶음 id의 쉼표 목록이다(design §UX-P.3). */
import type { Project } from "@agent-console/contracts/projects";

export interface ProjectLogFilter {
  /** 로그 질의에 합칠 필터. 연결된 묶음이 없으면 undefined(로그를 거르지 않는다). */
  filter: { project: string } | undefined;
  /** 연결된 로그 묶음 id. */
  groups: string[];
  /** false면 "로그 연결 안 됨 — [연결]" 안내를 보인다. 프로젝트가 없으면(모든 프로젝트) true(안내 불필요). */
  linked: boolean;
}

/** 쉼표가 들어간 id는 쉼표 목록에 못 넣으므로 거른다. */
function cleanGroups(groups: readonly string[] | undefined): string[] {
  const seen = new Set<string>();
  for (const g of groups ?? []) {
    const t = g.trim();
    if (t !== "" && !t.includes(",")) seen.add(t);
  }
  return [...seen];
}

/**
 * 프로젝트의 로그 필터. `project`가 null/undefined(모든 프로젝트)이면 거르지 않는다.
 * @param project 현재 프로젝트 정의(`log_projects` 사용)
 */
export function logFilterFor(project: Pick<Project, "log_projects"> | null | undefined): ProjectLogFilter {
  if (project === null || project === undefined) return { filter: undefined, groups: [], linked: true };
  const groups = cleanGroups(project.log_projects);
  if (groups.length === 0) return { filter: undefined, groups, linked: false };
  return { filter: { project: groups.join(",") }, groups, linked: true };
}

/** 이미 있는 로그 필터에 프로젝트 필터를 덮어 합친다(프로젝트 쪽 값이 `project` 키를 대체). 연결 없으면 그대로. */
export function applyLogFilter<F extends Record<string, unknown>>(
  base: F,
  project: Pick<Project, "log_projects"> | null | undefined,
): F & { project?: string } {
  const { filter } = logFilterFor(project);
  return filter === undefined ? base : { ...base, ...filter };
}
