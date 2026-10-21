/** 가져오기 REST(`.claude` 등 출처 → 리소스). */
import type { ImportPreview, ImportPreviewRequest, ImportRequest, ImportResult, ImportSourceDescriptor } from "@agent-console/contracts";
import type { RestIo } from "../io";

export interface ImportsClient {
  /** 가져오기 출처 목록(디스크립터). */
  listImportSources(): Promise<ImportSourceDescriptor[]>;
  previewImport(request: ImportPreviewRequest): Promise<ImportPreview>;
  importResources(request: ImportRequest): Promise<ImportResult>;
}

export function createImportsClient(io: RestIo): ImportsClient {
  return {
    listImportSources: () => io.request("GET", "/resources/import/sources"),
    previewImport: (req) => io.request("POST", "/resources/import/preview", { body: req }),
    importResources: (req) => io.request("POST", "/resources/import", { body: req }),
  };
}
