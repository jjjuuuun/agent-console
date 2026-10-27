import type { GraphSummary } from "@agent-console/contracts";
import type { GroupByDef, SortDef } from "@agent-console/list-arrange";
import { folderGroupDef, labelsGroupDef, modifiedSortDef, nameSortDef, projectGroupDef } from "../library";

export type SortDirection = "asc" | "desc";
/** 정렬마다 처음 방향(열 머리를 처음 누를 때). */
export const DEFAULT_DIRECTION: Readonly<Record<string, SortDirection>> = { name: "asc", modified: "desc" };

/** 팀 구성 목록의 묶는 기준 데이터: 폴더(기본)·라벨·프로젝트. */
export function teamGroupDefs(noProjects: string): GroupByDef<GraphSummary>[] {
  return [folderGroupDef<GraphSummary>(), labelsGroupDef<GraphSummary>(), projectGroupDef<GraphSummary>(noProjects)];
}

/** 정렬 데이터: 이름, 최근 수정(`saved_at`이 있을 때만). 방향은 열 머리 단추가 정한다. */
export function teamSortDefs(dirs: Readonly<Record<string, SortDirection>>): SortDef<GraphSummary>[] {
  return [nameSortDef<GraphSummary>(dirs["name"] === "desc"), modifiedSortDef<GraphSummary>(dirs["modified"] !== "asc")];
}
