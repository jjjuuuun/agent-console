/** 리소스 REST: CRUD·본문·사용처·여러 파일 리소스. */
import type { DefinitionReference, Issue, Resource, ResourceFile, ResourceSummary } from "@agent-console/contracts";
import { enc, encodePath, ifMatch, query, withHeaders, type RestIo, type Versioned } from "../io";

/** GET `/resources` 필터. */
export interface ListResourcesParams {
  type?: string;
}

/** 여러 파일 리소스의 파일 한 개 읽기 결과. */
export interface ResourceFileContent {
  /** 텍스트(`text/*`)일 때 내용, 그 밖은 null(편집기에서 열 수 없음) */
  text: string | null;
  contentType: string;
  /** 바이트 수 */
  size: number;
  /** 정의 `version_hash`(= 다음 쓰기의 `If-Match`) */
  version_hash: string | undefined;
}

export interface ResourcesClient {
  listResources(params?: ListResourcesParams): Promise<ResourceSummary[]>;
  createResource(resource: Resource): Promise<Versioned<Resource>>;
  getResource(id: string): Promise<Versioned<Resource>>;
  updateResource(id: string, resource: Resource, versionHash?: string): Promise<Versioned<Resource>>;
  deleteResource(id: string, versionHash?: string): Promise<void>;
  listResourceUsages(id: string): Promise<DefinitionReference[]>;
  /** 문서형 리소스 본문(텍스트). */
  getResourceContent(id: string): Promise<Versioned<string>>;
  /** 본문 저장. `versionHash`(정의 `version_hash`)를 `If-Match`로 보낸다. 412면 `versionConflict`. */
  putResourceContent(id: string, text: string, versionHash: string, mediaType?: string): Promise<{ version_hash: string | undefined; issues?: Issue[] | undefined }>;
  /** 파일 목록(경로 순). `multi_file`이 아닌 종류는 422 `resource.not_multi_file`. */
  listResourceFiles(id: string): Promise<ResourceFile[]>;
  /** 파일 내용 + 정의 `ETag`. */
  readResourceFile(id: string, path: string): Promise<ResourceFileContent>;
  /** 파일 쓰기(없으면 만든다). `versionHash`는 `If-Match`(없음 428, 다름 412). 경로 위반 400, 총량 초과 413. */
  putResourceFile(
    id: string,
    path: string,
    content: string | Uint8Array,
    versionHash: string,
    mediaType?: string,
  ): Promise<Versioned<Resource>>;
  /** 파일 삭제. 응답 = 정의 + 새 `ETag`. */
  deleteResourceFile(id: string, path: string, versionHash: string): Promise<Versioned<Resource>>;
}

export function createResourcesClient(io: RestIo): ResourcesClient {
  return {
    listResources: (params) => io.request("GET", `/resources${query(params)}`),
    createResource: (r) => io.requestVersioned("POST", "/resources", { body: r }),
    getResource: (id) => io.requestVersioned("GET", `/resources/${enc(id)}`),
    updateResource: (id, r, hash) => io.requestVersioned("PUT", `/resources/${enc(id)}`, { body: r, ...withHeaders(ifMatch(hash)) }),
    deleteResource: (id, hash) => io.request("DELETE", `/resources/${enc(id)}`, withHeaders(ifMatch(hash))),
    listResourceUsages: (id) => io.request("GET", `/resources/${enc(id)}/usages`),
    getResourceContent: (id) => io.requestText("GET", `/resources/${enc(id)}/content`, { headers: { Accept: "text/plain, text/markdown, */*" } }),
    putResourceContent: async (id, text, hash, mediaType) => {
      const r = await io.requestText("PUT", `/resources/${enc(id)}/content`, {
        text,
        headers: { "If-Match": hash, "Content-Type": mediaType ?? "text/plain; charset=utf-8" },
      });
      return { version_hash: r.version_hash, ...(r.issues === undefined ? {} : { issues: r.issues }) };
    },
    listResourceFiles: (id) => io.request("GET", `/resources/${enc(id)}/files`),
    readResourceFile: async (id, path) => {
      const r = await io.requestBlob("GET", `/resources/${enc(id)}/files/${encodePath(path)}`, {
        headers: { Accept: "text/plain, application/octet-stream, */*" },
      });
      const isText = r.contentType.toLowerCase().startsWith("text/");
      return { text: isText ? await r.blob.text() : null, contentType: r.contentType, size: r.blob.size, version_hash: r.etag };
    },
    putResourceFile: (id, path, content, hash, mediaType) =>
      io.requestVersioned("PUT", `/resources/${enc(id)}/files/${encodePath(path)}`, {
        ...(typeof content === "string" ? { text: content } : { bytes: content }),
        headers: {
          "If-Match": hash,
          "Content-Type": mediaType ?? (typeof content === "string" ? "text/plain; charset=utf-8" : "application/octet-stream"),
        },
      }),
    deleteResourceFile: (id, path, hash) =>
      io.requestVersioned("DELETE", `/resources/${enc(id)}/files/${encodePath(path)}`, { headers: { "If-Match": hash } }),
  };
}
