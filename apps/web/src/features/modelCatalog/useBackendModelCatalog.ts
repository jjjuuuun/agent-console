import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { BackendModelCatalogResult } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { queryKeys, useApiQuery } from "../../app/queries";

const catalogKey = (backendId: string) => queryKeys.descriptors("backend-model-catalog").concat(backendId);

/**
 * 백엔드 하나의 모델 목록(설정 + 계정 조회)과 조회 상태. 모델 칸·연결 모달 줄이 같은 질의 캐시를 쓴다.
 * `refresh`는 서버 캐시를 건너뛰고(`refresh=true`) 다시 조회해 캐시를 바꾼다. 백엔드를 못 정했으면 질의하지 않는다.
 * 옛 서버(경로 없음)는 `data.discovery === null`이다.
 */
export function useBackendModelCatalog(backendId: string | null | undefined) {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const id = backendId ?? "";
  const query = useApiQuery<BackendModelCatalogResult>(catalogKey(id), (r) => r.getBackendModelCatalog(id), { enabled: id !== "", meta: { silentBackgroundError: true } });
  const [refreshing, setRefreshing] = useState(false);
  /** 새 목록을 받으면 그 결과를, 요청이 실패하면 `undefined`(화면은 이전 값을 유지). */
  const refresh = useCallback(async (): Promise<BackendModelCatalogResult | undefined> => {
    if (id === "") return undefined;
    setRefreshing(true);
    try {
      const next = await rest.getBackendModelCatalog(id, { refresh: true });
      queryClient.setQueryData(catalogKey(id), next);
      return next;
    } catch {
      return undefined;
    } finally {
      setRefreshing(false);
    }
  }, [id, rest, queryClient]);
  return { ...query, refreshing, refresh };
}
