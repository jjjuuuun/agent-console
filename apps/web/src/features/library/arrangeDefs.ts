import { byNumber, byText, folderOf, type GroupByDef, type SortDef, type Usable } from "@agent-console/list-arrange";

/** 정의 요약·정의 공통의 필드 중 묶기·정렬이 읽는 것(없는 필드는 값 없음으로 본다). */
export interface ArrangeableDefinition {
  name: string;
  labels?: string[] | undefined;
  project?: string | null | undefined;
  saved_at?: number | null | undefined;
  attributes?: Record<string, unknown> | undefined;
}

/** 라벨별(여러 묶음에 보임). */
export function labelsGroupDef<T extends ArrangeableDefinition>(): GroupByDef<T> {
  return { id: "labels", titleKey: "group.labels", multi: true, read: (x) => x.labels ?? [] };
}

/**
 * 폴더별(`attributes.ui.folder`, `/` 계층). 목록 응답은 `attributes`를 값이 있을 때만 싣는다(생략 = 없음).
 * 폴더 값이 하나도 없으면 묶음이 생기지 않아 평면으로 보이므로 기준 자체는 늘 고를 수 있다.
 */
export function folderGroupDef<T extends ArrangeableDefinition>(): GroupByDef<T> {
  return { id: "folder", titleKey: "group.folder", tree: true, read: (x) => [folderOf(x.attributes) ?? ""] };
}

/** 이미 있는 폴더 경로들(중간 단계 포함, 중복 없음, 이름순; 이동 후보). */
export function folderPathsOf(items: readonly { attributes?: Record<string, unknown> | undefined }[]): string[] {
  const set = new Set<string>();
  for (const it of items) {
    const f = folderOf(it.attributes);
    if (f === undefined) continue;
    const parts = f.split("/");
    for (let i = 1; i <= parts.length; i++) set.add(parts.slice(0, i).join("/"));
  }
  return [...set].sort((x, y) => x.localeCompare(y, "ko"));
}

/** 프로젝트별. 프로젝트에 속한 항목이 하나도 없으면 쓸 수 없음. */
export function projectGroupDef<T extends ArrangeableDefinition>(noneReason: string): GroupByDef<T> {
  return {
    id: "project",
    titleKey: "group.project",
    read: (x) => (x.project == null || x.project === "" ? [] : [x.project]),
    usable: (items): Usable => (items.some((x) => x.project != null && x.project !== "") ? { ok: true } : { ok: false, reason: noneReason }),
  };
}

/** 이름순 정렬(`desc`면 거꾸로). */
export function nameSortDef<T extends ArrangeableDefinition>(desc = false): SortDef<T> {
  const cmp = byText<T>((x) => x.name);
  return { id: "name", titleKey: "sort.name", compare: desc ? (a, b) => cmp(b, a) : cmp };
}

/** 최근 수정순 정렬(수정 시각이 있는 항목이 하나라도 있을 때만 보인다). 같으면 이름순. */
export function modifiedSortDef<T extends ArrangeableDefinition>(desc = true): SortDef<T> {
  const byTime = byNumber<T>((x) => x.saved_at ?? undefined, desc);
  const byName = byText<T>((x) => x.name);
  return { id: "modified", titleKey: "sort.modified", compare: (a, b) => byTime(a, b) || byName(a, b), available: (items) => items.some((x) => x.saved_at != null) };
}
