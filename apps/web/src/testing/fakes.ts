/**
 * 테스트 전용 가짜 클라이언트·픽스처(앱 코드에서 import하지 않는다).
 * 종류·이름 문자열은 임의 값이며 앱의 어떤 분기에도 쓰이지 않는다.
 */
import { vi } from "vitest";
import type { ConnectionStatus, RestClient, WsClient } from "@agent-console/api-client";
import { ApiError } from "@agent-console/api-client";
import { CONTRACTS_VERSION, type Interaction, type WorkspaceSettings } from "@agent-console/contracts";
import type { ProjectsClient } from "@agent-console/projects";
import type { ApiClients } from "../app/apiClients";

type RestMocks = { [K in keyof RestClient]: ReturnType<typeof vi.fn> };

/** 모든 REST 메서드를 vi.fn으로 가진 가짜. 필요한 것만 덮어쓴다. 설정은 ETag 해시를 갖는다. */
export function createFakeRest(overrides: Partial<Record<keyof RestClient, unknown>> = {}): RestClient & RestMocks {
  let settings: WorkspaceSettings = {};
  let hash = "s1";
  const base: Partial<Record<keyof RestClient, unknown>> = {
    getBootstrap: vi.fn(async () => ({ token: "t", server_version: "9.9.9", contracts_version: CONTRACTS_VERSION })),
    getSettingsVersioned: vi.fn(async () => ({ value: settings, version_hash: hash })),
    putSettingsVersioned: vi.fn(async (next: WorkspaceSettings) => {
      settings = next;
      hash = `s${Number(hash.slice(1)) + 1}`;
      return { value: settings, version_hash: hash };
    }),
    listEdgeTypes: vi.fn(async () => [
      { id: "kind-x", title: "연결 가나" },
      { id: "kind-y", title: "연결 다라" },
    ]),
    listMergeStrategies: vi.fn(async () => [{ id: "strat-a", description: "전략 에이" }, { id: "strat-b" }]),
    listBackendStatuses: vi.fn(async () => []),
    listBackends: vi.fn(async () => [{ id: "be-1", title: "백엔드 하나", config_schema: { type: "object", properties: { opt_z: { type: "string", title: "옵션 제트" } } } }]),
    listConditionOperators: vi.fn(async () => []),
    listDelegationStrategies: vi.fn(async () => [{ id: "dl-1", title: "위임 하나", member_fields: ["model"], max_depth: 1, allows_outgoing_flow: false, member_interaction_kinds: null }]),
    listResourceTypes: vi.fn(async () => []),
    listResources: vi.fn(async () => []),
    listUsageSources: vi.fn(async () => [
      { descriptor: { id: "src-1", title: "출처 하나", trust: "official", description: "공식 출처" }, enabled: false },
      { descriptor: { id: "src-2", title: "출처 둘", trust: "unofficial", description: "비공식 방식" }, enabled: false },
    ]),
    getUsage: vi.fn(async () => ({ windows: [{ source: "src-1", window: "win-q", observed_at: 1 }], rollups: [], generated_at: 1 })),
    getServerInfo: vi.fn(async () => ({ server_version: "9.9.9", contracts_version: CONTRACTS_VERSION, plugins: [{ name: "plug-a", group: "grp", loaded: true }], attributes: { host: "127.0.0.1", port: 8765, workspace: "/ws", allow_remote: false, allowed_origins: ["http://localhost:5173"] } })),
    listAgents: vi.fn(async () => []),
    listGraphs: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    listRuns: vi.fn(async () => []),
  };
  return new Proxy({ ...base, ...overrides } as Record<string, unknown>, {
    get: (target, key: string) => target[key] ?? (target[key] = vi.fn(async () => undefined)),
  }) as never;
}

export interface FakeWs extends WsClient {
  setStatus(status: ConnectionStatus): void;
  /** 구독자에게 상호작용 변화를 보낸다 */
  emitInteraction(interaction: Interaction): void;
  /** 로그 수집 알림(`logs.ingested`)을 구독자에게 보낸다 */
  emitLogs(count: number, sourceIds?: string[]): void;
}

export function createFakeWs(initial: ConnectionStatus = "open"): FakeWs {
  let status = initial;
  const statusListeners = new Set<(s: ConnectionStatus) => void>();
  const interactionListeners = new Set<(i: Interaction) => void>();
  const logListeners = new Set<(p: { count: number; source_ids?: string[] }) => void>();
  return {
    get status() {
      return status;
    },
    connect: vi.fn(),
    close: vi.fn(),
    onStatus(listener: (s: ConnectionStatus) => void) {
      statusListeners.add(listener);
      return () => statusListeners.delete(listener);
    },
    subscribeInteractions(handler: (i: Interaction) => void) {
      interactionListeners.add(handler);
      return { topic: "interactions", unsubscribe: () => interactionListeners.delete(handler) };
    },
    subscribeLogs(handler: (p: { count: number; source_ids?: string[] }) => void) {
      logListeners.add(handler);
      return { topic: "logs", unsubscribe: () => logListeners.delete(handler) };
    },
    subscribe: vi.fn(),
    subscribeRun: vi.fn(),
    subscribeConversation: vi.fn(),
    onMessage: vi.fn(() => () => {}),
    setStatus(next: ConnectionStatus) {
      status = next;
      statusListeners.forEach((l) => l(next));
    },
    emitInteraction(i: Interaction) {
      interactionListeners.forEach((l) => l(i));
    },
    emitLogs(count: number, sourceIds?: string[]) {
      logListeners.forEach((l) => l({ count, ...(sourceIds ? { source_ids: sourceIds } : {}) }));
    },
  } as unknown as FakeWs;
}

/** 모든 메서드가 vi.fn인 가짜 프로젝트 클라이언트. 목록은 기본으로 비어 있다. */
export function createFakeProjects(overrides: Partial<Record<keyof ProjectsClient, unknown>> = {}): ProjectsClient & { [K in keyof ProjectsClient]: ReturnType<typeof vi.fn> } {
  const base: Record<string, unknown> = { listProjects: vi.fn(async () => []), listScopeIssues: vi.fn(async () => []), ...overrides };
  return new Proxy(base, { get: (target, key: string) => target[key] ?? (target[key] = vi.fn(async () => undefined)) }) as never;
}

export function createFakeClients(restOverrides: Partial<Record<keyof RestClient, unknown>> = {}, projectsOverrides: Partial<Record<keyof ProjectsClient, unknown>> = {}) {
  const rest = createFakeRest(restOverrides);
  const ws = createFakeWs();
  const projects = createFakeProjects(projectsOverrides);
  const clients: ApiClients = { rest, projects, ws, meta: { baseUrl: "http://fake.test", serverVersion: "9.9.9", contractsVersion: CONTRACTS_VERSION } };
  return { rest, ws, projects, clients };
}

export function versionConflict(): ApiError {
  return new ApiError(412, { code: "version_conflict", message: "충돌", details: { current_version_hash: "h9", saved_at: 1_700_000_000 } });
}

export function pendingInteraction(id: string, conversationId = "c1", createdAt = 1): Interaction {
  return { id, run_id: "r1", conversation_id: conversationId, node_id: "n", kind: "k-x", status: "pending", created_at: createdAt };
}
