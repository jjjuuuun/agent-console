/**
 * 공유 메모리 REST(design §5.7R.5.2)와 로그 색인 비우기(M-3).
 * 범위 종류·범위 이름·태그·키를 모른다(전부 서버가 주는 데이터). 범위는 `MemoryScopeRef`이며
 * 질의에서는 `<종류>:<범위 id>` 문자열(`memoryScopeText`)로 쓴다.
 */
import type {
  MemoryCopyRequest,
  MemoryCopyResult,
  MemoryEntry,
  MemoryEntryPage,
  MemoryImportResult,
  MemoryMoveRequest,
  MemoryRetentionPlan,
  MemoryRetentionPlanRequest,
  MemoryRetentionResult,
  MemoryScopeKindList,
  MemoryScopeRef,
  MemoryScopeSummary,
  MemoryTagList,
  MemoryUpdateRequest,
  MemoryVersion,
  MemoryVersionSummary,
  MemoryWriteRequest,
} from "@agent-console/contracts/memory";
import type { Issue } from "@agent-console/contracts";
import { ApiError } from "../errors";
import { enc, type BlobResponse, type RestIo } from "../io";

/** 질의 인자 표기 `<종류>:<범위 id>`(범위 id가 없으면 콜론 뒤가 비어 있다). */
export function memoryScopeText(scope: MemoryScopeRef): string {
  return `${scope.kind}:${scope.id ?? ""}`;
}

/** `ListMemoryEntriesParams`·태그·내보내기 질의를 쿼리 문자열로(값이 없으면 보내지 않고, 반복 키는 여러 번 쓴다). */
function memoryQuery(params: Readonly<Record<string, string | number | boolean | readonly string[] | null | undefined>>): string {
  const parts: string[] = [];
  for (const [name, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    const list = Array.isArray(value) ? (value as readonly string[]) : [String(value)];
    for (const item of list) parts.push(`${enc(name)}=${enc(item)}`);
  }
  return parts.length === 0 ? "" : `?${parts.join("&")}`;
}

export interface ListMemoryEntriesParams {
  /** 범위(여러 개 가능). 생략 = 모든 범위. */
  scopes?: readonly MemoryScopeRef[];
  /** 키·본문·태그 검색어. */
  q?: string;
  /** 모두 붙어 있어야 하는 태그. */
  tags?: readonly string[];
  /** 마지막으로 쓴 실행 id. */
  authorRun?: string;
  /** 마지막으로 쓴 주체 종류(`MemoryAuthor.kind`). */
  authorKind?: string;
  includeArchived?: boolean;
  includeDeleted?: boolean;
  /** 서버 정렬 값(계약 `MEMORY_ENTRY_SORTS`). 생략 = 서버 기본. */
  sort?: string;
  order?: "asc" | "desc";
  cursor?: string | null;
  limit?: number;
}

/** 가져오기 충돌 정책(계약 어휘). */
export type MemoryImportPolicyName = string;

/** 로그 색인 비우기 요청(`POST /logs/index/purge`, 모듈 안 모델이라 여기서 정의한다). */
export interface LogIndexPurgeRequest {
  sources?: readonly string[];
  categories?: readonly string[];
  /** Unix epoch 초. 이보다 이른 이벤트만. */
  before?: number;
  /** 범위 출처의 커서도 지워 다음 수집이 다시 읽게 한다(서버 기본 true). */
  rescan?: boolean;
  /** 기본 true(지울 행 수만 센다). */
  dry_run?: boolean;
  /** 범위 없이 실제로 지울 때 필요한 확인. */
  all?: boolean;
}

export interface LogIndexPurgeResult {
  dry_run: boolean;
  events: number;
  usage: number;
  cursors: number;
  agents: number;
}

/** 412 `version_conflict`의 `details.current_version`(메모리 항목). 해당 오류가 아니면 undefined. */
export function memoryConflictVersion(error: unknown): number | undefined {
  if (!(error instanceof ApiError) || error.status !== 412) return undefined;
  const v = error.details["current_version"];
  return typeof v === "number" ? v : undefined;
}

export interface MemoryClient {
  /**
   * 메모리를 한 공간에서 다른 공간으로 복사한다(`POST /memory/copy`, 복사 뒤에는 독립). 공간 = `SpaceRef`(null = 공용).
   * 충돌은 `on_conflict`가 정하고 `remap`은 범위 id 바꾸기. 결과에 복사·건너뜀 수와 충돌 목록.
   */
  copyMemory(request: MemoryCopyRequest): Promise<MemoryCopyResult>;
  /** 병합된 범위 종류(끈 종류는 `disabled: true`). */
  listMemoryScopeKinds(): Promise<MemoryScopeKindList>;
  /** 항목이 있는 범위 요약. `kind`로 종류 하나만. */
  listMemoryScopes(kind?: string): Promise<MemoryScopeSummary[]>;
  /** 태그와 항목 수(내림차순). 지운 항목은 세지 않는다. */
  listMemoryTags(params?: { scopes?: readonly MemoryScopeRef[]; includeArchived?: boolean }): Promise<MemoryTagList>;
  listMemoryEntries(params?: ListMemoryEntriesParams): Promise<MemoryEntryPage>;
  /** 새 항목(버전 1). 같은 범위·키가 있으면 409 `already_exists`(`details.entry_id`). */
  createMemoryEntry(request: MemoryWriteRequest): Promise<MemoryEntry>;
  getMemoryEntry(id: string, options?: { includeDeleted?: boolean }): Promise<MemoryEntry>;
  /** 고치기. `version`은 `If-Match`(필수): 다르면 412(`memoryConflictVersion`), 없으면 428. */
  updateMemoryEntry(id: string, request: MemoryUpdateRequest, version: number): Promise<MemoryEntry>;
  /** 표시 삭제(지운 항목을 돌려준다). */
  deleteMemoryEntry(id: string, version?: number): Promise<MemoryEntry>;
  /** 완전 삭제(버전·검색 행까지, 204). */
  purgeMemoryEntry(id: string): Promise<void>;
  moveMemoryEntry(id: string, request: MemoryMoveRequest, version?: number): Promise<MemoryEntry>;
  archiveMemoryEntry(id: string, version?: number): Promise<MemoryEntry>;
  unarchiveMemoryEntry(id: string, version?: number): Promise<MemoryEntry>;
  /** 되돌리기: `version`을 주면 그 버전 본문으로, 생략하면 지운 항목 되살리기. 새 버전이 생긴다. */
  restoreMemoryEntry(id: string, version?: number): Promise<MemoryEntry>;
  /** 버전 목록(오름차순, 본문 없음). */
  listMemoryVersions(id: string): Promise<MemoryVersionSummary[]>;
  getMemoryVersion(id: string, version: number): Promise<MemoryVersion>;
  /** 정리 미리보기(아무것도 바꾸지 않는다). `rules`를 주면 저장 전 규칙으로 시험한다. */
  planMemoryRetention(request?: MemoryRetentionPlanRequest): Promise<MemoryRetentionPlan>;
  /** 저장된 정리 규칙을 지금 적용한다. */
  applyMemoryRetention(): Promise<MemoryRetentionResult>;
  /** 편집 중인 `memory` 설정 섹션 검사(저장을 막지 않는다). */
  checkMemorySettings(section?: Record<string, unknown>): Promise<Issue[]>;
  /** 마크다운 zip 내려받기(파일 이름은 `Content-Disposition`). */
  exportMemory(params?: { scopes?: readonly MemoryScopeRef[]; includeArchived?: boolean }): Promise<BlobResponse>;
  /** zip 바이트를 그대로 본문으로 보낸다(multipart 아님). `dryRun`이면 쓰지 않고 수만 센다. */
  importMemory(archive: Uint8Array, options?: { policy?: MemoryImportPolicyName; dryRun?: boolean }): Promise<MemoryImportResult>;
  /** 로그 색인 비우기(M-3). 기본 `dry_run` true. 범위 없이 실제로 지우려면 `all: true`. */
  purgeLogIndex(request?: LogIndexPurgeRequest): Promise<LogIndexPurgeResult>;
}

export function createMemoryClient(io: RestIo): MemoryClient {
  const entry = (id: string) => `/memory/entries/${enc(id)}`;
  const ifMatch = (version: number | undefined) => (version === undefined ? {} : { headers: { "If-Match": String(version) } });
  const scopeParam = (scopes: readonly MemoryScopeRef[] | undefined) => (scopes ?? []).map(memoryScopeText);
  return {
    copyMemory: (request) => io.request("POST", "/memory/copy", { body: request }),
    listMemoryScopeKinds: () => io.request("GET", "/memory/scope-kinds"),
    listMemoryScopes: (kind) => io.request("GET", `/memory/scopes${memoryQuery({ kind })}`),
    listMemoryTags: (params) =>
      io.request("GET", `/memory/tags${memoryQuery({ scope: scopeParam(params?.scopes), include_archived: params?.includeArchived })}`),
    listMemoryEntries: (p = {}) =>
      io.request(
        "GET",
        `/memory/entries${memoryQuery({
          scope: scopeParam(p.scopes),
          q: p.q,
          tag: p.tags,
          author_run: p.authorRun,
          author_kind: p.authorKind,
          include_archived: p.includeArchived,
          include_deleted: p.includeDeleted,
          sort: p.sort,
          order: p.order,
          cursor: p.cursor,
          limit: p.limit,
        })}`,
      ),
    createMemoryEntry: (request) => io.request("POST", "/memory/entries", { body: request }),
    getMemoryEntry: (id, options) => io.request("GET", `${entry(id)}${memoryQuery({ include_deleted: options?.includeDeleted })}`),
    updateMemoryEntry: (id, request, version) => io.request("PUT", entry(id), { body: request, ...ifMatch(version) }),
    deleteMemoryEntry: (id, version) => io.request("DELETE", entry(id), ifMatch(version)),
    purgeMemoryEntry: async (id) => {
      await io.request("DELETE", `${entry(id)}?purge=true`);
    },
    moveMemoryEntry: (id, request, version) => io.request("POST", `${entry(id)}/move`, { body: request, ...ifMatch(version) }),
    archiveMemoryEntry: (id, version) => io.request("POST", `${entry(id)}/archive`, ifMatch(version)),
    unarchiveMemoryEntry: (id, version) => io.request("POST", `${entry(id)}/unarchive`, ifMatch(version)),
    restoreMemoryEntry: (id, version) => io.request("POST", `${entry(id)}/restore${memoryQuery({ version })}`),
    listMemoryVersions: (id) => io.request("GET", `${entry(id)}/versions`),
    getMemoryVersion: (id, version) => io.request("GET", `${entry(id)}/versions/${version}`),
    planMemoryRetention: (request) => io.request("POST", "/memory/retention/plan", request === undefined ? {} : { body: request }),
    applyMemoryRetention: () => io.request("POST", "/memory/retention/apply"),
    checkMemorySettings: (section) => io.request("POST", "/memory/settings/check", { body: section ?? {} }),
    exportMemory: (params) =>
      io.requestBlob("GET", `/memory/export${memoryQuery({ scope: scopeParam(params?.scopes), include_archived: params?.includeArchived === false ? "false" : undefined })}`),
    importMemory: async (archive, options) => {
      const r = await io.requestVersioned<MemoryImportResult>("POST", `/memory/import${memoryQuery({ policy: options?.policy, dry_run: options?.dryRun })}`, {
        bytes: archive,
        headers: { "Content-Type": "application/zip" },
      });
      return r.value;
    },
    purgeLogIndex: (request) => io.request("POST", "/logs/index/purge", { body: request ?? {} }),
  };
}
