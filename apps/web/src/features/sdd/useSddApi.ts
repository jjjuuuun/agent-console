/**
 * 스펙(SDD) 서버 상태 훅(TanStack Query). 화면은 이 훅만 부르고 REST를 직접 부르지 않는다.
 * 질의 키는 `["sdd", 공간, 종류, …]` — 실시간 변경·쓰기 뒤 `["sdd"]` 한 번으로 무효화한다. 공간 = 현재 프로젝트 id(없으면 빈 문자열).
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { ApiError, type ListSpecTasksParams, type SddClient, type Versioned } from "@agent-console/api-client";
import type { BulkActionsResult, EffectiveSyntax, ParsedTask, SddInfo, SpecDocumentContent, SpecSummary, SpecTemplateSummary, SpecView, TaskAction, TaskPlan, TraceMatrix } from "@agent-console/contracts/sdd";
import { useApi } from "../../app/ApiContext";
import { useProjectId } from "../../app/projectScope";
import { SDD_LIMITS } from "./sddConfig";

export const sddKeys = {
  root: ["sdd"] as const,
  info: (p: string) => ["sdd", p, "info"] as const,
  specs: (p: string) => ["sdd", p, "specs"] as const,
  spec: (p: string, id: string) => ["sdd", p, "spec", id] as const,
  doc: (p: string, id: string, doc: string) => ["sdd", p, "spec", id, "doc", doc] as const,
  tasks: (p: string, id: string, filter: string) => ["sdd", p, "spec", id, "tasks", filter] as const,
  syntax: (p: string, id: string) => ["sdd", p, "spec", id, "syntax"] as const,
  actions: (p: string, id: string, key: string) => ["sdd", p, "spec", id, "actions", key] as const,
  bulkActions: (p: string, id: string, keys: string) => ["sdd", p, "spec", id, "bulk-actions", keys] as const,
  plan: (p: string, id: string) => ["sdd", p, "spec", id, "plan"] as const,
  trace: (p: string, id: string) => ["sdd", p, "spec", id, "trace"] as const,
  templates: (p: string) => ["sdd", p, "templates"] as const,
  importFiles: (p: string, path: string) => ["sdd", p, "import-files", path] as const,
};

/** 현재 공간(프로젝트 id, 없으면 null)과 그 공간의 스펙 클라이언트. 컨테이너·훅이 함께 쓴다. */
export interface SddSpace {
  project: string | null;
  /** 질의 키에 쓰는 공간 문자열(프로젝트가 없으면 빈 문자열) */
  key: string;
  client: SddClient;
}

export function useSddSpace(): SddSpace {
  const { sdd } = useApi();
  const project = useProjectId();
  return useMemo(() => ({ project, key: project ?? "", client: sdd(project) }), [sdd, project]);
}

/** 화면 정보: 스펙 폴더·한도·능력·실행 라벨 표시 규칙. */
export function useSddInfo(): UseQueryResult<SddInfo, Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.info(s.key), queryFn: () => s.client.getSddInfo(), retry: false, staleTime: 30_000 });
}

export function useSpecList(): UseQueryResult<SpecSummary[], Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.specs(s.key), queryFn: () => s.client.listSpecs(), retry: false });
}

export function useSpecView(id: string): UseQueryResult<Versioned<SpecView>, Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.spec(s.key, id), queryFn: () => s.client.getSpec(id), retry: false, staleTime: 0 });
}

/** 문서 본문(`version_hash` = 본문 해시). 파일이 없으면 오류(`sdd.document_missing`)로 오며 재시도하지 않는다. */
export function useSpecDocument(id: string, doc: string | null): UseQueryResult<Versioned<SpecDocumentContent>, Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.doc(s.key, id, doc ?? ""), queryFn: () => s.client.getSpecDocument(id, doc ?? ""), enabled: doc !== null, retry: false, staleTime: 0 });
}

/** 작업 목록(서버 거르기). 거르기 값이 키에 들어가므로 바뀌면 다시 묻는다. */
export function useSpecTasks(id: string, params: ListSpecTasksParams, enabled: boolean): UseQueryResult<ParsedTask[], Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.tasks(s.key, id, JSON.stringify(params)), queryFn: () => s.client.listSpecTasks(id, params), enabled, retry: false, staleTime: 0 });
}

export function useSpecSyntax(id: string): UseQueryResult<EffectiveSyntax, Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.syntax(s.key, id), queryFn: () => s.client.getSpecSyntax(id), retry: false });
}

/** 작업 하나에서 할 수 있는 연동 동작(행의 [실행 ▾]를 열 때 읽는다, 30초 캐시). */
export function useTaskActions(id: string, key: string, enabled: boolean): UseQueryResult<TaskAction[], Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.actions(s.key, id, key), queryFn: () => s.client.listTaskActions(id, key), enabled, retry: false, staleTime: SDD_LIMITS.actionsStaleMs });
}

/** 고른 작업들의 동작 합집합과 작업별 가능 동작(한꺼번에 시작 대화상자). */
export function useBulkActions(id: string, keys: readonly string[], enabled: boolean): UseQueryResult<BulkActionsResult, Error> {
  const s = useSddSpace();
  return useQuery({
    queryKey: sddKeys.bulkActions(s.key, id, keys.join("\u0000")),
    queryFn: () => s.client.listBulkActions(id, { task_keys: keys as [string, ...string[]] }),
    enabled: enabled && keys.length > 0,
    retry: false,
    staleTime: SDD_LIMITS.actionsStaleMs,
  });
}

/** 계획(층·병목·막힘·순환). 서버가 계산한 값을 그대로 쓴다. */
export function useSpecPlan(id: string, enabled: boolean): UseQueryResult<TaskPlan, Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.plan(s.key, id), queryFn: () => s.client.getSpecPlan(id), enabled, retry: false, staleTime: 0 });
}

/** 요구 ↔ 작업 ↔ 실행 ↔ 검증 추적 표. */
export function useSpecTrace(id: string, enabled: boolean): UseQueryResult<TraceMatrix, Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.trace(s.key, id), queryFn: () => s.client.getSpecTrace(id), enabled, retry: false, staleTime: 0 });
}

/** 이 공간의 문서 틀 목록. */
export function useSpecTemplates(enabled = true): UseQueryResult<SpecTemplateSummary[], Error> {
  const s = useSddSpace();
  return useQuery({ queryKey: sddKeys.templates(s.key), queryFn: () => s.client.listSpecTemplates(), enabled, retry: false });
}

/** 쓰기·실시간 뒤 스펙 질의를 모두 다시 읽게 한다. */
export function useInvalidateSdd(): () => Promise<void> {
  const qc = useQueryClient();
  return useCallback(() => qc.invalidateQueries({ queryKey: sddKeys.root }), [qc]);
}

/**
 * WS `sdd.changed` 구독: 알림은 본문 없이 "무엇이 바뀌었나"만 오므로 짧은 시간의 알림을 모아 한 번 무효화한다(300ms 디바운스).
 * `ownHashes`에 든 `version_hash`는 자기가 방금 저장한 것이라 다시 불러오지 않는다. `onReconnect`: 끊겼다 다시 연결되면 놓친 알림을 메운다.
 */
export function useSddLive(ownHashes: { readonly current: ReadonlySet<string> }, onChanged?: (spec: string | null) => void): void {
  const { ws } = useApi();
  const invalidate = useInvalidateSdd();
  const latest = useRef({ invalidate, onChanged });
  useEffect(() => {
    latest.current = { invalidate, onChanged };
  });
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let pending: string | null | undefined;
    const flush = () => {
      timer = undefined;
      const spec = pending ?? null;
      pending = undefined;
      latest.current.onChanged?.(spec);
      void latest.current.invalidate();
    };
    const sub = ws.subscribeSdd((changed) => {
      if (changed.version_hash !== undefined && changed.version_hash !== null && ownHashes.current.has(changed.version_hash)) return;
      pending = pending === undefined ? changed.spec_id : pending === changed.spec_id ? pending : null;
      timer ??= setTimeout(flush, SDD_LIMITS.liveDebounceMs);
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
  }, [ws, ownHashes]);
}

/** 오류가 `code`(서버 오류 코드)인가. */
export function isApiError(e: unknown, code: string): e is ApiError {
  return e instanceof ApiError && e.code === code;
}
