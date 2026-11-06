/**
 * 위키 서버 상태 훅(TanStack Query). 화면은 이 훅만 부르고 REST를 직접 부르지 않는다.
 * 질의 키는 `["wiki", 공간, …]` — 실시간 변경·쓰기 뒤 `["wiki"]` 한 번으로 무효화한다. 공간 = 현재 프로젝트 id(없으면 빈 문자열).
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery, useQuery, useQueryClient, type UseInfiniteQueryResult, type UseQueryResult } from "@tanstack/react-query";
import type { InfiniteData } from "@tanstack/react-query";
import type { Versioned, WikiClient } from "@agent-console/api-client";
import type {
  EffectiveWikiSyntax,
  WikiChangePage,
  WikiChanged,
  WikiHistoryPage,
  WikiInfo,
  WikiPageList,
  WikiPageTemplateInfo,
  WikiPageView,
  WikiRulesListItem,
  WikiSummary,
  WikiView,
} from "@agent-console/contracts/wiki";
import { useApi } from "../../app/ApiContext";
import { useProjectId } from "../../app/projectScope";
import { WIKI_LIMITS } from "./wikiConfig";

export const wikiKeys = {
  root: ["wiki"] as const,
  info: (p: string) => ["wiki", p, "info"] as const,
  list: (p: string) => ["wiki", p, "wikis"] as const,
  wiki: (p: string, id: string) => ["wiki", p, "wiki", id] as const,
  pages: (p: string, id: string) => ["wiki", p, "wiki", id, "pages"] as const,
  page: (p: string, id: string, path: string) => ["wiki", p, "wiki", id, "page", path] as const,
  history: (p: string, id: string, path: string) => ["wiki", p, "wiki", id, "history", path] as const,
  version: (p: string, id: string, path: string, v: number) => ["wiki", p, "wiki", id, "version", path, v] as const,
  templates: (p: string, id: string) => ["wiki", p, "wiki", id, "templates"] as const,
  syntax: (p: string, id: string) => ["wiki", p, "wiki", id, "syntax"] as const,
  changes: (p: string, id: string) => ["wiki", p, "wiki", id, "changes"] as const,
  rules: (p: string) => ["wiki", p, "rules"] as const,
};

/** 현재 공간(프로젝트 id, 없으면 null)과 그 공간의 위키 클라이언트. 컨테이너·훅이 함께 쓴다. */
export interface WikiSpace {
  project: string | null;
  /** 질의 키에 쓰는 공간 문자열(프로젝트가 없으면 빈 문자열) */
  key: string;
  client: WikiClient;
}

export function useWikiSpace(): WikiSpace {
  const { wiki } = useApi();
  const project = useProjectId();
  return useMemo(() => ({ project, key: project ?? "", client: wiki(project) }), [wiki, project]);
}

/** 화면 정보: 페이지 폴더·능력·한도. */
export function useWikiInfo(): UseQueryResult<WikiInfo, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.info(s.key), queryFn: () => s.client.getWikiInfo(), retry: false, staleTime: 30_000 });
}

export function useWikiList(enabled = true): UseQueryResult<WikiSummary[], Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.list(s.key), queryFn: () => s.client.listWikis(), enabled, retry: false });
}

export function useWikiView(id: string): UseQueryResult<Versioned<WikiView>, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.wiki(s.key, id), queryFn: () => s.client.getWiki(id), retry: false, staleTime: 0 });
}

/** 페이지 목록(상한 안은 한 번에 받는다. 커서·`limit`은 없다). */
export function usePageList(id: string, enabled = true): UseQueryResult<WikiPageList, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.pages(s.key, id), queryFn: () => s.client.listWikiPages(id), enabled, retry: false, staleTime: 0 });
}

/** 페이지 본문(`version_hash` = 본문 해시). 없으면 오류(`wiki.page_not_found`)로 오며 재시도하지 않는다. */
export function usePage(id: string, path: string | null): UseQueryResult<Versioned<WikiPageView>, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.page(s.key, id, path ?? ""), queryFn: () => s.client.getWikiPage(id, path ?? ""), enabled: path !== null, retry: false, staleTime: 0 });
}

/** 페이지 기록. 기록 저장소가 없으면 409로 오며 재시도하지 않는다. */
export function usePageHistory(id: string, path: string | null, enabled: boolean): UseQueryResult<WikiHistoryPage, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.history(s.key, id, path ?? ""), queryFn: () => s.client.getWikiPageHistory(id, path ?? ""), enabled: enabled && path !== null, retry: false, staleTime: 0 });
}

/** 기록의 한 버전 본문(글). */
export function usePageVersion(id: string, path: string | null, version: number | null): UseQueryResult<Versioned<string>, Error> {
  const s = useWikiSpace();
  return useQuery({
    queryKey: wikiKeys.version(s.key, id, path ?? "", version ?? 0),
    queryFn: () => s.client.getWikiPageVersion(id, path ?? "", version ?? 0),
    enabled: path !== null && version !== null,
    retry: false,
    staleTime: Infinity,
  });
}

/** 합친 페이지 틀 목록. */
export function useWikiTemplates(id: string, enabled: boolean): UseQueryResult<WikiPageTemplateInfo[], Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.templates(s.key, id), queryFn: () => s.client.listWikiTemplates(id), enabled, retry: false });
}

/** 유효 문법(링크 규칙과 삽입 틀). 문법을 못 읽어도 화면은 일반 마크다운으로 동작한다. */
export function useWikiSyntax(id: string, enabled = true): UseQueryResult<EffectiveWikiSyntax, Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.syntax(s.key, id), queryFn: () => s.client.getWikiSyntax(id), enabled, retry: false, meta: { silentBackgroundError: true } });
}

/** 최근 변경(커서, 지운 페이지 포함). 트리 아래 [최근 변경]에서 쓴다. */
export function useWikiChanges(id: string, enabled: boolean): UseInfiniteQueryResult<InfiniteData<WikiChangePage, string | undefined>, Error> {
  const s = useWikiSpace();
  return useInfiniteQuery({
    queryKey: wikiKeys.changes(s.key, id),
    queryFn: ({ pageParam }) => s.client.listWikiChanges(id, { limit: WIKI_LIMITS.changesPage, ...(pageParam === undefined ? {} : { cursor: pageParam }) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled,
    retry: false,
  });
}

/** 이 공간의 위키 규칙 목록(새 위키 대화상자). */
export function useWikiRulesList(enabled: boolean): UseQueryResult<WikiRulesListItem[], Error> {
  const s = useWikiSpace();
  return useQuery({ queryKey: wikiKeys.rules(s.key), queryFn: () => s.client.listWikiRules(), enabled, retry: false, staleTime: 0 });
}

/** 쓰기·실시간 뒤 위키 질의를 모두 다시 읽게 한다. */
export function useInvalidateWiki(): () => Promise<void> {
  const qc = useQueryClient();
  return useCallback(() => qc.invalidateQueries({ queryKey: wikiKeys.root }), [qc]);
}

/** 자기가 방금 쓴 페이지의 기록(위키 id + 경로 → 쓴 시각 ms). `wiki.changed`가 이 기록과 같으면 다시 불러오지 않는다. */
export type OwnWrites = Map<string, number>;
export const ownWriteKey = (wikiId: string, path: string): string => `${wikiId}\u0000${path}`;

/**
 * WS `wiki.changed` 구독: 알림은 본문 없이 "무엇이 바뀌었나"만 오므로 짧은 시간의 알림을 모아 한 번 무효화한다(300ms 디바운스).
 * 알림의 모든 페이지가 `ownWrites`에 최근(몇 초 안) 자기가 쓴 것으로 있고 외부 변경이 아니면 다시 불러오지 않는다.
 * `onChanged`: 무효화 직전에 모은 알림들(위키 id별로 합침)을 받는다. 끊겼다 다시 연결되면 놓친 알림을 메운다.
 */
export function useWikiLive(ownWrites: { readonly current: OwnWrites }, onChanged?: (events: readonly WikiChanged[]) => void): void {
  const { ws } = useApi();
  const invalidate = useInvalidateWiki();
  const latest = useRef({ invalidate, onChanged });
  useEffect(() => {
    latest.current = { invalidate, onChanged };
  });
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let pending: WikiChanged[] = [];
    const flush = () => {
      timer = undefined;
      const events = pending;
      pending = [];
      latest.current.onChanged?.(events);
      void latest.current.invalidate();
    };
    const isOwn = (c: WikiChanged): boolean => {
      if (c.external === true || c.deleted === true) return false;
      const paths = c.paths ?? [];
      if (paths.length === 0) return false;
      const now = Date.now();
      return paths.every((p) => {
        const at = ownWrites.current.get(ownWriteKey(c.wiki_id, p));
        return at !== undefined && now - at < WIKI_LIMITS.ownWriteTtlMs;
      });
    };
    const sub = ws.subscribeWiki((changed) => {
      if (isOwn(changed)) return;
      pending.push(changed);
      timer ??= setTimeout(flush, WIKI_LIMITS.liveDebounceMs);
    });
    let lost = ws.status === "reconnecting" || ws.status === "closed";
    const off = ws.onStatus((status) => {
      if (lost && status === "open") void latest.current.invalidate();
      lost = status === "reconnecting" || status === "closed" ? true : status === "open" ? false : lost;
    });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      off();
      sub.unsubscribe();
    };
  }, [ws, ownWrites]);
}
