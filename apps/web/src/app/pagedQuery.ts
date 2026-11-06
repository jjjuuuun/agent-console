import { useCallback, useMemo } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import { useApi } from "./ApiContext";

/** 서버 커서 페이지의 최소 모양(`RunPage`·`ConversationPage`가 맞는다). */
export interface CursorPage<T> {
  items?: readonly T[] | undefined;
  /** 불투명 문자열. null·생략 = 끝 */
  next_cursor?: string | null | undefined;
  /** 이 페이지의 출처(예: 프로젝트 폴더 기록 → 앱 옛 기록). 값의 뜻은 서버 몫이고 웹은 바뀌는 지점만 본다. */
  source?: string | undefined;
}

export interface PagedList<T> {
  /** 읽은 페이지를 이어 붙인 항목(같은 id는 앞의 것만). 첫 페이지 전에는 undefined */
  items: readonly T[] | undefined;
  /** 항목 id → 그 항목에서 출처가 바뀐 새 출처(출처 구분선을 그릴 자리). 항목이 없는 페이지에서는 생기지 않는다 */
  sourceBreaks: ReadonlyMap<string, string>;
  /** 항목 id -> 그 항목을 받은 페이지의 출처(출처를 안 주는 서버면 비어 있다) */
  sourceOf: ReadonlyMap<string, string>;
  hasMore: boolean;
  loadMore(): void;
  loadingMore: boolean;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  isFetching: boolean;
  refetch(): void;
}

/**
 * 커서 페이지를 TanStack `useInfiniteQuery`로 이어 읽는다(컨테이너 훅, UI 없음).
 * `key`에 거르기 조건(프로젝트 포함)을 넣으면 조건이 바뀔 때 첫 페이지부터 새로 읽는다.
 * @param load 커서(없으면 null)를 받아 한 페이지를 읽는 함수
 */
export function useApiPagedQuery<T extends { id: string }>(
  key: readonly unknown[],
  load: (rest: RestClient, cursor: string | null) => Promise<CursorPage<T>>,
  options: { enabled?: boolean; retry?: boolean | number; refetchInterval?: (items: readonly T[] | undefined) => number | false } = {},
): PagedList<T> {
  const { rest } = useApi();
  const { refetchInterval, ...rest2 } = options;
  const q = useInfiniteQuery<CursorPage<T>, Error, { pages: CursorPage<T>[] }, readonly unknown[], string | null>({
    queryKey: key,
    queryFn: ({ pageParam }) => load(rest, pageParam),
    initialPageParam: null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    select: (d) => ({ pages: d.pages }),
    ...(refetchInterval ? { refetchInterval: (query) => refetchInterval(flatten(query.state.data?.pages).items) } : {}),
    ...rest2,
  });
  const pages = q.data?.pages;
  const flat = useMemo(() => flatten(pages), [pages]);
  const { fetchNextPage, refetch } = q;
  const loadMore = useCallback(() => void fetchNextPage(), [fetchNextPage]);
  const reload = useCallback(() => void refetch(), [refetch]);
  return {
    items: flat.items,
    sourceBreaks: flat.breaks,
    sourceOf: flat.sources,
    hasMore: q.hasNextPage,
    loadMore,
    loadingMore: q.isFetchingNextPage,
    isPending: q.isPending,
    isError: q.isError,
    error: q.error,
    isFetching: q.isFetching,
    refetch: reload,
  };
}

/** 페이지 배열 -> 이어 붙인 항목과 출처 바뀜 자리. 순수 함수. */
export function flatten<T extends { id: string }>(pages: readonly CursorPage<T>[] | undefined): { items: T[] | undefined; breaks: Map<string, string>; sources: Map<string, string> } {
  if (pages === undefined) return { items: undefined, breaks: new Map(), sources: new Map() };
  const seen = new Set<string>();
  const items: T[] = [];
  const breaks = new Map<string, string>();
  const sources = new Map<string, string>();
  let prevSource: string | undefined;
  for (const page of pages) {
    let first = true;
    for (const item of page.items ?? []) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      if (first && prevSource !== undefined && page.source !== undefined && page.source !== prevSource) breaks.set(item.id, page.source);
      first = false;
      if (page.source !== undefined) sources.set(item.id, page.source);
      items.push(item);
    }
    // 항목이 없는 페이지는 출처를 바꾸지 않는다(구분선은 실제로 출처가 다른 항목 앞에만)
    if (!first && page.source !== undefined) prevSource = page.source;
  }
  return { items, breaks, sources };
}
