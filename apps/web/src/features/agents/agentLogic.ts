import type { RestClient, Versioned } from "@agent-console/api-client";
import { getContractSchema, type Agent, type RunEvent } from "@agent-console/contracts";
import type { SchemaNode } from "../../lib/schemaTools";

/** `AgentSettings` 스키마의 속성 이름(에이전트 문서에서 설정에 해당하는 키). 코드에 필드 목록을 두지 않는다. */
export function agentSettingsKeys(): string[] {
  const props = (getContractSchema("AgentSettings") as SchemaNode)["properties"];
  return typeof props === "object" && props !== null ? Object.keys(props) : [];
}

/** 에이전트를 읽는다. 서버는 저장 원문(지정한 필드만)을 주므로 그대로 쓴다. 버전은 `ETag`. */
export async function loadAgent(rest: RestClient, id: string): Promise<Versioned<Agent>> {
  return rest.getAgentVersioned(id);
}

/** 저장하고, 서버가 저장한 것은 보낸 문서와 같으므로(지정한 필드만) 그대로 돌려준다. */
export async function saveAgent(rest: RestClient, agent: Agent, versionHash: string | undefined): Promise<Versioned<Agent>> {
  const saved = await rest.updateAgentVersioned(agent.id, agent, versionHash);
  return { value: agent, version_hash: saved.version_hash };
}

/** 에이전트 문서에서 설정 필드만(`hide`에 든 키는 제외). */
export function settingsOf(agent: Agent, hide: readonly string[]): Record<string, unknown> {
  const keys = agentSettingsKeys().filter((k) => !hide.includes(k));
  return Object.fromEntries(Object.entries(agent).filter(([k]) => keys.includes(k)));
}

/** 설정 폼이 돌려준 값으로 에이전트의 설정 필드를 바꾼다(숨긴 필드와 식별 필드는 그대로). */
export function withSettings(agent: Agent, next: Record<string, unknown>, hide: readonly string[]): Agent {
  const keys = new Set(agentSettingsKeys().filter((k) => !hide.includes(k)));
  const kept = Object.fromEntries(Object.entries(agent).filter(([k]) => !keys.has(k)));
  return { ...kept, ...next } as Agent;
}

/** 에이전트 목록 필터. 검색어는 이름·역할·설명·id 부분 일치(대소문자 무시). */
export function filterAgents(agents: readonly Agent[], query: string, used: "all" | "used" | "unused", usageCount: (id: string) => number | undefined): Agent[] {
  const q = query.trim().toLowerCase();
  return agents.filter((a) => {
    if (q !== "" && !`${a.name} ${a.role ?? ""} ${a.description ?? ""} ${a.id}`.toLowerCase().includes(q)) return false;
    if (used === "all") return true;
    const n = usageCount(a.id);
    return n === undefined ? true : used === "used" ? n > 0 : n === 0;
  });
}

/** 이름 오름차순(한국어 로케일). */
export function sortByName<T extends { name: string }>(items: readonly T[]): T[] {
  return [...items].sort((a, b) => a.name.localeCompare(b.name, "ko"));
}

export interface ActivityGroup {
  runId: string;
  firstTs: number;
  lastTs: number;
  count: number;
  lastType: string;
}

/** 이벤트(최신순)를 실행별로 묶는다. 묶음은 가장 최근 이벤트 순. */
export function groupActivity(events: readonly RunEvent[]): ActivityGroup[] {
  const groups = new Map<string, ActivityGroup>();
  for (const e of events) {
    const g = groups.get(e.run_id);
    if (g === undefined) groups.set(e.run_id, { runId: e.run_id, firstTs: e.ts, lastTs: e.ts, count: 1, lastType: e.type });
    else {
      g.count += 1;
      g.firstTs = Math.min(g.firstTs, e.ts);
      if (e.ts > g.lastTs) {
        g.lastTs = e.ts;
        g.lastType = e.type;
      }
    }
  }
  return [...groups.values()].sort((a, b) => b.lastTs - a.lastTs);
}
