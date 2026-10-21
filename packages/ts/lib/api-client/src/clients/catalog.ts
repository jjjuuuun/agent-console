/** 서버가 알려 주는 종류 목록(노드·엣지·백엔드·위임 전략·상호작용·리소스 종류·병합 전략). 전부 읽기 전용. */
import type {
  BackendDescriptor,
  BackendProbeRequest,
  BackendProbeResult,
  BackendReadiness,
  ConditionOperatorDescriptor,
  DelegationStrategyDescriptor,
  EdgeTypeDescriptor,
  InteractionKindDescriptor,
  MergeStrategyInfo,
  ModelInfo,
  NodeTypeDescriptor,
  PortSpec,
  ResourceTypeDescriptor,
} from "@agent-console/contracts";
import { enc, type RestIo } from "../io";

export interface CatalogClient {
  listNodeTypes(): Promise<NodeTypeDescriptor[]>;
  resolvePorts(nodeTypeId: string, config: Record<string, unknown>): Promise<PortSpec>;
  listEdgeTypes(): Promise<EdgeTypeDescriptor[]>;
  listBackends(): Promise<BackendDescriptor[]>;
  listBackendModels(backendId: string): Promise<ModelInfo[]>;
  /** 모든 백엔드의 정적 점검 상태(모델 호출 없음). 모듈이 꺼져 있으면 404. */
  listBackendStatuses(): Promise<BackendReadiness[]>;
  /** 백엔드 하나의 정적 점검 상태(다시 확인). */
  getBackendStatus(backendId: string): Promise<BackendReadiness>;
  /** 연결 테스트: 실제 호출이 일어난다(비용). 미지원이면 409 `backend.probe_unsupported`. */
  probeBackend(backendId: string, request?: BackendProbeRequest): Promise<BackendProbeResult>;
  listDelegationStrategies(): Promise<DelegationStrategyDescriptor[]>;
  /** 조건 연산자 목록(X22). 조건 편집 위젯이 연산자 선택·값 입력 모양을 이것으로 그린다. */
  listConditionOperators(): Promise<ConditionOperatorDescriptor[]>;
  listInteractionKinds(): Promise<InteractionKindDescriptor[]>;
  listResourceTypes(): Promise<ResourceTypeDescriptor[]>;
  /** `settings_merge`에 쓸 수 있는 병합 전략 이름(서버 표: 기본 + 플러그인). */
  listMergeStrategies(): Promise<MergeStrategyInfo[]>;
}

export function createCatalogClient(io: RestIo): CatalogClient {
  return {
    listNodeTypes: () => io.request("GET", "/node-types"),
    resolvePorts: (id, config) => io.request("POST", `/node-types/${enc(id)}/ports`, { body: { config } }),
    listEdgeTypes: () => io.request("GET", "/edge-types"),
    listBackends: () => io.request("GET", "/backends"),
    listBackendModels: (id) => io.request("GET", `/backends/${enc(id)}/models`),
    listBackendStatuses: () => io.request("GET", "/backends/status"),
    getBackendStatus: (id) => io.request("GET", `/backends/${enc(id)}/status`),
    probeBackend: (id, request) => io.request("POST", `/backends/${enc(id)}/probe`, { body: request ?? {} }),
    listDelegationStrategies: () => io.request("GET", "/delegation-strategies"),
    listConditionOperators: () => io.request("GET", "/condition-operators"),
    listInteractionKinds: () => io.request("GET", "/interaction-kinds"),
    listResourceTypes: () => io.request("GET", "/resource-types"),
    listMergeStrategies: () => io.request("GET", "/merge-strategies"),
  };
}
