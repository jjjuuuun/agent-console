import { useCallback, useEffect, useRef, useState } from "react";
import type { LogAggregateRequest, LogAggregateRow, LogWidget } from "@agent-console/contracts";
import type { WidgetRegistry, WidgetResult } from "@agent-console/log-view";
import { ApiError } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { LOGS_LIMITS } from "./logsConfig";
import { aggregateKey, overrideWindow } from "./logsLib";

interface Entry {
  status: "loading" | "ok" | "error";
  rows?: readonly LogAggregateRow[];
  error?: { message: string; code?: string; detail?: string };
  updatedAt?: number;
}

export interface WidgetResults {
  results: Record<string, WidgetResult>;
  /** 위젯이 처음 화면에 보일 때(그때까지 집계 요청을 미룬다) */
  onVisible(id: string): void;
  refresh(id: string): void;
  refreshAll(): void;
}

export interface UseWidgetResultsOptions {
  widgets: readonly LogWidget[];
  registry: WidgetRegistry;
  /** 도구 줄 기간 덮어쓰기(null = 위젯 설정대로) */
  window: { since?: string; until?: string } | null;
  tz: string;
  /** 새 요청을 만들지 않는다(집계 서버를 쉬게 할 때). 기존 결과는 그대로 */
  paused?: boolean;
}

interface Job {
  key: string;
  body: LogAggregateRequest;
}

/**
 * 대시보드 위젯의 집계 결과: 보이는 위젯만 요청하고, 같은 질의(`group_by`·`metric`·`filter`·`tz`)는 한 번만 요청해 공유하며,
 * 동시 요청은 4개 이하 큐로 보낸다. 알 수 없는 종류(레지스트리에 없음)는 요청하지 않는다. 새로 고침 중에도 이전 본문은 유지한다.
 */
export function useWidgetResults({ widgets, registry, window, tz, paused = false }: UseWidgetResultsOptions): WidgetResults {
  const { rest } = useApi();
  const [entries, setEntries] = useState<Readonly<Record<string, Entry>>>({});
  const [visible, setVisible] = useState<ReadonlySet<string>>(new Set());
  const requested = useRef(new Set<string>());
  const queue = useRef<Job[]>([]);
  const active = useRef(0);
  const pump = useRef<() => void>(() => undefined);

  useEffect(() => {
    pump.current = () => {
      while (active.current < LOGS_LIMITS.maxConcurrentAggregates) {
        const job = queue.current.shift();
        if (job === undefined) return;
        active.current += 1;
        rest
          .aggregateLogs(job.body)
          .then((rows) => setEntries((cur) => ({ ...cur, [job.key]: { status: "ok", rows, updatedAt: Date.now() } })))
          .catch((e: unknown) => {
            const error = e instanceof ApiError ? { message: e.message, code: e.code, detail: `code: ${e.code}\nstatus: ${e.status}` } : { message: e instanceof Error ? e.message : String(e) };
            setEntries((cur) => ({ ...cur, [job.key]: { status: "error", error } }));
          })
          .finally(() => {
            active.current -= 1;
            pump.current();
          });
      }
    };
  }, [rest]);

  const requestOf = useCallback(
    (w: LogWidget): Job => {
      const filter = overrideWindow(w.query.filter as Record<string, unknown> | undefined, window);
      return { key: aggregateKey(w, filter, tz), body: { group_by: w.query.group_by ?? [], metric: w.query.metric, filter, tz } };
    },
    [window, tz],
  );

  /** 요청을 큐에 넣는다(이전 결과가 있으면 로딩 동안에도 본문을 유지한다). */
  const enqueue = useCallback((job: Job) => {
    requested.current.add(job.key);
    setEntries((cur) => ({ ...cur, [job.key]: { ...(cur[job.key] ?? {}), status: "loading" } }));
    if (!queue.current.some((j) => j.key === job.key)) queue.current.push(job);
    pump.current();
  }, []);

  useEffect(() => {
    if (paused) return;
    for (const w of widgets) {
      if (!registry.has(w.kind) || !visible.has(w.id)) continue;
      const job = requestOf(w);
      if (!requested.current.has(job.key)) enqueue(job);
    }
  }, [widgets, registry, visible, requestOf, paused, enqueue]);

  const results: Record<string, WidgetResult> = {};
  for (const w of widgets) {
    if (!registry.has(w.kind)) continue;
    const entry = entries[requestOf(w).key];
    results[w.id] =
      entry === undefined
        ? { loading: true }
        : { loading: entry.status === "loading", ...(entry.rows === undefined ? {} : { rows: entry.rows }), ...(entry.error === undefined ? {} : { error: entry.error }), ...(entry.updatedAt === undefined ? {} : { updatedAt: entry.updatedAt }) };
  }

  const onVisible = useCallback((id: string) => setVisible((cur) => (cur.has(id) ? cur : new Set(cur).add(id))), []);
  const refresh = useCallback(
    (id: string) => {
      const w = widgets.find((x) => x.id === id);
      if (w !== undefined && registry.has(w.kind)) enqueue(requestOf(w));
    },
    [widgets, registry, requestOf, enqueue],
  );
  const refreshAll = useCallback(() => {
    for (const w of widgets) if (registry.has(w.kind) && visible.has(w.id)) enqueue(requestOf(w));
  }, [widgets, registry, visible, requestOf, enqueue]);
  return { results, onVisible, refresh, refreshAll };
}
