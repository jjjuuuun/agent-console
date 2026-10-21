import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import type { Graph, Interaction, NodeRun, Run, RunEvent, Trace } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { INTERACTION_EVENT_PREFIX, RUN_REFETCH_DEBOUNCE_MS, SNAPSHOT_EVENT_PREFIXES } from "./runsConfig";
import { isActiveRun, lastSeqOf, mergeEvents } from "./runsLib";

export interface RunGraphResult {
  graph: Graph;
  /** 실행 당시 버전을 찾았는가(false면 현재 팀 구성으로 대신 보여 줌) */
  exact: boolean;
}

const NO_EVENTS: readonly RunEvent[] = [];
const runKey = (id: string) => ["run", id] as const;
const traceKey = (id: string) => ["run", id, "trace"] as const;
const interactionsKey = (id: string) => ["run", id, "interactions"] as const;

export async function loadRunGraph(rest: RestClient, graphId: string, versionHash: string): Promise<RunGraphResult> {
  try {
    const version = await rest.getGraphVersion(graphId, versionHash);
    if (version.content != null) return { graph: version.content as unknown as Graph, exact: true };
  } catch {
    // 실행 당시 버전이 없으면 현재 버전으로 대신한다.
  }
  const current = await rest.getGraph(graphId);
  return { graph: current.graph, exact: false };
}

export type LoadState = "loading" | "ready" | "error";

export interface RunView {
  run: Run | undefined;
  nodeRuns: readonly NodeRun[];
  /** 직접 자식 Run(중첩 팀, 만든 순). 서버가 안 채웠으면 undefined */
  children: readonly Run[] | undefined;
  snapshotStatus: LoadState;
  snapshotError: Error | null;
  reloadSnapshot(): void;
  events: readonly RunEvent[];
  eventsStatus: LoadState;
  reloadEvents(): void;
  /** 마지막으로 이벤트를 받은 시각(epoch 초, ts) */
  lastEventTs: number | undefined;
  trace: Trace | undefined;
  traceStatus: LoadState;
  reloadTrace(): void;
  interactions: readonly Interaction[];
  interactionsStatus: LoadState;
  reloadInteractions(): void;
  graph: RunGraphResult | undefined;
  graphStatus: LoadState;
  /** 이벤트 순서에 틈이 있어 다시 읽은 적이 있으면 증가 */
  resyncs: number;
}

function status(q: { isPending: boolean; isError: boolean }): LoadState {
  return q.isError ? "error" : q.isPending ? "loading" : "ready";
}

/**
 * 실행 한 건을 보는 데 필요한 서버 상태를 모은다(컨테이너 훅, UI 없음).
 * 스냅샷(`GET /runs/{id}`) → 이벤트 전체(`GET /runs/{id}/events`) → WS `run:<id>` `since_seq` 구독.
 * 같은 seq는 한 번만 적용하고, 순서에 틈이 있으면 이벤트를 다시 읽는다.
 * 이벤트가 오면 스냅샷·trace·상호작용을 디바운스 후 다시 읽는다(추정으로 계산하지 않고 서버 값을 쓴다).
 */
export function useRunView(runId: string, options: { /** false면 trace(위임 흐름)를 읽지 않는다. 기본 true */ trace?: boolean } = {}): RunView {
  const { rest, ws } = useApi();
  const qc = useQueryClient();

  const snapshot = useApiQuery(runKey(runId), (r) => r.getRun(runId), {
    refetchInterval: (query) => (query.state.data !== undefined && isActiveRun(query.state.data.run.status) ? 5000 : false),
  });
  const trace = useApiQuery(traceKey(runId), (r) => r.getRunTrace(runId), { enabled: options.trace ?? true });
  const interactions = useApiQuery(interactionsKey(runId), (r) => r.listRunInteractions(runId));
  const run = snapshot.data?.run;
  const graph = useApiQuery(["run", runId, "graph", run?.graph_id, run?.graph_version], (r) => loadRunGraph(r, run!.graph_id, run!.graph_version), {
    enabled: run !== undefined,
    staleTime: Infinity,
  });

  // 이벤트 상태는 실행 id와 함께 저장한다(다른 실행으로 바뀌면 effect에서 동기 setState 없이 비어 보이게).
  const [store, setStore] = useState<{ runId: string; events: readonly RunEvent[]; status: LoadState }>({ runId, events: [], status: "loading" });
  const events = store.runId === runId ? store.events : NO_EVENTS;
  const eventsStatus: LoadState = store.runId === runId ? store.status : "loading";
  const [resyncs, setResyncs] = useState(0);
  const eventsRef = useRef<readonly RunEvent[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pendingFlags = useRef({ snapshot: false, trace: false, interactions: false });
  const [reloadToken, setReloadToken] = useState(0);

  const flush = useCallback(() => {
    timer.current = undefined;
    const flags = pendingFlags.current;
    pendingFlags.current = { snapshot: false, trace: false, interactions: false };
    if (flags.snapshot) void qc.invalidateQueries({ queryKey: runKey(runId), exact: true });
    if (flags.trace) void qc.invalidateQueries({ queryKey: traceKey(runId) });
    if (flags.interactions) void qc.invalidateQueries({ queryKey: interactionsKey(runId) });
  }, [qc, runId]);

  const schedule = useCallback(
    (added: readonly RunEvent[]) => {
      const flags = pendingFlags.current;
      for (const e of added) {
        if (SNAPSHOT_EVENT_PREFIXES.some((p) => e.type.startsWith(p))) flags.snapshot = true;
        if (e.type.startsWith(INTERACTION_EVENT_PREFIX)) flags.interactions = true;
        flags.trace = true;
      }
      if (timer.current === undefined) timer.current = setTimeout(flush, RUN_REFETCH_DEBOUNCE_MS);
    },
    [flush],
  );

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    eventsRef.current = [];

    const apply = (incoming: readonly RunEvent[]) => {
      const merged = mergeEvents(eventsRef.current, incoming);
      if (merged.added > 0) {
        eventsRef.current = merged.events;
        setStore((cur) => ({ runId, events: merged.events, status: cur.runId === runId ? cur.status : "loading" }));
        schedule(incoming);
      }
      if (merged.gap) {
        setResyncs((n) => n + 1);
        void rest.listRunEvents(runId, { since_seq: lastSeqOf(eventsRef.current) }).then((list) => {
          if (!cancelled) apply(list);
        });
      }
    };

    rest
      .listRunEvents(runId)
      .then((list) => {
        if (cancelled) return;
        apply(list);
        setStore((cur) => ({ runId, events: cur.runId === runId ? cur.events : eventsRef.current, status: "ready" }));
        const sub = ws.subscribeRun(runId, (e) => apply([e]), { sinceSeq: lastSeqOf(eventsRef.current) });
        unsubscribe = () => sub?.unsubscribe();
      })
      .catch(() => {
        if (!cancelled) setStore((cur) => ({ runId, events: cur.runId === runId ? cur.events : NO_EVENTS, status: "error" }));
      });
    return () => {
      cancelled = true;
      unsubscribe?.();
      if (timer.current !== undefined) clearTimeout(timer.current);
      timer.current = undefined;
    };
  }, [rest, ws, runId, schedule, reloadToken]);

  return {
    run,
    nodeRuns: snapshot.data?.node_runs ?? [],
    children: snapshot.data?.children ?? undefined,
    snapshotStatus: status(snapshot),
    snapshotError: snapshot.error,
    reloadSnapshot: () => void snapshot.refetch(),
    events,
    eventsStatus,
    reloadEvents: () => setReloadToken((n) => n + 1),
    lastEventTs: events.length === 0 ? undefined : events[events.length - 1]!.ts,
    trace: trace.data,
    traceStatus: status(trace),
    reloadTrace: () => void trace.refetch(),
    interactions: interactions.data ?? [],
    interactionsStatus: status(interactions),
    reloadInteractions: () => void interactions.refetch(),
    graph: graph.data,
    graphStatus: run === undefined ? "loading" : status(graph),
    resyncs,
  };
}
