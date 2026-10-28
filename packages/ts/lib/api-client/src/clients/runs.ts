/** 실행(Run) REST: 생성·조회·취소·추적·이벤트·위임 집계·이어 가기. */
import type { CreateRunRequest, HandoffMatrix, ResumeOptions, Run, RunEvent, RunSnapshot, RunStatus, Trace } from "@agent-console/contracts";
import type { AssignProjectRequest, AssignProjectResult, ProjectCounts } from "@agent-console/contracts/projects";
import { enc, query, type RestIo } from "../io";

/** GET `/runs` 필터(§R9.5). 값이 없는 키는 보내지 않는다. */
export interface ListRunsParams {
  graph_id?: string;
  conversation_id?: string;
  agent_id?: string;
  status?: RunStatus;
  /** 이 루트 Run 아래 모든 자식 Run(손자 포함, 루트 자신은 빠짐). 없는 id면 빈 목록(404 아님, 5R.13). */
  root?: string;
  /** 그 프로젝트의 Run만(`project_id`, 불투명 문자열). 생략 = 모두. */
  project?: string;
  /** `app` = 앱 저장소에 남은 옛 기록, `project` = 프로젝트 폴더 기록(기본). 프로젝트 기록 DB를 쓰는 서버에서만 뜻이 있다. */
  source?: string;
  limit?: number;
}

/** GET `/runs/handoffs` 필터. 실행 목록 필터와 같은 이름을 쓴다. */
export type HandoffParams = ListRunsParams;

/** GET `/runs/{id}/events` 필터. */
export interface ListRunEventsParams {
  actor?: string;
  /** 이벤트 type 접두(예: `hook.`, `mcp.`). */
  type_prefix?: string;
  /** 이 seq 다음 이벤트만(서버 1R.14). 생략하면 처음부터. */
  since_seq?: number;
}

export interface RunsClient {
  /** `project_id`별 루트 Run 수(`ProjectCounts`: 전체·프로젝트 없음·프로젝트별). */
  getRunProjectCounts(): Promise<ProjectCounts>;
  /** Run을 프로젝트에 넣는다(`ids` 또는 `from_null`). 못 옮긴 것은 결과 `skipped`에 이유와 함께. */
  assignRunsToProject(request: AssignProjectRequest): Promise<AssignProjectResult>;
  createRun(request: CreateRunRequest): Promise<Run>;
  listRuns(params?: ListRunsParams): Promise<Run[]>;
  /** Run 스냅샷. `children`은 직접 자식 Run(만든 순, 서버가 채우면 늘 배열). */
  getRun(id: string): Promise<RunSnapshot>;
  cancelRun(id: string): Promise<Run>;
  getRunTrace(id: string): Promise<Trace>;
  listRunEvents(id: string, params?: ListRunEventsParams): Promise<RunEvent[]>;
  /** 여러 실행의 위임·넘기기 집계. */
  getHandoffs(params?: HandoffParams): Promise<HandoffMatrix>;
  /** 끊긴 노드 목록. 끊기지 않았거나 이미 이어 갔으면 `nodes`가 비어 있다. */
  getResumeOptions(runId: string): Promise<ResumeOptions>;
  /** 고른 노드부터 다시 실행 -> 새 Run(202). 422 `validation_failed`(`details.issues[].node_id`), 409 `run_not_resumable`·`conversation_busy`. */
  resumeRun(runId: string, nodeIds: readonly string[]): Promise<Run>;
}

export function createRunsClient(io: RestIo): RunsClient {
  return {
    getRunProjectCounts: () => io.request("GET", "/runs/project-counts"),
    assignRunsToProject: (request) => io.request("POST", "/runs/assign-project", { body: request }),
    createRun: (req) => io.request("POST", "/runs", { body: req }),
    listRuns: (params) => io.request("GET", `/runs${query(params)}`),
    getRun: (id) => io.request("GET", `/runs/${enc(id)}`),
    cancelRun: (id) => io.request("POST", `/runs/${enc(id)}/cancel`),
    getRunTrace: (id) => io.request("GET", `/runs/${enc(id)}/trace`),
    listRunEvents: (id, params) => io.request("GET", `/runs/${enc(id)}/events${query(params)}`),
    getHandoffs: (params) => io.request("GET", `/runs/handoffs${query(params)}`),
    getResumeOptions: (runId) => io.request("GET", `/runs/${enc(runId)}/resume-options`),
    resumeRun: (runId, nodeIds) => io.request("POST", `/runs/${enc(runId)}/resume`, { body: { node_ids: nodeIds } }),
  };
}
