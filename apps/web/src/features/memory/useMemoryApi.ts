/**
 * 메모리 서버 상태 훅(TanStack Query). 화면은 이 훅만 부르고 REST를 직접 부르지 않는다.
 * 질의 키는 `["memory", 종류, …]` — 실시간 변경·쓰기 뒤 `["memory"]` 한 번으로 무효화한다.
 */
import { useCallback, useMemo } from "react";
import { keepPreviousData, useInfiniteQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { ApiError, memoryScopeText, type ListMemoryEntriesParams, type RestClient } from "@agent-console/api-client";
import type { MemoryEntry, MemoryEntryPage, MemoryEntrySummary, MemoryScopeKindList, MemoryScopeRef, MemoryScopeSummary, MemoryTagList, MemoryVersion, MemoryVersionSummary } from "@agent-console/contracts/memory";
import { useApi } from "../../app/ApiContext";
import { useApiQuery, useWorkspaceSettings } from "../../app/queries";
import { useModule } from "../../modules";
import { LIMIT_OPTION_KEYS, MEMORY_LIMITS, MEMORY_ROLE, SETTINGS_SECTION } from "./memoryConfig";
import { sortParams, type MemoryViewState } from "./memoryUrl";

export const memoryKeys = {
  root: ["memory"] as const,
  kinds: () => ["memory", "kinds"] as const,
  scopes: () => ["memory", "scopes"] as const,
  tags: (scope: MemoryScopeRef | null, archived: boolean) => ["memory", "tags", scope === null ? "" : memoryScopeText(scope), archived] as const,
  entries: (key: string) => ["memory", "entries", key] as const,
  entry: (id: string) => ["memory", "entry", id] as const,
  versions: (id: string) => ["memory", "versions", id] as const,
  version: (id: string, version: number) => ["memory", "version", id, version] as const,
  limits: (moduleId: string) => ["memory", "limits", moduleId] as const,
};

export function useMemoryKinds(): UseQueryResult<MemoryScopeKindList, Error> {
  return useApiQuery(memoryKeys.kinds(), (rest) => rest.listMemoryScopeKinds());
}

export function useMemoryScopes(): UseQueryResult<MemoryScopeSummary[], Error> {
  return useApiQuery(memoryKeys.scopes(), (rest) => rest.listMemoryScopes());
}

/** 서버 태그 목록(팝오버를 열 때만 부른다). 현재 범위·보관 포함 필터를 그대로 넘긴다. */
export function useMemoryTags(scope: MemoryScopeRef | null, includeArchived: boolean, enabled: boolean): UseQueryResult<MemoryTagList, Error> {
  return useApiQuery(
    memoryKeys.tags(scope, includeArchived),
    (rest) => rest.listMemoryTags({ ...(scope === null ? {} : { scopes: [scope] }), includeArchived }),
    { enabled, staleTime: 0, meta: { silentBackgroundError: true } },
  );
}

/** 목록 질의 인자(주소 상태 + 검색어)와 그 키. */
export function entriesParams(view: MemoryViewState, q: string): ListMemoryEntriesParams {
  return {
    ...(view.scope === null ? {} : { scopes: [view.scope] }),
    ...(q.trim() === "" ? {} : { q }),
    ...(view.tag === null ? {} : { tags: [view.tag] }),
    ...(view.authorRun === null ? {} : { authorRun: view.authorRun }),
    ...(view.authorKind === null ? {} : { authorKind: view.authorKind }),
    includeArchived: view.includeArchived,
    includeDeleted: view.includeDeleted,
    ...sortParams(view.sort),
    limit: MEMORY_LIMITS.pageSize,
  };
}

export interface EntryList {
  items: MemoryEntrySummary[];
  total: number | null;
  hasMore: boolean;
  fetchMore: () => void;
  fetching: boolean;
  fetchingMore: boolean;
  pending: boolean;
  error: Error | null;
  refetch: () => void;
}

/** 항목 목록(커서 쪽 넘김). 정렬은 서버가 하고 화면은 다시 정렬하지 않는다. 쪽을 이어 붙일 때 같은 id는 한 번만 둔다. */
export function useMemoryEntries(view: MemoryViewState, q: string): EntryList {
  const { rest } = useApi();
  const params = useMemo(() => entriesParams(view, q), [view, q]);
  const key = JSON.stringify(params);
  const query = useInfiniteQuery<MemoryEntryPage, Error, { pages: MemoryEntryPage[] }, readonly unknown[], string | null>({
    queryKey: memoryKeys.entries(key),
    queryFn: ({ pageParam }) => rest.listMemoryEntries({ ...params, cursor: pageParam }),
    initialPageParam: null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
  const pages = query.data?.pages;
  const items = useMemo(() => {
    const seen = new Set<string>();
    const out: MemoryEntrySummary[] = [];
    for (const page of pages ?? []) {
      for (const item of page.items ?? []) {
        if (seen.has(item.id)) continue;
        seen.add(item.id);
        out.push(item);
      }
    }
    return out;
  }, [pages]);
  const { fetchNextPage, hasNextPage, isFetchingNextPage, refetch } = query;
  const fetchMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const total = pages?.[pages.length - 1]?.total ?? pages?.[0]?.total ?? null;
  return {
    items,
    total,
    hasMore: hasNextPage,
    fetchMore,
    fetching: query.isFetching,
    fetchingMore: isFetchingNextPage,
    pending: query.isPending,
    error: query.error,
    refetch: () => void refetch(),
  };
}

export function useMemoryEntry(id: string | null, includeDeleted: boolean): UseQueryResult<MemoryEntry, Error> {
  return useApiQuery(memoryKeys.entry(id ?? ""), (rest) => rest.getMemoryEntry(id ?? "", { includeDeleted }), { enabled: id !== null, retry: false, staleTime: 0 });
}

export function useMemoryVersions(id: string | null, enabled: boolean): UseQueryResult<MemoryVersionSummary[], Error> {
  return useApiQuery(memoryKeys.versions(id ?? ""), (rest) => rest.listMemoryVersions(id ?? ""), { enabled: enabled && id !== null, staleTime: 0 });
}

export function useMemoryVersion(id: string | null, version: number | null): UseQueryResult<MemoryVersion, Error> {
  return useApiQuery(memoryKeys.version(id ?? "", version ?? 0), (rest) => rest.getMemoryVersion(id ?? "", version ?? 0), {
    enabled: id !== null && version !== null,
    staleTime: Infinity,
  });
}

export interface MemoryLimits {
  /** 설치자 한도(항목 본문 최대 바이트). 서버가 안 주면 null(저장 막기 없음, 서버 422가 최종) */
  maxEntryBytes: number | null;
  /** 버전 보관 수(기록 대화상자 안내 줄). 모르면 null */
  maxVersions: number | null;
}

const numberOr = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null);

/** 한도: 이 역할을 맡은 모듈의 읽기 전용 옵션에서 읽는다. 모듈 id는 역할로 찾는다(코드에 없다). */
export function useMemoryLimits(): MemoryLimits {
  const lookup = useModule(MEMORY_ROLE);
  const moduleId = lookup.modules[0]?.id ?? "";
  const q = useApiQuery(memoryKeys.limits(moduleId), (rest) => rest.getModuleOptions(moduleId), {
    enabled: moduleId !== "",
    retry: false,
    staleTime: 60_000,
    meta: { silentBackgroundError: true },
  });
  const values = q.data?.values;
  // 버전 보관 수는 설치자 한도가 아니라 사용자 설정(`memory` 섹션)이다.
  const settings = useWorkspaceSettings();
  const section = settings.data?.value[SETTINGS_SECTION] as { max_versions_per_entry?: unknown } | undefined;
  const versions = section?.max_versions_per_entry;
  return useMemo(() => ({ maxEntryBytes: numberOr(values?.[LIMIT_OPTION_KEYS.maxEntryBytes]), maxVersions: numberOr(versions) }), [values, versions]);
}

/** 쓰기·실시간 뒤 메모리 질의를 모두 다시 읽게 한다. */
export function useInvalidateMemory(): () => Promise<void> {
  const qc = useQueryClient();
  return useCallback(() => qc.invalidateQueries({ queryKey: memoryKeys.root }), [qc]);
}

/** 호출 함수에 주입할 REST 클라이언트(훅 밖 비동기 동작이 쓴다). */
export function useMemoryRest(): RestClient {
  return useApi().rest;
}

export function isApiError(e: unknown, code: string): e is ApiError {
  return e instanceof ApiError && e.code === code;
}
