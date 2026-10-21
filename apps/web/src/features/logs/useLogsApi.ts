/**
 * 로그 서버 상태 훅(TanStack Query). 화면은 이 훅만 부르고 REST를 직접 부르지 않는다.
 * 질의 키는 `["logs", 종류, …]` — 수집·재연결 때 `["logs"]` 한 번으로 무효화한다.
 */
import { useMemo } from "react";
import { keepPreviousData, useInfiniteQuery, type UseQueryResult } from "@tanstack/react-query";
import { ApiError, type LogQueryParams, type RestClient } from "@agent-console/api-client";
import type { LogEventPage, LogQuerySchema, LogSourceInfo, LogTaxonomy } from "@agent-console/contracts";
import { toTaxonomyView, type LogTaxonomyView } from "@agent-console/log-view";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { LOGS_LIMITS } from "./logsConfig";
import { paramsKey } from "./logsLib";

export const logKeys = {
  root: ["logs"] as const,
  sources: () => ["logs", "sources"] as const,
  taxonomy: () => ["logs", "taxonomy"] as const,
  schema: () => ["logs", "schema"] as const,
  classifiers: () => ["logs", "classifiers"] as const,
  templates: () => ["logs", "templates"] as const,
  total0: () => ["logs", "total0"] as const,
  sessions: (key: string) => ["logs", "sessions", key] as const,
  timeline: (session: string, key: string) => ["logs", "timeline", session, key] as const,
  trace: (session: string) => ["logs", "trace", session] as const,
  events: (key: string) => ["logs", "events", key] as const,
  event: (uid: string) => ["logs", "event", uid] as const,
  handoffs: (key: string) => ["logs", "handoffs", key] as const,
  runLogs: (runId: string, key: string) => ["logs", "run", runId, key] as const,
};

/** 출처 목록·상태. */
export function useLogSources(enabled = true): UseQueryResult<LogSourceInfo[], Error> {
  return useApiQuery(logKeys.sources(), (rest) => rest.listLogSources(), { enabled });
}

/** 유효 분류 체계의 원본(없거나 실패하면 undefined — 화면은 그대로 동작한다). */
export function useLogTaxonomy(enabled = true): UseQueryResult<LogTaxonomy, Error> {
  return useApiQuery(logKeys.taxonomy(), (rest) => rest.getLogTaxonomy(), { enabled, retry: false, staleTime: 60_000, meta: { silentBackgroundError: true } });
}

/** 분류 체계의 화면용 조회 객체(비어 있거나 실패해도 id 이름으로 동작). */
export function useLogTaxonomyView(enabled = true): LogTaxonomyView {
  const q = useLogTaxonomy(enabled);
  return useMemo(() => toTaxonomyView(q.data), [q.data]);
}

/** 차원·지표·필터 이름 목록. 404·실패면 data가 없고 호출하는 쪽이 자유 입력으로 폴백한다. */
export function useLogSchema(enabled = true): UseQueryResult<LogQuerySchema, Error> {
  return useApiQuery(logKeys.schema(), (rest) => rest.getLogSchema(), { enabled, retry: false, staleTime: 5 * 60_000, meta: { silentBackgroundError: true } });
}

/** 등록된 분류기 디스크립터(출처 설정 폼의 분류기 선택지). */
export function useLogClassifiers(enabled = true) {
  return useApiQuery(logKeys.classifiers(), (rest) => rest.listLogClassifiers(), { enabled, retry: false, meta: { silentBackgroundError: true } });
}

export function useLogSessions(params: LogQueryParams, enabled = true) {
  const key = paramsKey(params);
  return useApiQuery(logKeys.sessions(key), (rest) => rest.listLogSessions(params), { enabled, placeholderData: keepPreviousData });
}

export function useLogTimeline(session: string, params: LogQueryParams, enabled = true) {
  const key = paramsKey(params);
  return useApiQuery(logKeys.timeline(session, key), (rest) => rest.getLogTimeline(session, params), { enabled, placeholderData: keepPreviousData, retry: (n, e) => n < 1 && !(e instanceof ApiError && e.status < 500) });
}

export function useLogTrace(session: string, enabled: boolean) {
  return useApiQuery(logKeys.trace(session), (rest) => rest.getLogSessionTrace(session), { enabled, retry: false });
}

export function useLogEventDetail(uid: string | null) {
  return useApiQuery(logKeys.event(uid ?? ""), (rest: RestClient) => rest.getLogEvent(uid ?? ""), { enabled: uid !== null && uid !== "", staleTime: LOGS_LIMITS.detailStaleMs });
}

export function useLogHandoffs(params: LogQueryParams, enabled = true) {
  const key = paramsKey(params);
  return useApiQuery(logKeys.handoffs(key), (rest) => rest.getLogHandoffs(params), { enabled, placeholderData: keepPreviousData });
}

export function useLogTemplates(enabled: boolean) {
  return useApiQuery(logKeys.templates(), (rest) => rest.listLogDashboardTemplates(), { enabled, retry: false });
}

/** 필터 없는 `limit=1` 조회(빈 상태 B/C 판정). 이벤트가 하나라도 있으면 true, 실패면 undefined(C로 본다). */
export function useAnyEvents(enabled: boolean): boolean | undefined {
  const q = useApiQuery(
    logKeys.total0(),
    async (rest) => {
      const page = await rest.listLogEvents({ limit: 1 });
      return (page.items?.length ?? 0) > 0 || (page.total ?? 0) > 0;
    },
    { enabled, retry: false, staleTime: 0 },
  );
  return q.isError ? undefined : q.data;
}

/** 키셋 페이지 이벤트 목록(첫 페이지 `limit`개). `fetchNextPage`는 한 번에 하나만 진행된다. */
export function useLogEventPages(params: LogQueryParams, enabled = true) {
  const { rest } = useApi();
  const key = paramsKey(params);
  return useInfiniteQuery({
    queryKey: logKeys.events(key),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => rest.listLogEvents(typeof pageParam === "string" ? { ...params, cursor: pageParam } : params),
    getNextPageParam: (last: LogEventPage) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

/** 실행에 연결된 세션 로그(첫 페이지 `limit`개 + 키셋). */
export function useRunLogPages(runId: string, params: LogQueryParams, enabled: boolean) {
  const { rest } = useApi();
  const key = paramsKey(params);
  return useInfiniteQuery({
    queryKey: logKeys.runLogs(runId, key),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => rest.listRunLogs(runId, typeof pageParam === "string" ? { ...params, cursor: pageParam } : params),
    getNextPageParam: (last: LogEventPage) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}
