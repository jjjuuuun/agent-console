/**
 * 프로젝트 REST 클라이언트. 전송은 주입한다(`@agent-console/api-client`의 `RestIo`가 그대로 맞는다).
 * 서버: mod-projects(`/api/v1/projects…`). 경로 접두어 `/api/v1`는 전송 쪽이 붙인다.
 */
import type {
  DeletePlan,
  MovePlan,
  MovePlanRequest,
  Project,
  ProjectCreate,
  ProjectDeleteMode,
  ProjectUpdate,
} from "@agent-console/contracts/projects";
import type { Issue } from "@agent-console/contracts";

/** `ETag`를 `version_hash`로 풀어 함께 돌려주는 응답. */
export interface ProjectsVersioned<T> {
  value: T;
  version_hash: string | undefined;
}

/** 이 클라이언트가 필요로 하는 전송의 최소 모양(`RestIo`의 부분 집합). */
export interface ProjectsIo {
  request<T>(method: string, path: string, opts?: { body?: unknown; headers?: Record<string, string> }): Promise<T>;
  requestVersioned<T>(
    method: string,
    path: string,
    opts?: { body?: unknown; headers?: Record<string, string> },
  ): Promise<ProjectsVersioned<T>>;
}

export interface ProjectsClient {
  /** 모든 프로젝트(id 순). */
  listProjects(): Promise<Project[]>;
  getProject(id: string): Promise<Project>;
  /** `getProject`와 같되 `ETag`(`version_hash`)를 함께 돌려준다(고칠 때 `If-Match`로 쓴다). */
  getProjectVersioned(id: string): Promise<ProjectsVersioned<Project>>;
  /** 만들기(201). 같은 id가 있으면 409 `already_exists`. */
  createProject(body: ProjectCreate): Promise<ProjectsVersioned<Project>>;
  /** 고치기: 쓴 필드만 바뀐다. `versionHash`를 주면 `If-Match`(다르면 412). */
  updateProject(id: string, patch: ProjectUpdate, versionHash?: string): Promise<ProjectsVersioned<Project>>;
  /** 삭제(204). `mode` 생략 = 서버 기본(공용으로 옮기기). */
  deleteProject(id: string, options?: { mode?: ProjectDeleteMode; versionHash?: string }): Promise<void>;
  /** 삭제하면 바뀌는 것(저장하지 않음). */
  getDeletePlan(id: string): Promise<DeletePlan>;
  /** 정의 하나를 `to` 범위로 옮길 때의 계획(저장하지 않음). `to` null = 공용. */
  getMovePlan(request: MovePlanRequest): Promise<MovePlan>;
  /** 계획의 `moves`를 적용한다. 응답 = 실제로 바꾼 이동 + 적용 뒤 경고. */
  applyMove(plan: MovePlan): Promise<MovePlan>;
  /** 워크스페이스 전체의 범위 이슈(경고·정보). */
  listScopeIssues(): Promise<Issue[]>;
}

const enc = encodeURIComponent;
const ifMatch = (hash: string | undefined): { headers: Record<string, string> } | Record<string, never> =>
  hash === undefined ? {} : { headers: { "If-Match": hash } };

/**
 * 프로젝트 클라이언트를 만든다.
 * @param io 전송(`createRestIo(...)`의 결과 등)
 */
export function createProjectsClient(io: ProjectsIo): ProjectsClient {
  return {
    listProjects: () => io.request("GET", "/projects"),
    getProject: (id) => io.request("GET", `/projects/${enc(id)}`),
    getProjectVersioned: (id) => io.requestVersioned("GET", `/projects/${enc(id)}`),
    createProject: (body) => io.requestVersioned("POST", "/projects", { body }),
    updateProject: (id, patch, hash) => io.requestVersioned("PUT", `/projects/${enc(id)}`, { body: patch, ...ifMatch(hash) }),
    deleteProject: async (id, options = {}) => {
      const mode = options.mode === undefined ? "" : `?mode=${enc(options.mode)}`;
      await io.request("DELETE", `/projects/${enc(id)}${mode}`, ifMatch(options.versionHash));
    },
    getDeletePlan: (id) => io.request("POST", `/projects/${enc(id)}/delete-plan`),
    getMovePlan: (request) => io.request("POST", "/projects/move-plan", { body: request }),
    applyMove: (plan) => io.request("POST", "/projects/move", { body: plan }),
    listScopeIssues: () => io.request("POST", "/projects/scope-issues"),
  };
}
