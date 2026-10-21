import { byNumber, byText, folderOf, usableUnlessAllDistinct, type GroupByDef, type SortDef } from "@agent-console/list-arrange";
import type { Agent } from "@agent-console/contracts";

/** 묶음 "묶지 않음"을 뜻하는 저장 id. */
export const GROUP_NONE = "none";
/** 속성 키로 묶는 기준 id(키는 보기 상태의 `attrKey`). */
export const GROUP_ATTRIBUTE = "attribute";

const text = (v: unknown): string[] => (typeof v === "string" && v.trim() !== "" ? [v] : []);
/** 스칼라 값(문자열·숫자·불리언)을 문자열로. 객체·배열·null은 값 없음. */
const scalar = (v: unknown): string[] => (typeof v === "string" || typeof v === "number" || typeof v === "boolean" ? text(String(v)) : []);

export interface AgentGroupInput {
  /** 속성 기준에서 읽을 `attributes` 최상위 키(비면 값 없음). */
  attrKey: string;
  /** 역할 기준을 쓸 수 없을 때 보일 사유(문구). */
  roleReason: string;
}

/** 에이전트 목록의 묶는 기준 데이터. 화면은 이 표를 그대로 `ListViewMenu`·`groupItems`에 넘긴다. */
export function agentGroupDefs({ attrKey, roleReason }: AgentGroupInput): GroupByDef<Agent>[] {
  const role = (a: Agent) => text(a.role);
  return [
    { id: "folder", titleKey: "group.folder", tree: true, read: (a) => [folderOf(a.attributes) ?? ""] },
    { id: "labels", titleKey: "group.labels", multi: true, read: (a) => a.labels ?? [] },
    { id: "role", titleKey: "group.role", read: role, usable: usableUnlessAllDistinct(role, roleReason) },
    { id: "backend", titleKey: "group.backend", read: (a) => text(a.backend) },
    { id: "model", titleKey: "group.model", read: (a) => text(a.model) },
    { id: GROUP_ATTRIBUTE, titleKey: "group.attribute", read: (a) => (attrKey.trim() === "" ? [] : scalar(a.attributes?.[attrKey.trim()])) },
  ];
}

/** 정렬 데이터. `usage`는 사용 팀 수가 있을 때만 쓸 수 있다(정의-팀 연동이 꺼지면 숨김). */
export function agentSortDefs(usage: ((id: string) => number | undefined) | undefined): SortDef<Agent>[] {
  const defs: SortDef<Agent>[] = [{ id: "name", titleKey: "sort.name", compare: byText((a) => a.name) }];
  if (usage !== undefined) {
    const nameCmp = byText<Agent>((a) => a.name);
    const byUsage = byNumber<Agent>((a) => usage(a.id), true);
    defs.push({ id: "usage", titleKey: "sort.usage", compare: (a, b) => byUsage(a, b) || nameCmp(a, b) });
  }
  return defs;
}

/** 속성 키 후보: 항목들의 `attributes` 최상위 키 중 스칼라 값이 있는 것(`ui` 제외), 이름순. */
export function attributeKeys(agents: readonly Agent[]): string[] {
  const keys = new Set<string>();
  for (const a of agents) for (const [k, v] of Object.entries(a.attributes ?? {})) if (k !== "ui" && scalar(v).length > 0) keys.add(k);
  return [...keys].sort((x, y) => x.localeCompare(y, "ko"));
}

/** 이미 있는 폴더 경로들(중복 없음, 이름순; 이동 후보). */
export function folderPaths(agents: readonly Agent[]): string[] {
  const set = new Set<string>();
  for (const a of agents) {
    const f = folderOf(a.attributes);
    if (f === undefined) continue;
    const parts = f.split("/");
    for (let i = 1; i <= parts.length; i++) set.add(parts.slice(0, i).join("/"));
  }
  return [...set].sort((x, y) => x.localeCompare(y, "ko"));
}
