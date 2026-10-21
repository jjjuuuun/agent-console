/** 워크스페이스 설정 REST. */
import type { WorkspaceSettings } from "@agent-console/contracts";
import { ifMatch, withHeaders, type RestIo, type Versioned } from "../io";

export interface SettingsClient {
  getSettings(): Promise<WorkspaceSettings>;
  /** `versionHash`를 주면 `If-Match`로 보낸다(선택). */
  putSettings(settings: WorkspaceSettings, versionHash?: string): Promise<WorkspaceSettings>;
  /** 설정과 `ETag`(`version_hash`). 설정 파일이 없으면 기본값이고 `version_hash`는 undefined. */
  getSettingsVersioned(): Promise<Versioned<WorkspaceSettings>>;
  /** `putSettings`와 같되 새 `ETag`를 함께 돌려준다. 412면 `ApiError.versionConflict`. */
  putSettingsVersioned(settings: WorkspaceSettings, versionHash?: string): Promise<Versioned<WorkspaceSettings>>;
}

export function createSettingsClient(io: RestIo): SettingsClient {
  return {
    getSettings: () => io.request("GET", "/settings"),
    putSettings: (s, hash) => io.request("PUT", "/settings", { body: s, ...withHeaders(ifMatch(hash)) }),
    getSettingsVersioned: () => io.requestVersioned("GET", "/settings"),
    putSettingsVersioned: (s, hash) => io.requestVersioned("PUT", "/settings", { body: s, ...withHeaders(ifMatch(hash)) }),
  };
}
