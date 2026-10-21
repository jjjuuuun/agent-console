/**
 * 정의 버전 기록·비교·되돌리기 REST(§2R.9). 정의 종류 이름을 모른다:
 * 호출은 정의 경로(`definitionBase("/agents", "a1")` 같은 문자열)를 받는다.
 */
import type { DefinitionDiff, DefinitionVersion, ResourceFile, RestoreVersionRequest } from "@agent-console/contracts";
import { enc, encodePath, type RestIo } from "../io";

/** 버전 본문 파일 읽기 결과. 텍스트가 아니면 `text`가 null이다. */
export interface VersionFileContent {
  /** 텍스트(`text/*`)일 때 내용, 그 밖(`application/octet-stream` 등)은 null */
  text: string | null;
  contentType: string;
  /** 바이트 수 */
  size: number;
}

export interface VersionsClient {
  /** 버전 목록(최신순, `content` 없음). */
  listDefinitionVersions(base: string): Promise<DefinitionVersion[]>;
  /** 한 버전(`content` = 정의 원문). */
  getDefinitionVersion(base: string, hash: string): Promise<DefinitionVersion>;
  /** 두 버전 비교. `to`를 생략하면 현재와 비교(정의가 지워졌으면 404). */
  diffDefinitionVersions(base: string, from: string, to?: string): Promise<DefinitionDiff>;
  /** 그 버전의 본문 파일 목록(스냅샷이 없으면 404). */
  listVersionFiles(base: string, hash: string): Promise<ResourceFile[]>;
  /** 그 버전의 본문 파일 내용. */
  readVersionFile(base: string, hash: string, path: string): Promise<VersionFileContent>;
  /**
   * 되돌리기 = 그 버전 내용으로 새 버전 저장. `currentHash`는 `If-Match`(정의가 있으면 필수, 지운 정의는 생략).
   * 없음 428, 다름 412(`ApiError.versionConflict`), 저장 전 검사 실패 422 `validation_failed`(`details.issues`).
   */
  restoreDefinitionVersion(
    base: string,
    hash: string,
    request?: RestoreVersionRequest,
    currentHash?: string,
  ): Promise<{ value: DefinitionVersion; version_hash: string | undefined }>;
}

export function createVersionsClient(io: RestIo): VersionsClient {
  return {
    listDefinitionVersions: (base) => io.request("GET", `${base}/versions`),
    getDefinitionVersion: (base, hash) => io.request("GET", `${base}/versions/${enc(hash)}`),
    diffDefinitionVersions: (base, from, to) => io.request("GET", `${base}/versions/${enc(from)}/diff${to === undefined ? "" : `/${enc(to)}`}`),
    listVersionFiles: (base, hash) => io.request("GET", `${base}/versions/${enc(hash)}/files`),
    readVersionFile: async (base, hash, path) => {
      const r = await io.requestBlob("GET", `${base}/versions/${enc(hash)}/files/${encodePath(path)}`, {
        headers: { Accept: "text/plain, application/octet-stream, */*" },
      });
      const isText = r.contentType.toLowerCase().startsWith("text/");
      return { text: isText ? await r.blob.text() : null, contentType: r.contentType, size: r.blob.size };
    },
    restoreDefinitionVersion: (base, hash, request, currentHash) =>
      io.requestVersioned("POST", `${base}/versions/${enc(hash)}/restore`, {
        body: request ?? {},
        ...(currentHash === undefined ? {} : { headers: { "If-Match": currentHash } }),
      }),
  };
}
