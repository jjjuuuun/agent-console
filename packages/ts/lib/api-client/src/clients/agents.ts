/** 에이전트 정의 REST. */
import type { Agent, DefinitionReference, EffectiveSettings, RunEvent } from "@agent-console/contracts";
import { enc, ifMatch, query, withHeaders, type RestIo, type Versioned } from "../io";

export interface AgentsClient {
  listAgents(): Promise<Agent[]>;
  getAgent(id: string): Promise<Agent>;
  createAgent(agent: Agent): Promise<Agent>;
  /** `versionHash`를 주면 `If-Match`로 보낸다(선택). */
  updateAgent(id: string, agent: Agent, versionHash?: string): Promise<Agent>;
  deleteAgent(id: string, versionHash?: string): Promise<void>;
  /** `getAgent`와 같되 `ETag`(`version_hash`)를 함께 돌려준다(저장 때 `If-Match`로 쓴다). */
  getAgentVersioned(id: string): Promise<Versioned<Agent>>;
  /** `updateAgent`와 같되 새 `ETag`를 함께 돌려준다. 412면 `ApiError.versionConflict`. */
  updateAgentVersioned(id: string, agent: Agent, versionHash?: string): Promise<Versioned<Agent>>;
  /** 이 에이전트를 쓰는 곳(팀 구성 등). */
  listAgentUsages(id: string): Promise<DefinitionReference[]>;
  getAgentEffectiveSettings(id: string): Promise<EffectiveSettings>;
  /** 에이전트별 최근 이벤트. 계약 모델이 없어 `RunEvent[]`로 가정(임시, 1R.14 확정 대기). */
  getAgentActivity(id: string, limit?: number): Promise<RunEvent[]>;
}

export function createAgentsClient(io: RestIo): AgentsClient {
  return {
    listAgents: () => io.request("GET", "/agents"),
    getAgent: (id) => io.request("GET", `/agents/${enc(id)}`),
    createAgent: (agent) => io.request("POST", "/agents", { body: agent }),
    updateAgent: (id, agent, hash) => io.request("PUT", `/agents/${enc(id)}`, { body: agent, ...withHeaders(ifMatch(hash)) }),
    deleteAgent: (id, hash) => io.request("DELETE", `/agents/${enc(id)}`, withHeaders(ifMatch(hash))),
    getAgentVersioned: (id) => io.requestVersioned("GET", `/agents/${enc(id)}`),
    updateAgentVersioned: (id, agent, hash) =>
      io.requestVersioned("PUT", `/agents/${enc(id)}`, { body: agent, ...withHeaders(ifMatch(hash)) }),
    listAgentUsages: (id) => io.request("GET", `/agents/${enc(id)}/usages`),
    getAgentEffectiveSettings: (id) => io.request("GET", `/agents/${enc(id)}/effective-settings`),
    getAgentActivity: (id, limit) => io.request("GET", `/agents/${enc(id)}/activity${query({ limit })}`),
  };
}
