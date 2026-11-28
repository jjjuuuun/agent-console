import type { ArchitectureGroupView, ArchitectureProfileList, ArchitectureView } from "@agent-console/contracts";

type Translate = (text: string) => string;

const opt = (value: string | null | undefined, tr: Translate): string | null | undefined => (typeof value === "string" ? tr(value) : value);

function groups(list: ArchitectureGroupView[] | null | undefined, tr: Translate): ArchitectureGroupView[] | null | undefined {
  return list?.map((g) => (typeof g.label === "string" ? { ...g, label: tr(g.label) } : g));
}

/**
 * 구조도 응답에서 서버가 준 글자(제목·영역·칸 제목/설명·그룹·연결 라벨·부분 수집 이유·비고·사용 불가 항목·이유)를
 * 화면 언어로 옮긴다. 아이디·좌표·지표 값은 그대로다. 번역이 없는 글자는 원문 그대로(`tr` 규칙).
 */
export function localizeArchitectureView(view: ArchitectureView, tr: Translate): ArchitectureView {
  return {
    ...view,
    ...(view.title !== undefined ? { title: tr(view.title) } : {}),
    ...(view.zones ? { zones: view.zones.map((z) => ({ ...z, label: opt(z.label, tr), description: opt(z.description, tr) })) } : {}),
    ...(view.cells
      ? {
          cells: view.cells.map((c) => ({
            ...c,
            label: tr(c.label),
            description: opt(c.description, tr),
            partial_reason: opt(c.partial_reason, tr),
            ...(c.groups !== undefined ? { groups: groups(c.groups, tr) } : {}),
            ...(c.unavailable ? { unavailable: c.unavailable.map((u) => ({ ...u, item: tr(u.item), ...(u.reason !== undefined ? { reason: tr(u.reason) } : {}) })) } : {}),
          })),
        }
      : {}),
    ...(view.edges ? { edges: view.edges.map((e) => ({ ...e, label: opt(e.label, tr), partial_reason: opt(e.partial_reason, tr) })) } : {}),
    ...(view.unavailable ? { unavailable: view.unavailable.map((u) => ({ ...u, item: tr(u.item), ...(u.reason !== undefined ? { reason: tr(u.reason) } : {}) })) } : {}),
    ...(view.notes ? { notes: view.notes.map((n) => ({ ...n, message: tr(n.message) })) } : {}),
  };
}

/** 프로필 목록의 프로필 이름을 옮긴다(사용자가 만든 프로필 이름은 번역이 없어 그대로 나온다). */
export function localizeArchitectureProfiles(list: ArchitectureProfileList, tr: Translate): ArchitectureProfileList {
  return list.profiles ? { ...list, profiles: list.profiles.map((p) => (typeof p.title === "string" ? { ...p, title: tr(p.title) } : p)) } : list;
}
