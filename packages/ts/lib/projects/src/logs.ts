/**
 * 프로젝트 → 로그 필터. 로그 세션은 등록된 프로젝트 폴더에 속하면 `LogSessionSummary.project_id`를 갖고(폴더 포함 관계,
 * 서버가 정한다), 로그 질의 필터 `project`는 그 id(쉼표로 여럿)다. 묶기 규칙·연결(`log_projects`)은 없어졌다(K33-15).
 */

/** 프로젝트 id 또는 id를 가진 객체(`Project`·`ProjectView.project`). */
export type LogProjectRef = string | { id: string } | { project: { id: string } };

export interface ProjectLogFilter {
  /** 로그 질의에 합칠 필터. 프로젝트가 없으면(거르지 않음) undefined. */
  filter: { project: string } | undefined;
  /** 거르는 프로젝트 id. 없으면 null. */
  id: string | null;
}

function idOf(ref: LogProjectRef | null | undefined): string | null {
  if (ref === null || ref === undefined) return null;
  const raw = typeof ref === "string" ? ref : "project" in ref ? ref.project.id : ref.id;
  const t = raw.trim();
  // 쉼표는 필터 목록의 구분자라 id에 들어갈 수 없다.
  return t === "" || t.includes(",") ? null : t;
}

/**
 * 프로젝트의 로그 필터(`project=<id>`). 프로젝트가 없으면(null/undefined) 거르지 않는다.
 * @param project 프로젝트 id 또는 프로젝트 객체
 */
export function logFilterFor(project: LogProjectRef | null | undefined): ProjectLogFilter {
  const id = idOf(project);
  return id === null ? { filter: undefined, id: null } : { filter: { project: id }, id };
}

/** 이미 있는 로그 필터에 프로젝트 필터를 덮어 합친다(프로젝트 쪽 값이 `project` 키를 대체). 프로젝트가 없으면 그대로. */
export function applyLogFilter<F extends Record<string, unknown>>(base: F, project: LogProjectRef | null | undefined): F & { project?: string } {
  const { filter } = logFilterFor(project);
  return filter === undefined ? base : { ...base, ...filter };
}
