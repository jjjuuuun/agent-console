/** 실행(Run) REST: 생성·조회·취소·추적·이벤트·위임 집계·이어 가기. */
import type { CreateRunRequest, HandoffMatrix, ResumeOptions, Run, RunEvent, RunPage, RunSnapshot, RunStatus, Trace } from "@agent-console/contracts";
import type { RunLocation } from "@agent-console/contracts/runs";
import type { AssignProjectRequest, AssignProjectResult, ProjectCounts, RecordsMoveRequest, RecordsMoveResult } from "@agent-console/contracts/projects";
import { enc, query, SPACE_PARAM, withQueryParam, type RestIo } from "../io";

/** Run 단위 호출의 기록 공간(`?project=`). null·undefined·빈 문자열 = 붙이지 않음(앱 기록 또는 서버가 아는 자리). */
export type RunSpace = string | null | undefined;
const at = (path: string, project: RunSpace): string => (project === null || project === undefined || project === "" ? path : withQueryParam(path, SPACE_PARAM, project));

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

/** GET `/runs/page` 질의(6R.12). 커서는 불투명 문자열이라 응답 `next_cursor`를 그대로 넘긴다. */
export interface RunsPageParams {
  cursor?: string | null;
  /** 한 페이지 크기(서버 기본 50, 1~1000). */
  limit?: number;
  project?: string;
  /** 루트 Run만. */
  root_only?: boolean;
  /** 여러 상태 = OR. */
  status?: readonly RunStatus[];
  graph_id?: string;
  /** `<키>=<값>` 문자열(여러 개 = AND). */
  label?: readonly string[];
  /** 커서가 없을 때의 출처(기본 `project`). 커서에 든 출처가 우선한다. */
  source?: string;
  /** 그 에이전트가 actor로 남긴 이벤트가 있는 Run. */
  agent_id?: string;
  conversation_id?: string;
  /** 그 루트 Run 아래 모든 자손(루트 자신은 빠짐). */
  root?: string;
  /** `created_at` 하한(epoch 초). 이 시각 이후에 만든 Run만. */
  since?: number;
  /** run id·graph_id·입력 최상위 문자열 부분 일치(ASCII 대소문자 무시, 서버 상한 200자). */
  q?: string;
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
  /** 이 노드 id가 `node_path`에 있는 이벤트만(하위 그래프 안 이벤트 포함, 서버 6R.12). */
  node?: string;
  /** 그 Run이 있는 기록 공간(`?project=`, `locateRun`의 `project_id`). 생략 = 앱 기록 또는 서버가 아는 자리. */
  project?: string;
}

export interface RunsClient {
  /** `project_id`별 루트 Run 수(`ProjectCounts`: 전체·프로젝트 없음·프로젝트별). */
  getRunProjectCounts(): Promise<ProjectCounts>;
  /** Run을 프로젝트에 넣는다(`ids` 또는 `from_null`). 못 옮긴 것은 결과 `skipped`에 이유와 함께. */
  assignRunsToProject(request: AssignProjectRequest): Promise<AssignProjectResult>;
  /** 앱에 남은 옛 기록을 프로젝트 폴더의 기록 DB로 옮긴다(`select` project·null·ids). 같은 id는 `skipped`, 못 옮긴 것은 `failed`. */
  moveRunsToProject(request: RecordsMoveRequest): Promise<RecordsMoveResult>;
  createRun(request: CreateRunRequest): Promise<Run>;
  listRuns(params?: ListRunsParams): Promise<Run[]>;
  /** 실행 목록 커서 페이지(`GET /runs/page`). `next_cursor`가 null이면 끝, 응답 `source`는 그 페이지의 출처. */
  runsPage(params?: RunsPageParams): Promise<RunPage>;
  /**
   * Run 스냅샷. `children`은 직접 자식 Run(만든 순, 서버가 채우면 늘 배열).
   * `project` = 그 Run이 있는 기록 공간(`?project=`). 없는 공간이면 `ApiError` 404 — `locateRun`으로 찾는다.
   */
  getRun(id: string, project?: RunSpace): Promise<RunSnapshot>;
  /**
   * Run이 있는 기록 공간(`GET /runs/{id}/locate`, 계약 0.14.8). `project_id`를 Run 단위 호출의 `project`로 넘긴다(null = 앱 기록).
   * 없으면 `ApiError` 404 `not_found`, 여러 공간에 있으면 409 `run.ambiguous`(`details.project_ids`). 옛 서버는 404/405.
   */
  locateRun(id: string): Promise<RunLocation>;
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
    moveRunsToProject: (request) => io.request("POST", "/runs/move-to-project", { body: request }),
    createRun: (req) => io.request("POST", "/runs", { body: req }),
    listRuns: (params) => io.request("GET", `/runs${query(params)}`),
    runsPage: (params) => io.request("GET", `/runs/page${query(params)}`),
    getRun: (id, project) => io.request("GET", at(`/runs/${enc(id)}`, project)),
    locateRun: (id) => io.request("GET", `/runs/${enc(id)}/locate`),
    cancelRun: (id) => io.request("POST", `/runs/${enc(id)}/cancel`),
    getRunTrace: (id) => io.request("GET", `/runs/${enc(id)}/trace`),
    listRunEvents: (id, params) => io.request("GET", `/runs/${enc(id)}/events${query(params)}`),
    getHandoffs: (params) => io.request("GET", `/runs/handoffs${query(params)}`),
    getResumeOptions: (runId) => io.request("GET", `/runs/${enc(runId)}/resume-options`),
    resumeRun: (runId, nodeIds) => io.request("POST", `/runs/${enc(runId)}/resume`, { body: { node_ids: nodeIds } }),
  };
}
