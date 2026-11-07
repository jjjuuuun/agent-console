/**
 * 프로젝트 2 REST(design §PI.10, 계약 `projects` 3.0.0): 등록·조회·수정·해제, 폴더 확인·탐색·선택,
 * 공간 사이 복사(계획·적용), 옛 기록 복사 계획.
 * 서버: `mod-projects`(`/api/v1/projects…`). 정의·메모리의 공간 인자(`?project=`)는 `withSpace`(io.ts)가 맡는다.
 * 구성 종류·프로젝트·폴더 이름을 모른다(전부 서버가 주는 데이터).
 */
import type {
  CopyApplyRequest,
  CopyApplyResult,
  CopyItem,
  CopyKindInfo,
  CopyPlan,
  CopyPlanRequest,
  FolderCapabilities,
  FolderCheck,
  FolderCheckRequest,
  FolderListing,
  FolderPickRequest,
  FolderPickResult,
  ManifestResetRequest,
  ManifestResetResult,
  ProjectCreate,
  ProjectUpdate,
  ProjectView,
} from "@agent-console/contracts/projects";
import { enc, ifMatch, query, withHeaders, type RestIo, type Versioned } from "../io";

/** `GET /projects/folders` 질의. */
export interface ListFoldersParams {
  /** 나열할 폴더. 생략하면 서버 기본 시작 위치. */
  path?: string;
  /** 숨김 폴더도 받는가(기본 서버 값). */
  hidden?: boolean;
}

export interface ProjectsClient {
  /** 등록된 프로젝트(해제한 것 포함, `project.archived`)와 상태. */
  listProjects(): Promise<ProjectView[]>;
  getProject(id: string): Promise<ProjectView>;
  /** `getProject`와 같되 `ETag`(`version_hash`)를 함께 돌려준다(고칠 때 `If-Match`). */
  getProjectVersioned(id: string): Promise<Versioned<ProjectView>>;
  /** 폴더를 프로젝트로 등록(201). 폴더에 이미 설정이 있으면 채택한다. 폴더가 겹치면 409. */
  createProject(body: ProjectCreate): Promise<Versioned<ProjectView>>;
  /** 쓴 필드만 바꾼다(`folder` = 경로 다시 지정, `archived` = 해제·다시 등록). `versionHash`를 주면 `If-Match`(다르면 412). */
  updateProject(id: string, patch: ProjectUpdate, versionHash?: string): Promise<Versioned<ProjectView>>;
  /** 등록 해제(204). 폴더 안 파일은 지우지 않는다(서버가 보관 처리). */
  unregisterProject(id: string, versionHash?: string): Promise<void>;

  /** 설정 파일을 다시 만든다(`status == "manifest_invalid"`일 때만, 아니면 409). 이전 파일은 서버가 백업으로 옮기고 `backup_path`를 준다. */
  resetProjectManifest(id: string, body: ManifestResetRequest): Promise<ManifestResetResult>;
  /** 구성 폴더의 `.gitignore`에 빠진 줄만 덧붙인다(기존 줄은 그대로). 갱신된 프로젝트를 돌려준다. */
  appendProjectGitignore(id: string): Promise<ProjectView>;

  /** 폴더 확인. `create: true`면 없는 폴더를 만든다(사용자가 [폴더 만들기]를 눌렀을 때만). */
  checkFolder(request: FolderCheckRequest): Promise<FolderCheck>;
  /** `checkFolder({path, create: true})`의 줄임. */
  createFolder(path: string): Promise<FolderCheck>;
  /** 하위 폴더 목록(탐색 패널). */
  listFolders(params?: ListFoldersParams): Promise<FolderListing>;
  /** 폴더 고르는 방법(앱 안 찾아보기·OS 선택 창) — 지원 여부와 이유. */
  getFolderCapabilities(): Promise<FolderCapabilities>;
  /**
   * OS 폴더 선택 창을 띄운다. 사용자가 고를 때까지 응답이 오지 않으므로 `signal`을 abort하면 요청을 끊는다
   * (서버가 창을 닫는다). 끊으면 `ApiError`(`network_error`)로 reject된다.
   */
  pickFolder(request?: FolderPickRequest, options?: { signal?: AbortSignal }): Promise<FolderPickResult>;

  /** 공간 사이 복사 계획(저장하지 않음). 공간 = `SpaceRef`(`project_id` null = 공용). */
  planCopy(request: CopyPlanRequest): Promise<CopyPlan>;
  /** 계획을 적용한다. 항목별 결과(`conflict` = 계획 뒤에 바뀜). */
  applyCopy(request: CopyApplyRequest): Promise<CopyApplyResult>;
  /** 옛 방식으로 만든 이 프로젝트 전용 정의를 프로젝트 사본으로 옮기는 계획(`CopyPlan` 형식). */
  planLegacyCopy(id: string): Promise<CopyPlan>;
  /**
   * 한 공간(`project` null = 공용)에서 복사에 쓸 정의 종류와 방향 플래그(`library`: 공용에 둘 수 있음, `portable`: 프로젝트에 둘 수 있음).
   * 복사 대화상자는 종류 이름 표 없이 이 목록으로 채운다.
   */
  listCopyKinds(project: string | null): Promise<CopyKindInfo[]>;
  /** 한 공간의 정의 목록(본문 없음). `kind`를 생략하면 복사 종류 전부, 모르는 종류는 404. */
  listCopyItems(project: string | null, kind?: string): Promise<CopyItem[]>;
  /**
   * 프로젝트 사본의 정의 하나를 지운다(종류 공통, `CopyKindInfo.deletable`인 종류만). `opts.ifMatch`를 주면 `If-Match`로 보낸다.
   * 오류: 404 `project.not_found`·`not_found`, 400 `bad_request`(details.reason `not_deletable`), 409 `project.config_readonly`, 412 `version_conflict`.
   */
  deleteCopyItem(projectId: string, kind: string, itemId: string, opts?: { ifMatch?: string }): Promise<void>;
}

export function createProjectsClient(io: RestIo): ProjectsClient {
  const check = (request: FolderCheckRequest): Promise<FolderCheck> => io.request("POST", "/projects/folders/check", { body: request });
  return {
    listProjects: () => io.request("GET", "/projects"),
    getProject: (id) => io.request("GET", `/projects/${enc(id)}`),
    getProjectVersioned: (id) => io.requestVersioned("GET", `/projects/${enc(id)}`),
    createProject: (body) => io.requestVersioned("POST", "/projects", { body }),
    updateProject: (id, patch, hash) =>
      io.requestVersioned("PUT", `/projects/${enc(id)}`, { body: patch, ...withHeaders(ifMatch(hash)) }),
    unregisterProject: (id, hash) => io.request("DELETE", `/projects/${enc(id)}`, withHeaders(ifMatch(hash))),

    resetProjectManifest: (id, body) => io.request("POST", `/projects/${enc(id)}/manifest/reset`, { body }),
    appendProjectGitignore: (id) => io.request("POST", `/projects/${enc(id)}/gitignore/append`),

    checkFolder: check,
    createFolder: (path) => check({ path, create: true }),
    listFolders: (params) => io.request("GET", `/projects/folders${query(params)}`),
    getFolderCapabilities: () => io.request("GET", "/projects/folders/capabilities"),
    pickFolder: (request = {}, options = {}) =>
      io.request("POST", "/projects/folders/pick", {
        body: request,
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),

    planCopy: (request) => io.request("POST", "/projects/copy/plan", { body: request }),
    applyCopy: (request) => io.request("POST", "/projects/copy/apply", { body: request }),
    planLegacyCopy: (id) => io.request("POST", `/projects/${enc(id)}/legacy/plan`),
    listCopyKinds: (project) => io.request("GET", `/projects/copy/kinds${query({ project: project ?? undefined })}`),
    listCopyItems: (project, kind) => io.request("GET", `/projects/copy/items${query({ project: project ?? undefined, kind })}`),
    deleteCopyItem: (projectId, kind, itemId, opts = {}) =>
      io.request("DELETE", `/projects/copy/items/${enc(kind)}/${enc(itemId)}${query({ project: projectId })}`, withHeaders(ifMatch(opts.ifMatch))),
  };
}
