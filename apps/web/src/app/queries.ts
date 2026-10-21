import { useCallback } from "react";
import { QueryCache, QueryClient, useQuery, type UseQueryOptions, type UseQueryResult } from "@tanstack/react-query";
import { ApiError, type RestClient, type Versioned } from "@agent-console/api-client";
import type { WorkspaceSettings } from "@agent-console/contracts";
import { useRequires } from "../modules";
import { useApi } from "./ApiContext";
import { DOCUMENT_REQUIRES } from "./requirements";

/** 서버 상태 질의 키 모음. 화면은 이 함수로 키를 만들어 무효화·공유한다. */
export const queryKeys = {
  settings: () => ["settings"] as const,
  descriptors: (name: string) => ["descriptors", name] as const,
  list: (name: string, params?: unknown) => (params === undefined ? (["list", name] as const) : (["list", name, params] as const)),
};

export interface AppQueryClientOptions {
  /** 이미 데이터가 있는 질의의 백그라운드 갱신이 실패했을 때(한 번씩) */
  onBackgroundError?: (error: unknown) => void;
  /** 테스트에서 재시도를 끄기 위한 값. 기본은 클라이언트 오류(4xx)가 아니면 2번까지 */
  retry?: boolean | number;
}

/**
 * 이 질의의 오류를 토스트로 알리지 말아야 하는가: 지금 보고 있는 관찰자가 하나 이상이고 **모두**
 * `meta.silentBackgroundError`를 단 경우만 true. 관찰자가 0개이거나 하나라도 플래그가 없으면(예: 사용량 화면) false.
 * 질의 자체의 `query.meta`와 관찰자 옵션의 `meta`는 다르다(여기서는 관찰자 것만 본다).
 */
export function isSilentBackgroundError(query: { observers: readonly { options: { meta?: Record<string, unknown> | undefined } }[] }): boolean {
  return query.observers.length > 0 && query.observers.every((o) => o.options.meta?.["silentBackgroundError"] === true);
}

/** 앱의 TanStack Query 클라이언트. 목록은 진입·창 포커스 복귀 때 최신화한다. */
export function createAppQueryClient(options: AppQueryClientOptions = {}): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.state.data !== undefined && !isSilentBackgroundError(query)) options.onBackgroundError?.(error);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: true,
        retry: options.retry ?? ((failureCount, error) => failureCount < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500)),
      },
    },
  });
}

/**
 * `ApiProvider`의 REST 클라이언트로 질의한다. `load`는 REST 클라이언트만 받는 순수 함수라 화면 훅이 모듈 상수로 둘 수 있다.
 * @param key `queryKeys`로 만든 키
 */
export function useApiQuery<T>(
  key: readonly unknown[],
  load: (rest: RestClient) => Promise<T>,
  options: Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn"> = {},
): UseQueryResult<T, Error> {
  const { rest } = useApi();
  const queryFn = useCallback(() => load(rest), [load, rest]);
  return useQuery<T, Error>({ queryKey: key, queryFn, ...options });
}

const loadSettings = (rest: RestClient) => rest.getSettingsVersioned();

/**
 * 공통 설정(저장 원문 + `ETag`). 서버는 지정한 키만 주고(없으면 `{}`) 설정 화면 편집기와 같은 키를 쓰므로 캐시를 공유한다.
 * 생략된 키는 `?.`·`??`로 읽는다.
 */
export function useWorkspaceSettings(): UseQueryResult<Versioned<WorkspaceSettings>, Error> {
  // 설정 문서를 책임지는 기능이 켜진 것이 확인된 뒤에만 부른다(꺼져 있으면 경로가 404일 것이므로).
  // 목록을 받지 못한 경우(fail-open)는 켜진 것으로 본다.
  const documentOn = useRequires(DOCUMENT_REQUIRES).phase === "met";
  return useApiQuery<Versioned<WorkspaceSettings>>(queryKeys.settings(), loadSettings, { enabled: documentOn });
}
