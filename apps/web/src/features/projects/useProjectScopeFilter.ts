import { useCallback } from "react";
import { filterByScope, normalizeScope, type Scope } from "@agent-console/projects";
import { useProjects } from "./ProjectsContext";

/**
 * 편집 중인 정의의 범위에 맞춰 선택지(팔레트·선택기)를 거르는 함수를 돌려준다.
 * 기준 프로젝트 = 편집 중인 항목의 프로젝트, 공용이면 현재 프로젝트. 공용 + 기준 프로젝트의 항목만 남고,
 * 기준이 없거나(모든 프로젝트 보기의 공용 항목) 프로젝트 기능이 꺼져 있으면 그대로 둔다. 보기 범위 선택(공용만 등)은 따르지 않는다.
 * @param editing 편집 중인 항목의 `project` 값(null/undefined = 공용)
 */
export function useProjectScopeFilter(editing: Scope): <T>(items: readonly T[], scopeOf: (item: T) => Scope) => T[] {
  const p = useProjects();
  const target = normalizeScope(editing) ?? p.current;
  const known = p.projects.map((x) => x.id).join("\u0000");
  return useCallback(
    <T,>(items: readonly T[], scopeOf: (item: T) => Scope): T[] =>
      !p.enabled || target === null
        ? [...items]
        : filterByScope(items, target, { mode: "shared_and_project", knownProjects: known === "" ? [] : known.split("\u0000"), scopeOf }),
    [p.enabled, target, known],
  );
}
