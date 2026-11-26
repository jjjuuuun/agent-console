import { ApiError, type RestClient } from "@agent-console/api-client";
import type { WorkspaceSettings } from "@agent-console/contracts";
import type { Versioned } from "@agent-console/api-client";

type SettingsRest = Pick<RestClient, "getSettingsVersioned" | "putSettingsVersioned">;

/**
 * 설정 문서에서 `ui.language` 한 칸만 바꿔 저장한다(screen-i18n §3-9, 요청 Q1). 서버에 저장된 최신 문서를 읽어 그 칸만 바꾸고
 * `If-Match`로 쓴다. 412(그 사이 다른 곳에서 바뀜)면 한 번 다시 읽고 다시 쓴다. 화면 편집 중인 초안은 건드리지 않는다.
 * @param value 언어 코드, `null` = 자동
 * @returns 저장된 문서(`ETag` 포함)
 * @throws 두 번째 시도도 실패하면 그 `ApiError`(또는 네트워크 오류)
 */
export async function saveLanguage(rest: SettingsRest, value: string | null): Promise<Versioned<WorkspaceSettings>> {
  for (let attempt = 0; ; attempt += 1) {
    const current = await rest.getSettingsVersioned();
    const next: WorkspaceSettings = { ...current.value, ui: { ...(current.value.ui ?? {}), language: value } };
    try {
      return await rest.putSettingsVersioned(next, current.version_hash);
    } catch (error) {
      const conflict = error instanceof ApiError && error.versionConflict !== undefined;
      if (!conflict || attempt >= 1) throw error;
    }
  }
}
