/** 가져오기 REST(`.claude` 등 출처 → 리소스). */
import type { ImportPreview, ImportPreviewRequest, ImportRequest, ImportResult, ImportSourceDescriptor } from "@agent-console/contracts";
import { query, type RestIo } from "../io";

/** 가져오기 질의(33k): 출처 폴더를 정하는 등록 프로젝트 id와 저장 위치. 모두 생략하면 서버 기본. */
export interface ImportScope {
  /** 출처 폴더의 등록 프로젝트 id(`?project=`). */
  project?: string | undefined;
  /** 가져온 정의를 쓸 곳(`?target=`): 프로젝트 사본 또는 공용(라이브러리). 열린 문자열이라 서버가 모르는 값은 거부한다. */
  target?: string | undefined;
}

export interface ImportsClient {
  /** 가져오기 출처 목록(디스크립터). */
  listImportSources(): Promise<ImportSourceDescriptor[]>;
  previewImport(request: ImportPreviewRequest, scope?: ImportScope): Promise<ImportPreview>;
  importResources(request: ImportRequest, scope?: ImportScope): Promise<ImportResult>;
}

export function createImportsClient(io: RestIo): ImportsClient {
  return {
    listImportSources: () => io.request("GET", "/resources/import/sources"),
    previewImport: (req, scope) => io.request("POST", `/resources/import/preview${query({ project: scope?.project, target: scope?.target })}`, { body: req }),
    importResources: (req, scope) => io.request("POST", `/resources/import${query({ project: scope?.project, target: scope?.target })}`, { body: req }),
  };
}
