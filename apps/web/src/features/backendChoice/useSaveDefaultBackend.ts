import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { WorkspaceSettings } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { queryKeys } from "../../app/queries";

/**
 * 공통 설정 `agent_defaults.backend`를 저장하는 함수(`PUT /settings` + If-Match).
 * 다른 설정은 읽은 그대로 두고, 저장 뒤 설정 캐시를 무효화한다. 실패하면 예외를 던진다.
 */
export function useSaveDefaultBackend(): (backendId: string) => Promise<void> {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  return useCallback(
    async (backendId: string) => {
      const current = await rest.getSettingsVersioned();
      const next: WorkspaceSettings = { ...current.value, agent_defaults: { ...(current.value.agent_defaults ?? {}), backend: backendId } };
      await rest.putSettingsVersioned(next, current.version_hash);
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
    },
    [rest, queryClient],
  );
}
