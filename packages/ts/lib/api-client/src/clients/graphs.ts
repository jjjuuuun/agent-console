/** 팀 구성(그래프) 정의 REST. */
import type {
  BundlePreview,
  DefinitionVersion,
  DraftGraphRequest,
  DraftNodeRequest,
  EffectiveSettings,
  Graph,
  GraphSummary,
  Issue,
  TeamPlanSummary,
  VersionedGraph,
} from "@agent-console/contracts";
import { enc, query, type RestIo } from "../io";

/** `listGraphs` 질의. */
export interface ListGraphsParams {
  /** false면 검증 요약(`validation`)을 계산하지 않는다(null). */
  validate?: boolean;
}

export interface GraphsClient {
  /** 팀 구성 목록. 요약마다 `validation`(검증 요약)이 오며 `validate: false`면 서버가 계산하지 않아 null이다. */
  listGraphs(params?: ListGraphsParams): Promise<GraphSummary[]>;
  /** 같은 id가 있으면 `already_exists`(409). */
  createGraph(graph: Graph): Promise<VersionedGraph>;
  getGraph(id: string): Promise<VersionedGraph>;
  /**
   * 그래프 저장. `versionHash`(마지막으로 받은 `version_hash`)를 `If-Match`로 보낸다.
   * 다른 곳에서 먼저 저장했으면 `ApiError`(status 412, `versionConflict` 노출).
   */
  updateGraph(id: string, graph: Graph, versionHash: string): Promise<VersionedGraph>;
  deleteGraph(id: string): Promise<void>;
  /** 팀 구성 복제(서버에서). 응답은 새 그래프(`VersionedGraph`, 임시 가정). */
  duplicateGraph(id: string, target: { id: string; name: string }): Promise<VersionedGraph>;
  getNodeEffectiveSettings(graphId: string, nodeId: string): Promise<EffectiveSettings>;
  /** 그 노드가 실행 때 받을 실행 묶음 미리보기와 묶음 경고(`BundlePreview`). */
  getNodeBundlePreview(graphId: string, nodeId: string): Promise<BundlePreview>;
  /** 저장하지 않은 초안 기준 유효 설정(저장하지 않음, 비밀은 서버가 가림). */
  previewDraftEffectiveSettings(request: DraftNodeRequest): Promise<EffectiveSettings>;
  /** 저장하지 않은 초안 기준 묶음 미리보기. */
  previewDraftBundle(request: DraftNodeRequest): Promise<BundlePreview>;
  /** 저장된 팀 구성의 계획 요약(입구·답변 자리·상호작용 허용). */
  getGraphPlan(id: string): Promise<TeamPlanSummary>;
  /** 저장하지 않은 초안의 계획 요약. */
  planDraftGraph(request: DraftGraphRequest): Promise<TeamPlanSummary>;
  /** `graph`를 생략하면 저장된 그래프를 검증한다. */
  validateGraph(id: string, graph?: Graph): Promise<Issue[]>;
  /** 버전 목록(`content` 없음). */
  listGraphVersions(id: string): Promise<DefinitionVersion[]>;
  /** 한 버전의 그래프 문서(`content`). 없으면 404. */
  getGraphVersion(id: string, versionHash: string): Promise<DefinitionVersion>;
}

export function createGraphsClient(io: RestIo): GraphsClient {
  return {
    listGraphs: (params) => io.request("GET", `/graphs${query(params)}`),
    createGraph: (graph) => io.request("POST", "/graphs", { body: graph }),
    getGraph: (id) => io.request("GET", `/graphs/${enc(id)}`),
    updateGraph: (id, graph, versionHash) => io.request("PUT", `/graphs/${enc(id)}`, { body: graph, headers: { "If-Match": versionHash } }),
    deleteGraph: (id) => io.request("DELETE", `/graphs/${enc(id)}`),
    duplicateGraph: (id, target) => io.request("POST", `/graphs/${enc(id)}/duplicate`, { body: target }),
    getNodeEffectiveSettings: (g, n) => io.request("GET", `/graphs/${enc(g)}/nodes/${enc(n)}/effective-settings`),
    getNodeBundlePreview: (g, n) => io.request("GET", `/graphs/${enc(g)}/nodes/${enc(n)}/bundle-preview`),
    previewDraftEffectiveSettings: (req) => io.request("POST", "/graphs/effective-settings", { body: req }),
    previewDraftBundle: (req) => io.request("POST", "/graphs/bundle-preview", { body: req }),
    getGraphPlan: (id) => io.request("GET", `/graphs/${enc(id)}/plan`),
    planDraftGraph: (req) => io.request("POST", "/graphs/plan", { body: req }),
    validateGraph: (id, graph) => io.request("POST", `/graphs/${enc(id)}/validate`, graph === undefined ? {} : { body: graph }),
    listGraphVersions: (id) => io.request("GET", `/graphs/${enc(id)}/versions`),
    getGraphVersion: (id, hash) => io.request("GET", `/graphs/${enc(id)}/versions/${enc(hash)}`),
  };
}
