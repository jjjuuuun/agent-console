import { ApiError, type RestClient, type Versioned } from "@agent-console/api-client";
import type { ImportCandidate, Issue, Resource, ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import { PartialSaveResult } from "../../definition/useDefinitionEditor";
import { describeError } from "../../app/errors";
import { resourceMessages as t } from "./messages";
import { planFileChanges, sortEntries, type FileEntry } from "./fileTreeLogic";

/** 편집 중인 리소스 한 건: 정의 + 문서 본문(문서형일 때). `origin`은 서버에 있는 상태(무엇이 바뀌었는지 알기 위해). */
export interface ResourceDoc {
  resource: Resource;
  /** 문서형 종류가 아니면 null */
  text: string | null;
  /** 여러 파일 종류(`content.multi_file`)의 파일들. 아니면 null */
  files?: FileEntry[] | null;
  /** 저장하다 멈춘 파일의 오류(경로 -> 서버 메시지). 서버에 있는 상태에는 없다 */
  fileErrors?: Record<string, string>;
  origin: { resource: Resource; text: string | null; files?: FileEntry[] | null };
}

export const WARN_BYTES = 512 * 1024;
export const MAX_EDIT_BYTES = 2 * 1024 * 1024;

/** 이 종류는 문서 본문을 가지는가(디스크립터 `content`). 디스크립터를 모르면 정의에 본문 참조가 있는지로 본다. */
export function hasDocument(descriptor: ResourceTypeDescriptor | undefined, resource?: Resource): boolean {
  return descriptor === undefined ? resource?.content != null : descriptor.content != null;
}

/** 이 종류는 본문이 여러 파일인가(디스크립터 `content.multi_file`). 종류 이름으로 정하지 않는다. */
export function isMultiFile(descriptor: ResourceTypeDescriptor | undefined): boolean {
  return descriptor?.content?.multi_file === true;
}

/** 편집기 언어 이름(디스크립터 `content.editor`, 기본 text). */
export function editorLanguageOf(descriptor: ResourceTypeDescriptor | undefined): string {
  return descriptor?.content?.editor ?? "text";
}

/** 지금 쓰는 미디어 타입: 정의에 있으면 그것, 없으면 디스크립터 첫 항목. */
export function mediaTypeOf(resource: Resource, descriptor: ResourceTypeDescriptor | undefined): string {
  return resource.content?.media_type ?? descriptor?.content?.media_types?.[0] ?? "text/plain";
}

/** 확장자를 알려진 형식에 매핑하는 기본 표(없으면 MIME 하위 형식 이름을 쓴다). 사용자 지정 형식이 늘어도 코드 수정이 필요 없다. */
export const EXTENSION_BY_MEDIA_TYPE: Readonly<Record<string, string>> = { "text/markdown": "md", "text/plain": "txt", "text/html": "html", "application/json": "json" };

/** 본문 참조 기본값: 디스크립터가 본문을 가지면 `{file: <id>.<확장자>, media_type: 첫 허용 형식}`, 아니면 undefined. */
export function defaultContentRef(descriptor: ResourceTypeDescriptor | undefined, id: string): { file: string; media_type: string } | undefined {
  if (descriptor?.content == null) return undefined;
  const media = descriptor.content.media_types?.[0] ?? "text/plain";
  const sub = media.split("/")[1]?.split("+")[0]?.replace(/^x-/, "") ?? "txt";
  return { file: `${id}.${EXTENSION_BY_MEDIA_TYPE[media] ?? (sub || "txt")}`, media_type: media };
}

export type ResourceTabId = "content" | "config" | "usages";

/** 탭 구성: 문서형은 [내용][설정][사용처], 설정형은 [설정][사용처]. 종류를 모르면 읽기 전용이라 [사용처]만. */
export function resourceTabIds(descriptor: ResourceTypeDescriptor | undefined, resource?: Resource): ResourceTabId[] {
  if (descriptor === undefined) return hasDocument(undefined, resource) ? ["content", "usages"] : ["config", "usages"];
  return descriptor.content != null ? ["content", "config", "usages"] : ["config", "usages"];
}

/** 본문 읽기. 본문 파일이 아직 없으면(404) 빈 문서로 본다. */
async function readText(rest: RestClient, id: string): Promise<{ text: string; hash: string | undefined }> {
  try {
    const got = await rest.getResourceContent(id);
    return { text: got.value, hash: got.version_hash };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return { text: "", hash: undefined };
    throw e;
  }
}

/** 여러 파일 본문을 모두 읽는다(경로 순). 텍스트가 아닌 파일은 `text: null`. */
export async function loadFiles(rest: RestClient, id: string): Promise<FileEntry[]> {
  const list = await rest.listResourceFiles(id);
  const entries = await Promise.all(
    list.map(async (f): Promise<FileEntry> => {
      const entry: FileEntry = { path: f.path, text: null, size: f.size };
      if (f.media_type != null) entry.mediaType = f.media_type;
      const got = await rest.readResourceFile(id, f.path);
      if (got.text === null && entry.mediaType === undefined && got.contentType !== "") entry.mediaType = got.contentType.split(";")[0]!.trim();
      return { ...entry, text: got.text };
    }),
  );
  return sortEntries(entries);
}

/** 리소스(정의 + 문서형이면 본문, 여러 파일 종류면 파일들)를 읽는다. 버전은 정의의 `ETag`. */
export async function loadResource(rest: RestClient, id: string, descriptors: readonly ResourceTypeDescriptor[]): Promise<Versioned<ResourceDoc>> {
  const got = await rest.getResource(id);
  const resource = got.value;
  const descriptor = descriptors.find((x) => x.id === got.value.type);
  const multi = isMultiFile(descriptor);
  const text = !multi && hasDocument(descriptor, got.value) ? (await readText(rest, id)).text : null;
  const files = multi ? await loadFiles(rest, id) : null;
  return { value: { resource, text, files, origin: { resource, text, files } }, version_hash: got.version_hash };
}

/**
 * 한 번의 [저장]: 정의가 바뀌었으면 `PUT /resources/{id}`, 본문이 바뀌었으면 `PUT /resources/{id}/content`.
 * 두 요청 중 하나만 성공하면 어느 쪽이 실패했는지 `PartialSaveError`로 알린다(성공한 쪽의 새 버전이 서버에 있다).
 */
export class PartialSaveError extends Error {
  readonly failed: "definition" | "content";
  constructor(failed: "definition" | "content", cause: unknown) {
    super(failed === "content" ? t.detail.saveContentFailed : t.detail.saveDefFailed, { cause });
    this.failed = failed;
  }
}

/** 여러 저장 요청에서 받은 경고(`X-Console-Issues`)를 한데 모은다. 같은 코드·경로·메시지는 한 번만. 없으면 빈 객체(Versioned에 그대로 펼친다). */
export function collectIssues(...parts: ReadonlyArray<readonly Issue[] | undefined>): { issues?: Issue[] } {
  const seen = new Set<string>();
  const out: Issue[] = [];
  for (const list of parts) {
    for (const i of list ?? []) {
      const key = `${i.code}\u0000${i.path ?? ""}\u0000${i.message}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.push(i);
      }
    }
  }
  return out.length === 0 ? {} : { issues: out };
}

export async function saveResource(rest: RestClient, doc: ResourceDoc, versionHash: string | undefined, descriptors: readonly ResourceTypeDescriptor[]): Promise<Versioned<ResourceDoc>> {
  if (doc.files != null) return saveResourceFiles(rest, doc, versionHash);
  const mediaType = mediaTypeOf(doc.resource, descriptors.find((x) => x.id === doc.resource.type));
  const defChanged = JSON.stringify(doc.resource) !== JSON.stringify(doc.origin.resource);
  const textChanged = doc.text !== null && doc.text !== doc.origin.text;
  let hash = versionHash;
  let done = false;
  let defIssues: readonly Issue[] | undefined;
  let contentIssues: readonly Issue[] | undefined;
  try {
    if (defChanged) {
      const saved = await rest.updateResource(doc.resource.id, doc.resource, hash);
      defIssues = saved.issues;
      hash = saved.version_hash ?? hash;
      done = true;
    }
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new PartialSaveError("definition", e);
  }
  try {
    if (textChanged && doc.text !== null) {
      const saved = await rest.putResourceContent(doc.resource.id, doc.text, hash ?? "", mediaType);
      contentIssues = saved.issues;
      hash = saved.version_hash ?? hash;
    }
  } catch (e) {
    if (e instanceof ApiError && !done) throw e;
    throw new PartialSaveError("content", e);
  }
  return { value: { ...doc, origin: { resource: doc.resource, text: doc.text, files: doc.origin.files } }, version_hash: hash, ...collectIssues(defIssues, contentIssues) };
}

function withoutFileErrors(doc: ResourceDoc): ResourceDoc {
  const next = { ...doc };
  delete next.fileErrors;
  return next;
}

/**
 * 여러 파일 종류의 [저장]: 정의가 바뀌었으면 먼저 저장하고, 바뀐 파일을 하나씩 올린 뒤(모두 성공해야) 지운다.
 * 파일 하나마다 `If-Match`가 새 해시로 이어진다. 일부가 실패하면 성공한 만큼 반영한 상태를 `PartialSaveResult`로
 * 알린다(실패한 변경은 초안에 남고 `fileErrors`에 서버 메시지가 붙는다). 해시가 어긋난 412는 그대로 던져 충돌로 다룬다.
 */
export async function saveResourceFiles(rest: RestClient, doc: ResourceDoc, versionHash: string | undefined): Promise<Versioned<ResourceDoc>> {
  const id = doc.resource.id;
  const originFiles = doc.origin.files ?? [];
  const draftFiles = doc.files ?? [];
  let hash = versionHash;
  let resource = doc.origin.resource;
  let applied = originFiles;
  const issues: Issue[] = [];
  const snapshot = (): Versioned<ResourceDoc> => ({ value: { ...withoutFileErrors(doc), resource, files: applied, origin: { resource, text: null, files: applied } }, version_hash: hash, ...collectIssues(issues) });
  if (JSON.stringify(doc.resource) !== JSON.stringify(doc.origin.resource)) {
    const saved = await rest.updateResource(id, doc.resource, hash);
    issues.push(...(saved.issues ?? []));
    hash = saved.version_hash ?? hash;
    resource = doc.resource;
  }
  const plan = planFileChanges(originFiles, draftFiles);
  const errors: Record<string, string> = {};
  for (const f of plan.puts) {
    try {
      const body = f.bytes ?? f.text ?? "";
      const saved = await rest.putResourceFile(id, f.path, body, hash ?? "", f.mediaType);
      issues.push(...(saved.issues ?? []));
      hash = saved.version_hash ?? hash;
      resource = saved.value;
      applied = sortEntries([...applied.filter((a) => a.path !== f.path), f.bytes !== undefined ? { path: f.path, text: null, size: f.bytes.length } : f]);
    } catch (e) {
      if (e instanceof ApiError && (e.versionConflict || e.status === 428)) throw e;
      errors[f.path] = describeError(e, t.files.putFailed).message;
    }
  }
  if (Object.keys(errors).length === 0) {
    for (const path of plan.deletes) {
      try {
        const saved = await rest.deleteResourceFile(id, path, hash ?? "");
        issues.push(...(saved.issues ?? []));
        hash = saved.version_hash ?? hash;
        resource = saved.value;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          // 이미 없다
        } else if (e instanceof ApiError && (e.versionConflict || e.status === 428)) {
          throw e;
        } else {
          errors[path] = describeError(e, t.files.deleteFailed).message;
          break;
        }
      }
      applied = applied.filter((a) => a.path !== path);
    }
  }
  const failed = Object.keys(errors);
  if (failed.length === 0) {
    const done = sortEntries(draftFiles.map((f) => (f.bytes !== undefined ? { path: f.path, text: null, size: f.bytes.length } : f)));
    return { value: { ...withoutFileErrors(doc), resource, files: done, origin: { resource, text: null, files: done } }, version_hash: hash, ...collectIssues(issues) };
  }
  const base = snapshot();
  throw new PartialSaveResult<ResourceDoc>(t.files.partial(failed.length), base, { ...doc, resource, fileErrors: errors, origin: base.value.origin });
}

/** 새 리소스 초안 문서: 종류가 정하는 본문 모양(문서형 = 빈 텍스트, 여러 파일형 = 빈 목록, 설정형 = 없음). */
export function newResourceDoc(descriptor: ResourceTypeDescriptor | undefined, seed: Pick<Resource, "id" | "name"> & Partial<Resource>): ResourceDoc {
  const content = defaultContentRef(descriptor, seed.id);
  const resource = { ...seed, type: descriptor?.id ?? seed.type ?? "", ...(content ? { content } : {}) } as Resource;
  const multi = isMultiFile(descriptor);
  const text = !multi && hasDocument(descriptor) ? "" : null;
  const files = multi ? [] : null;
  return { resource, text, files, origin: { resource, text, files } };
}

export interface CreateResourceOutcome {
  /** 서버가 만든 정의 */
  resource: Resource;
  /** 정의는 만들었지만 본문(텍스트·파일)을 저장하다 실패했다. 정의는 이미 있으므로 다시 만들면 안 된다 */
  bodyError?: unknown;
}

/**
 * 새 리소스를 만든다: 정의 `POST /resources`, 이어서 본문(문서 텍스트 또는 파일들)을 올린다. 정의 생성 실패는 던진다.
 * 본문 저장만 실패하면 던지지 않고 `bodyError`로 알린다(정의는 이미 서버에 있다).
 */
export async function createResourceDoc(rest: RestClient, doc: ResourceDoc, descriptors: readonly ResourceTypeDescriptor[]): Promise<CreateResourceOutcome> {
  const created = await rest.createResource(doc.resource);
  const resource = created.value;
  const emptyBody = doc.text === "" || (doc.text === null && (doc.files ?? []).length === 0);
  if (emptyBody) return { resource };
  try {
    await saveResource(rest, { ...doc, resource, origin: { resource, text: doc.text === null ? null : "", files: doc.files == null ? doc.files : [] } }, created.version_hash, descriptors);
    return { resource };
  } catch (e) {
    return { resource, bodyError: e };
  }
}

/** 종류별 개수(종류 id -> 수). */
export function countByType(resources: readonly ResourceSummary[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const r of resources) counts.set(r.type, (counts.get(r.type) ?? 0) + 1);
  return counts;
}

/** 목록 필터: 종류·검색어(이름·설명·id)·특정 id 집합(방금 가져온 항목). */
export function filterResources(resources: readonly ResourceSummary[], opts: { typeId: string | null; query: string; onlyIds?: ReadonlySet<string> | null }): ResourceSummary[] {
  const q = opts.query.trim().toLowerCase();
  return resources.filter(
    (r) =>
      (opts.typeId === null || r.type === opts.typeId) &&
      (opts.onlyIds == null || opts.onlyIds.has(r.id)) &&
      (q === "" || `${r.name} ${r.description ?? ""} ${r.id}`.toLowerCase().includes(q)),
  );
}

/** 가져오기 경고 중 비밀 관련으로 강조할 코드(서버 어휘). 그 밖의 경고도 서버 메시지 그대로 보인다. */
export const SECRET_WARNING_CODES: readonly string[] = ["import.secret_replaced", "import.secret_suspected"];

export function isSecretWarning(code: string): boolean {
  return SECRET_WARNING_CODES.includes(code);
}

/** 후보 목록에서 선택한 것으로 가져오기 요청 항목을 만든다(충돌 처리는 충돌 후보만 의미가 있다). */
export function buildImportItems(candidates: readonly ImportCandidate[], selected: ReadonlySet<string>, policies: Readonly<Record<string, string>>) {
  return candidates
    .filter((c) => selected.has(c.id))
    .map((c) => ({ candidate_id: c.id, on_conflict: (c.conflict ? (policies[c.id] ?? "rename") : "rename") as "skip" | "overwrite" | "rename" }));
}

/** 비밀 참조 접두어(서버 `SECRET_REF_PREFIX`와 같은 계약). */
const SECRET_PREFIX = "secret://";

/** 스키마 노드(또는 그 값 스키마·선택지)에 `x-secret: true` 주석이 있는가. */
function hasSecretAnnotation(node: unknown, depth = 0): boolean {
  if (typeof node !== "object" || node === null || depth > 3) return false;
  const n = node as Record<string, unknown>;
  if (n["x-secret"] === true) return true;
  const nested = [n["additionalProperties"], n["items"], ...(Array.isArray(n["anyOf"]) ? n["anyOf"] : []), ...(Array.isArray(n["oneOf"]) ? n["oneOf"] : [])];
  return nested.some((x) => hasSecretAnnotation(x, depth + 1));
}

/**
 * 비밀 값을 받는 설정 필드. 스키마의 `x-secret: true` 주석(속성 자체 또는 값 스키마)이 기준이다.
 * 주석이 하나도 없는 스키마(주석을 모르는 종류)는 설명에 `secret://`가 나오는 속성으로 대신 판별한다.
 * 키 이름을 코드에 두지 않는다.
 */
export function secretFieldsOf(schema: Record<string, unknown> | undefined): string[] {
  const props = schema?.["properties"];
  if (typeof props !== "object" || props === null) return [];
  const entries = Object.entries(props as Record<string, { description?: unknown }>);
  const annotated = entries.filter(([, p]) => hasSecretAnnotation(p)).map(([k]) => k);
  if (annotated.length > 0) return annotated;
  return entries.filter(([, p]) => typeof p?.description === "string" && p.description.includes(SECRET_PREFIX)).map(([k]) => k);
}

/** 비밀 필드 중 `secret://`로 시작하지 않는 값의 위치(JSON Pointer, config 기준). 값은 싣지 않는다. */
export function plainSecretPaths(config: Record<string, unknown>, fields: readonly string[]): string[] {
  const out: string[] = [];
  const bad = (v: unknown) => typeof v === "string" && v !== "" && !v.startsWith(SECRET_PREFIX);
  for (const f of fields) {
    const v = config[f];
    if (bad(v)) out.push(`/${f}`);
    else if (typeof v === "object" && v !== null && !Array.isArray(v)) {
      for (const [k, x] of Object.entries(v)) if (bad(x)) out.push(`/${f}/${k.replace(/~/g, "~0").replace(/\//g, "~1")}`);
    }
  }
  return out;
}

/** 서버 오류 경로(리소스 문서 기준 `/config/...`)를 설정 폼 기준으로. `/config` 밖이면 버린다. */
export function toConfigErrors<T extends { path: string }>(errors: readonly T[]): T[] {
  return errors.filter((e) => e.path === "/config" || e.path.startsWith("/config/")).map((e) => ({ ...e, path: e.path.slice("/config".length) }));
}
