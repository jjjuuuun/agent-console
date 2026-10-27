/**
 * 구조도 서버 상태 훅(TanStack Query). 화면은 이 훅만 부르고 REST를 직접 부르지 않는다.
 * 질의 키는 `["logs", "architecture", …]` — 로그 수집·재연결 때 `["logs"]` 한 번으로 함께 무효화된다.
 */
import { useEffect, useMemo } from "react";
import { keepPreviousData, useInfiniteQuery, type UseQueryResult } from "@tanstack/react-query";
import type { LogQueryParams } from "@agent-console/api-client";
import type { ArchitectureMembership, ArchitectureProfileList, ArchitectureView, LogEvent, LogEventPage } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { ARCH_LIMITS } from "./archConfig";

/** 질의 인자 → 안정된 문자열 키(이름 정렬). */
export function archParamsKey(params: LogQueryParams): string {
  return JSON.stringify(Object.entries(params).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

export const archKeys = {
  view: (key: string) => ["logs", "architecture", "view", key] as const,
  membership: (uid: string, profile: string) => ["logs", "architecture", "membership", uid, profile] as const,
  rows: (key: string) => ["logs", "architecture", "rows", key] as const,
  profiles: () => ["architecture", "profiles"] as const,
};

/** 범위 구조도. 다시 질의하는 동안 이전 그림을 남긴다. 실패는 재시도하지 않는다(상한 초과·규칙 없음은 바로 화면 상태가 된다). */
export function useArchitectureView(params: LogQueryParams, enabled: boolean): UseQueryResult<ArchitectureView, Error> {
  return useApiQuery(archKeys.view(archParamsKey(params)), (rest) => rest.getLogArchitecture(params), {
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

/** 이벤트 하나가 맞은 칸·연결·묶음(표에서 고른 이벤트 강조). 실패해도 화면은 그대로다. */
export function useEventMembership(uid: string | null, profile: string | undefined, enabled: boolean): UseQueryResult<ArchitectureMembership, Error> {
  return useApiQuery(archKeys.membership(uid ?? "", profile ?? ""), (rest) => rest.getLogEventArchitecture(uid ?? "", profile), {
    enabled: enabled && uid !== null && uid !== "",
    retry: false,
    staleTime: 5 * 60_000,
    meta: { silentBackgroundError: true },
  });
}

/** 프로필 목록(프로필 선택·"선택한 프로필이 없어" 안내용). 실패하면 선택 칸이 없을 뿐이다. */
export function useArchitectureProfiles(enabled: boolean): UseQueryResult<ArchitectureProfileList, Error> {
  return useApiQuery(archKeys.profiles(), (rest) => rest.listArchitectureProfiles(), {
    enabled,
    retry: false,
    staleTime: 60_000,
    meta: { silentBackgroundError: true },
  });
}

export interface ArchitectureRows {
  /** 지금까지 읽은 이벤트(서버 순서) */
  events: readonly LogEvent[];
  /** 끝까지 읽었는가 */
  complete: boolean;
  loading: boolean;
  error: Error | null;
}

/**
 * 구조도 선택(`arch` 필터) 또는 하위 구조도(`thread` 등)로 걸러진 이벤트를 끝까지 읽는다.
 * `params`가 null이면 질의하지 않는다. 표의 행 수가 칸 횟수와 같으려면 서버가 센 이벤트를 모두 읽어야 해서 쪽을 자동으로 이어 받는다.
 */
export function useArchitectureRows(params: LogQueryParams | null, enabled = true): ArchitectureRows {
  const { rest } = useApi();
  const key = params === null ? "" : archParamsKey(params);
  const q = useInfiniteQuery({
    queryKey: archKeys.rows(key),
    enabled: enabled && params !== null,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => rest.listLogEvents({ ...(params ?? {}), limit: ARCH_LIMITS.rowsPage, order: "asc", ...(typeof pageParam === "string" ? { cursor: pageParam } : {}) }),
    getNextPageParam: (last: LogEventPage) => last.next_cursor ?? undefined,
    retry: false,
  });
  const pages = q.data?.pages.length ?? 0;
  useEffect(() => {
    if (q.hasNextPage && !q.isFetchingNextPage && !q.isError && pages < ARCH_LIMITS.rowsMaxPages) void q.fetchNextPage();
  }, [q, pages]);
  return useMemo<ArchitectureRows>(
    () => ({
      events: q.data?.pages.flatMap((p) => p.items ?? []) ?? [],
      complete: q.data !== undefined && !q.hasNextPage,
      loading: q.isPending || q.isFetchingNextPage || q.hasNextPage,
      error: q.error,
    }),
    [q.data, q.hasNextPage, q.isPending, q.isFetchingNextPage, q.error],
  );
}
