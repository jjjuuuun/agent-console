/**
 * 스펙(SDD) REST(design §6R.7, 계약 `sdd` 1.0.0): 스펙 목록·보기·저장·삭제, 문서 본문·상태 전환, 작업(거르기·줄 고치기), 계획·추적,
 * 작업 동작·한꺼번에 시작, 자동 진행, 규칙 검사, 가져오기·내보내기, 문서 틀 목록.
 * 서버: `mod-sdd`(`/api/v1/sdd…`). 공간 인자(`?project=`)는 `withSpace(io, project)`가 맡는다: `createSddClient(withSpace(io, "payments"))`.
 * 문서 종류·상태·단계·역할·프로필 이름을 모른다(전부 서버가 주는 데이터).
 */
import type { ResourceFile } from "@agent-console/contracts";
import type {
  BulkActionsRequest,
  BulkActionsResult,
  BulkStartRequest,
  BulkStartResult,
  DocumentStateChange,
  EffectiveSyntax,
  ImportFileListing,
  ParsedTask,
  RulesCheckRequest,
  RulesCheckResult,
  SaveAsTemplateRequest,
  SaveAsTemplateResult,
  SddInfo,
  SpecCreateRequest,
  SpecDefinition,
  SpecDocumentContent,
  SpecExportRequest,
  SpecExportResult,
  SpecImportRequest,
  SpecSummary,
  SpecTemplate,
  SpecTemplateCreateRequest,
  SpecTemplateSummary,
  SpecView,
  TaskAction,
  TaskActionResult,
  TaskPatch,
  TaskPatchResult,
  TaskPlan,
  TemplateVariable,
  TraceMatrix,
  AutomationState,
} from "@agent-console/contracts/sdd";
import { enc, encodePath, ifMatch, query, withHeaders, type RestIo, type Versioned } from "../io";

/** 작업 목록 거르기(서버 질의). 배열은 같은 키를 되풀이한다. 상태·단계는 "또는", 필드는 "그리고". */
export interface ListSpecTasksParams {
  /** 작업 상태 id(여러 개 = 또는) */
  status?: readonly string[];
  /** 단계 id(여러 개 = 또는) */
  stage?: readonly string[];
  /** `<필드>=<값>`(여러 개 = 그리고) */
  field?: readonly string[];
  /** true = 준비된 작업만, false = 준비되지 않은 것만 */
  ready?: boolean;
  /** 키·id·제목에 든 글 */
  q?: string;
}

/** 문서 틀 뼈대 파일 읽기 결과. `version_hash` = 틀 정의 버전(`ETag`, 다음 쓰기의 `If-Match`). 텍스트가 아니면 `text`가 null. */
export interface TemplateFileContent {
  text: string | null;
  contentType: string;
  size: number;
  version_hash: string | undefined;
}

/** 자동 진행 조작 이름(서버 경로의 끝). */
export type SddAutomationOp = string;

export interface SddClient {
  /** 화면 정보: 스펙 폴더(`spec_root`)·한도·능력(`capabilities`)·실행 라벨 표시 규칙. */
  getSddInfo(): Promise<SddInfo>;
  listSpecs(): Promise<SpecSummary[]>;
  /** 만들기(틀 또는 빈 스펙). 201. */
  createSpec(body: SpecCreateRequest): Promise<Versioned<SpecView>>;
  getSpec(id: string): Promise<Versioned<SpecView>>;
  /** 규칙·문서 목록 저장. `If-Match`(스펙 `version_hash`) 필수. */
  putSpec(id: string, body: SpecDefinition, versionHash: string): Promise<Versioned<SpecView>>;
  deleteSpec(id: string, versionHash?: string): Promise<void>;
  /** 폴더 안 마크다운 파일을 새 스펙 문서로 복사. 201. */
  importSpec(body: SpecImportRequest): Promise<Versioned<SpecView>>;
  /** 가져오기용 폴더 안 파일 목록(폴더 기준 상대 경로, 빈 값 = 루트). */
  listImportFiles(path?: string): Promise<ImportFileListing>;
  exportSpec(id: string, body: SpecExportRequest): Promise<SpecExportResult>;
  /** 규칙 검사(저장하지 않음). 본문에 규칙이 없으면 스펙에 저장된 규칙. */
  checkSpec(id: string, body: RulesCheckRequest): Promise<RulesCheckResult>;
  checkTemplate(body: RulesCheckRequest): Promise<RulesCheckResult>;
  /** 이 공간의 문서 틀 목록. */
  listSpecTemplates(): Promise<SpecTemplateSummary[]>;
  listTemplateVariables(template?: string): Promise<TemplateVariable[]>;
  /** 빈 문서 틀 만들기(문서 0개, 규칙 비움). 201 + `ETag`. */
  createSpecTemplate(body: SpecTemplateCreateRequest): Promise<Versioned<SpecTemplate>>;
  /** 틀 원문 + `ETag`(정의 버전). 없으면 404 `sdd.not_found`. */
  getSpecTemplate(id: string): Promise<Versioned<SpecTemplate>>;
  /** 틀 저장. `If-Match` 필수(없으면 428, 낡으면 412). */
  putSpecTemplate(id: string, body: SpecTemplate, versionHash: string): Promise<Versioned<SpecTemplate>>;
  deleteSpecTemplate(id: string, versionHash?: string): Promise<void>;
  /** 틀 기준 변수 목록(`listTemplateVariables(id)`와 같다). */
  listSpecTemplateVariables(id: string): Promise<TemplateVariable[]>;
  /** 뼈대 파일 목록(경로 순). */
  listSpecTemplateFiles(id: string): Promise<ResourceFile[]>;
  readSpecTemplateFile(id: string, path: string): Promise<TemplateFileContent>;
  /** 뼈대 파일 쓰기. `versionHash` = 틀 정의 버전(`If-Match`). 응답 `version_hash`가 다음 쓰기의 `If-Match`다. 비밀 의심은 `issues`(`X-Console-Issues`). */
  putSpecTemplateFile(id: string, path: string, content: string | Uint8Array, versionHash: string, mediaType?: string): Promise<Versioned<SpecTemplate>>;
  deleteSpecTemplateFile(id: string, path: string, versionHash: string): Promise<Versioned<SpecTemplate>>;
  /** 문서 본문 읽기. `version_hash` = 본문 해시. 파일이 없으면 404 `sdd.document_missing`. */
  getSpecDocument(id: string, doc: string): Promise<Versioned<SpecDocumentContent>>;
  /** 본문 쓰기. `expectedHash` = `If-Match`(다르면 412), `createOnly` = `If-None-Match: *`(이미 있으면 거부). */
  putSpecDocument(id: string, doc: string, content: string, options?: { expectedHash?: string; createOnly?: boolean }): Promise<Versioned<SpecDocumentContent>>;
  /** 문서 상태 전환(403 `sdd.transition_denied`, 422 `sdd.gate_blocked`). */
  changeDocumentState(id: string, doc: string, body: DocumentStateChange, versionHash?: string): Promise<Versioned<SpecView>>;
  listSpecTasks(id: string, params?: ListSpecTasksParams): Promise<ParsedTask[]>;
  /** 작업 머리 줄 하나 고치기. 줄이 바뀌었으면 409 `sdd.task_changed`(`details`에 최신 줄). */
  patchSpecTask(id: string, key: string, body: TaskPatch): Promise<TaskPatchResult>;
  getSpecSyntax(id: string): Promise<EffectiveSyntax>;
  getSpecPlan(id: string): Promise<TaskPlan>;
  getSpecTrace(id: string): Promise<TraceMatrix>;
  listSpecVariables(id: string): Promise<TemplateVariable[]>;
  listTaskActions(id: string, key: string): Promise<TaskAction[]>;
  runTaskAction(id: string, key: string, integration: string, action: string, args?: Record<string, unknown>): Promise<TaskActionResult>;
  listBulkActions(id: string, body: BulkActionsRequest): Promise<BulkActionsResult>;
  bulkStartTasks(id: string, body: BulkStartRequest): Promise<BulkStartResult>;
  /** 자동 진행 멈춤·다시 시작(`op` = 서버 경로의 끝 이름). */
  controlAutomation(id: string, op: SddAutomationOp): Promise<AutomationState>;
  /** 이 스펙의 문서 목록과 규칙을 문서 틀로 복사. */
  saveSpecAsTemplate(id: string, body: SaveAsTemplateRequest): Promise<SaveAsTemplateResult>;
}

/** 작업 목록 질의를 서버 질의 이름으로(`field`는 `<필드>=<값>` 문자열 되풀이). */
function taskQuery(params: ListSpecTasksParams | undefined): string {
  if (params === undefined) return "";
  const { status, stage, field, ready, q } = params;
  return query({ status, stage, field, ready, q: q === undefined || q === "" ? undefined : q });
}

export function createSddClient(io: RestIo): SddClient {
  const spec = (id: string) => `/sdd/specs/${enc(id)}`;
  return {
    getSddInfo: () => io.request("GET", "/sdd/info"),
    listSpecs: () => io.request("GET", "/sdd/specs"),
    createSpec: (body) => io.requestVersioned("POST", "/sdd/specs", { body }),
    getSpec: (id) => io.requestVersioned("GET", spec(id)),
    putSpec: (id, body, hash) => io.requestVersioned("PUT", spec(id), { body, ...withHeaders(ifMatch(hash)) }),
    deleteSpec: (id, hash) => io.request("DELETE", spec(id), withHeaders(ifMatch(hash))),
    importSpec: (body) => io.requestVersioned("POST", "/sdd/specs/import", { body }),
    listImportFiles: (path = "") => io.request("GET", `/sdd/import/files${query({ path: path === "" ? undefined : path })}`),
    exportSpec: (id, body) => io.request("POST", `${spec(id)}/export`, { body }),
    checkSpec: (id, body) => io.request("POST", `${spec(id)}/check`, { body }),
    checkTemplate: (body) => io.request("POST", "/sdd/templates/check", { body }),
    listSpecTemplates: () => io.request("GET", "/sdd/templates"),
    listTemplateVariables: (template) => io.request("GET", `/sdd/templates/variables${query({ template })}`),
    createSpecTemplate: (body) => io.requestVersioned("POST", "/sdd/templates", { body }),
    getSpecTemplate: (id) => io.requestVersioned("GET", `/sdd/templates/${enc(id)}`),
    putSpecTemplate: (id, body, hash) => io.requestVersioned("PUT", `/sdd/templates/${enc(id)}`, { body, ...withHeaders(ifMatch(hash)) }),
    deleteSpecTemplate: (id, hash) => io.request("DELETE", `/sdd/templates/${enc(id)}`, withHeaders(ifMatch(hash))),
    listSpecTemplateVariables: (id) => io.request("GET", `/sdd/templates/${enc(id)}/variables`),
    listSpecTemplateFiles: (id) => io.request("GET", `/sdd/templates/${enc(id)}/files`),
    readSpecTemplateFile: async (id, path) => {
      const r = await io.requestBlob("GET", `/sdd/templates/${enc(id)}/files/${encodePath(path)}`, { headers: { Accept: "text/plain, application/octet-stream, */*" } });
      const isText = r.contentType.toLowerCase().startsWith("text/");
      return { text: isText ? await r.blob.text() : null, contentType: r.contentType, size: r.blob.size, version_hash: r.etag };
    },
    putSpecTemplateFile: (id, path, content, hash, mediaType) =>
      io.requestVersioned("PUT", `/sdd/templates/${enc(id)}/files/${encodePath(path)}`, {
        ...(typeof content === "string" ? { text: content } : { bytes: content }),
        headers: { "If-Match": hash, "Content-Type": mediaType ?? (typeof content === "string" ? "text/plain; charset=utf-8" : "application/octet-stream") },
      }),
    deleteSpecTemplateFile: (id, path, hash) => io.requestVersioned("DELETE", `/sdd/templates/${enc(id)}/files/${encodePath(path)}`, { headers: { "If-Match": hash } }),
    getSpecDocument: (id, doc) => io.requestVersioned("GET", `${spec(id)}/documents/${enc(doc)}`),
    putSpecDocument: (id, doc, content, options = {}) =>
      io.requestVersioned("PUT", `${spec(id)}/documents/${enc(doc)}`, {
        body: { content },
        ...withHeaders(options.createOnly === true ? { "If-None-Match": "*" } : ifMatch(options.expectedHash)),
      }),
    changeDocumentState: (id, doc, body, hash) =>
      io.requestVersioned("POST", `${spec(id)}/documents/${enc(doc)}/state`, { body, ...withHeaders(ifMatch(hash)) }),
    listSpecTasks: (id, params) => io.request("GET", `${spec(id)}/tasks${taskQuery(params)}`),
    patchSpecTask: (id, key, body) => io.request("PATCH", `${spec(id)}/tasks/${enc(key)}`, { body }),
    getSpecSyntax: (id) => io.request("GET", `${spec(id)}/syntax`),
    getSpecPlan: (id) => io.request("GET", `${spec(id)}/plan`),
    getSpecTrace: (id) => io.request("GET", `${spec(id)}/trace`),
    listSpecVariables: (id) => io.request("GET", `${spec(id)}/variables`),
    listTaskActions: (id, key) => io.request("GET", `${spec(id)}/tasks/${enc(key)}/actions`),
    runTaskAction: (id, key, integration, action, args) =>
      io.request("POST", `${spec(id)}/tasks/${enc(key)}/actions/${enc(integration)}/${enc(action)}`, { body: args === undefined ? {} : { args } }),
    listBulkActions: (id, body) => io.request("POST", `${spec(id)}/bulk-actions`, { body }),
    bulkStartTasks: (id, body) => io.request("POST", `${spec(id)}/bulk-start`, { body }),
    controlAutomation: (id, op) => io.request("POST", `${spec(id)}/automation/${enc(op)}`),
    saveSpecAsTemplate: (id, body) => io.request("POST", `${spec(id)}/save-as-template`, { body }),
  };
}
