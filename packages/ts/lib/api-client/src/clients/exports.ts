/** 내보내기 REST(§2R.7). */
import type { ExporterDescriptor, ExportPlan, ExportRequest, ExportResult, ExportRootInfo, ExportWriteRequest } from "@agent-console/contracts";
import type { BlobResponse, RestIo } from "../io";

export interface ExportArchive extends BlobResponse {
  /** 응답 파일 이름이 없으면 쓰는 기본 이름 */
  filename: string;
}

export interface ExportsClient {
  listExporters(): Promise<ExporterDescriptor[]>;
  /** 미리보기. 아무것도 쓰지 않는다. `root`·`subdir`를 주면 그 폴더 기준으로 동작을 계산한다. */
  planExport(request: ExportRequest): Promise<ExportPlan>;
  /** 보관 파일(zip). 토큰 헤더가 필요해 fetch로 받아 Blob으로 돌려준다. 파일 이름은 `Content-Disposition`, 없으면 `export.zip`. */
  downloadExportArchive(request: ExportRequest): Promise<ExportArchive>;
  /** 폴더 쓰기가 허용된 루트(토큰 필수). 빈 목록이면 폴더 쓰기를 숨긴다. */
  listExportRoots(): Promise<ExportRootInfo[]>;
  /** 폴더에 쓰기. `on_conflict=fail`이고 충돌이면 409 `already_exists`(`details.paths`). */
  writeExport(request: ExportWriteRequest): Promise<ExportResult>;
}

export function createExportsClient(io: RestIo): ExportsClient {
  return {
    listExporters: () => io.request("GET", "/exporters"),
    planExport: (req) => io.request("POST", "/exports/plan", { body: req }),
    downloadExportArchive: async (req) => {
      const r = await io.requestBlob("POST", "/exports/archive", { body: req });
      return { ...r, filename: r.filename ?? "export.zip" };
    },
    listExportRoots: () => io.request("GET", "/exports/roots"),
    writeExport: (req) => io.request("POST", "/exports/write", { body: req }),
  };
}
