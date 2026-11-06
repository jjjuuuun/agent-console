/**
 * 그래프·점검·규칙 탭의 서버 상태 훅(TanStack Query). 질의 키는 `useWikiApi`의 위키 키 아래(`["wiki", 공간, "wiki", id, …]`)라
 * `useInvalidateWiki` 한 번(쓰기·`wiki.changed`)으로 함께 무효화된다.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { WikiGraph, WikiLintReport } from "@agent-console/contracts/wiki";
import { useWikiSpace } from "./useWikiApi";

/** 그래프 질의 인자: 중심 경로(없으면 전체)와 깊이(없으면 서버가 정한 전체). */
export interface GraphQuery {
  center?: string | undefined;
  depth?: number | undefined;
}

export const wikiTabKeys = {
  graph: (p: string, id: string, q: GraphQuery) => ["wiki", p, "wiki", id, "graph", q.center ?? null, q.depth ?? null] as const,
  lint: (p: string, id: string) => ["wiki", p, "wiki", id, "lint"] as const,
};

/** 링크 그래프. 잘림(`truncated`)과 총 칸 수(`total`)는 서버 값이다. */
export function useWikiGraph(id: string, query: GraphQuery, enabled = true): UseQueryResult<WikiGraph, Error> {
  const s = useWikiSpace();
  return useQuery({
    queryKey: wikiTabKeys.graph(s.key, id, query),
    queryFn: () => s.client.getWikiGraph(id, { ...(query.center === undefined ? {} : { center: query.center }), ...(query.depth === undefined ? {} : { depth: query.depth }) }),
    enabled,
    retry: false,
    staleTime: 0,
  });
}

/** 점검 결과(한 번에 받는다). */
export function useWikiLint(id: string): UseQueryResult<WikiLintReport, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiTabKeys.lint(s.key, id), queryFn: () => s.client.getWikiLint(id), retry: false, staleTime: 0 });
}
