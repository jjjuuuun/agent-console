import type { ResourceSummary } from "@agent-console/contracts";
import type { GroupByDef, SortDef } from "@agent-console/list-arrange";
import { folderGroupDef, labelsGroupDef, modifiedSortDef, nameSortDef, projectGroupDef } from "../library";

/** 리소스 목록의 묶는 기준 데이터: 종류별(기본)·폴더·라벨·프로젝트. 묶음 이름은 종류 제목(디스크립터)이라 머리 순서도 제목순이다. */
export function resourceGroupDefs(typeTitle: (typeId: string) => string, noProjects: string): GroupByDef<ResourceSummary>[] {
  return [
    { id: "type", titleKey: "group.type", read: (r) => (r.type === "" ? [] : [typeTitle(r.type)]) },
    folderGroupDef<ResourceSummary>(),
    labelsGroupDef<ResourceSummary>(),
    projectGroupDef<ResourceSummary>(noProjects),
  ];
}

/** 정렬 데이터: 이름순, 최근 수정(요약에 `saved_at`이 있을 때만). */
export const resourceSortDefs: SortDef<ResourceSummary>[] = [nameSortDef<ResourceSummary>(), modifiedSortDef<ResourceSummary>()];
