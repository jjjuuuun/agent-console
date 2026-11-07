import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, type SpaceRestClient } from "@agent-console/api-client";
import type { Graph, Interaction, NodeRun, RecordSource, Run, RunEvent, Trace } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { useQuery } from "@tanstack/react-query";
import { useApiQuery } from "../../app/queries";
import { useAdoptLocatedProject, useProjectId } from "../../app/projectScope";
import { INTERACTION_EVENT_PREFIX, RUN_REFETCH_DEBOUNCE_MS, SNAPSHOT_EVENT_PREFIXES } from "./runsConfig";
import { isActiveRun, lastSeqOf, mergeEvents } from "./runsLib";

export interface RunGraphResult {
  graph: Graph;
  /** 실행 당시 버전을 찾았는가(false면 현재 팀 구성으로 대신 보여 줌) */
  exact: boolean;
}

const NO_EVENTS: readonly RunEvent[] = [];
/** 스냅샷 질의 키(기록 공간별). 접두 `["run", id, "snapshot"]`로 모두 다시 읽는다. */
const snapshotKey = (id: string, project: string | null) => ["run", id, "snapshot", project] as const;
const locateKey = (id: string) => ["run", id, "locate"] as const;
const traceKey = (id: string) => ["run", id, "trace"] as const;
const interactionsKey = (id: string) => ["run", id, "interactions"] as const;

const isNotFound = (error: unknown): boolean => error instanceof ApiError && error.status === 404;

/** 실행 당시 버전의 그래프(없으면 현재 버전). `rest`는 실행이 속한 공간(`space(run.project_id)`)의 클라이언트다. */
export async function loadRunGraph(rest: Pick<SpaceRestClient, "getGraph" | "getGraphVersion">, graphId: string, versionHash: string): Promise<RunGraphResult> {
  try {
    const version = await rest.getGraphVersion(graphId, versionHash);
    if (version.content != null) return { graph: version.content as unknown as Graph, exact: true };
  } catch {
    // 실행 당시 버전이 없으면 현재 버전으로 대신한다.
  }
  const current = await rest.getGraph(graphId);
  return { graph: current.graph, exact: false };
}

/** 실행이 속한 공간(프로젝트 또는 공용)에서 그 실행의 그래프를 읽는다. 실행이 없으면 질의하지 않는다. */
export function useRunGraph(run: Pick<Run, "id" | "graph_id" | "graph_version" | "project_id"> | undefined) {
  const { space } = useApi();
  const projectId = run?.project_id ?? null;
  return useQuery<RunGraphResult, Error>({
    queryKey: ["run", run?.id ?? "", "graph", projectId, run?.graph_id, run?.graph_version],
    queryFn: () => loadRunGraph(space(projectId), run!.graph_id, run!.graph_version),
    enabled: run !== undefined,
    staleTime: Infinity,
  });
}

export type LoadState = "loading" | "ready" | "error";

/** 실행이 속한 기록 공간을 알아낸 결과. `ready`가 거짓이면 다른 공간을 찾는 중이다(없음 표시를 미룬다). */
export interface RunScope {
  /** Run 단위 호출의 `?project=` 값(null = 붙이지 않음, 앱 기록 또는 서버가 아는 자리). */
  project: string | null;
  ready: boolean;
}

/** 앱 기록 출처(목록 페이지 `source`). 이 출처의 행은 `project_id`가 있어도 앱 기록에 있다. */
const APP_SOURCE: RecordSource = "app";

/** 실행 상세로 넘기는 주소 상태: 그 실행이 있을 기록 공간 힌트(목록에서 연 경우). */
export interface RunOpenState {
  runProject: string | null;
}

/** 목록 항목 → 상세 주소 상태. 앱 기록 출처 행은 null(앱 기록), 아니면 항목의 `project_id`. */
export function runOpenState(run: Pick<Run, "project_id">, source?: string): RunOpenState {
  return { runProject: source === APP_SOURCE ? null : (run.project_id ?? null) };
}

/** 주소 상태에서 공간 힌트를 꺼낸다(없거나 모양이 다르면 undefined = 현재 프로젝트). */
export function runProjectHint(state: unknown): string | null | undefined {
  if (state === null || typeof state !== "object" || !("runProject" in state)) return undefined;
  const value = (state as { runProject: unknown }).runProject;
  return value === null || typeof value === "string" ? value : undefined;
}

/**
 * 실행 위치 고르기(순수 함수, `useRunView`가 쓴다).
 * 1. 처음 부를 공간(`first`) = 목록 항목 등에서 받은 힌트, 없으면 현재 프로젝트.
 * 2. 그 공간에서 404가 나면 서버 `GET /runs/{id}/locate`(계약 0.14.8)의 `project_id`. 찾는 동안은 `ready: false`.
 * 3. 찾기가 실패하면(없음·여러 곳·옛 서버) `first` - 상세가 그 결과(404 등)를 보인다.
 */
export function chooseRunScope(first: string | null, firstNotFound: boolean, located: { project_id?: string | null } | undefined, locateFailed: boolean): RunScope {
  if (!firstNotFound) return { project: first, ready: true };
  if (located !== undefined) return { project: located.project_id ?? null, ready: true };
  return { project: first, ready: locateFailed };
}

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
export function useRunView(
  runId: string,
  options: {
    /** false면 trace(위임 흐름)를 읽지 않는다. 기본 true */
    trace?: boolean;
    /** 그 실행이 있을 기록 공간 힌트(예: 실행 목록 항목의 `project_id`). 생략 = 현재 프로젝트 */
    project?: string | null;
  } = {},
): RunView {
  const { rest, ws } = useApi();
  const qc = useQueryClient();
  const current = useProjectId();
  const first = options.project !== undefined ? options.project : current;

  const refetchInterval = (query: { state: { data: { run: Run } | undefined } }) => (query.state.data !== undefined && isActiveRun(query.state.data.run.status) ? 5000 : false);
  // 1) 힌트(없으면 현재 프로젝트)로 먼저 부른다. 404면 2) 위치를 찾아 3) 그 공간으로 다시 부른다(재시작 뒤 주소로 바로 연 실행).
  const firstSnapshot = useApiQuery(snapshotKey(runId, first), (r) => r.getRun(runId, first), { refetchInterval });
  const firstNotFound = isNotFound(firstSnapshot.error) && runId !== "";
  const located = useApiQuery(locateKey(runId), (r) => r.locateRun(runId), { enabled: firstNotFound, retry: false, staleTime: 60_000 });
  const scope = chooseRunScope(first, firstNotFound, located.data, located.isError);
  // 주소로 다른 프로젝트의 실행을 열었으면 현재 프로젝트를 그 프로젝트로 바꾼다(사이드바·목록·칩·주소 `prj` 일치)
  useAdoptLocatedProject(firstNotFound ? located.data?.project_id : undefined);
  const moved = scope.project !== first;
  const movedSnapshot = useApiQuery(snapshotKey(runId, scope.project), (r) => r.getRun(runId, scope.project), { enabled: moved, refetchInterval });
  const snapshot = moved ? movedSnapshot : firstSnapshot;
  const project = scope.project;
  const run = snapshot.data?.run;
  // 이벤트·상호작용은 그 공간에서 스냅샷을 받은 뒤에 읽는다(다른 공간을 찾는 중에 404를 받지 않게, 서버도 그 자리를 기억한다)
  const hasRun = run !== undefined;
  // 위임 흐름은 Run 단위 경로에 공간이 없어 서버가 아는 자리(스냅샷 조회가 기억)를 쓴다 - 스냅샷 다음에 읽는다
  const trace = useApiQuery(traceKey(runId), (r) => r.getRunTrace(runId), { enabled: (options.trace ?? true) && hasRun });
  const interactions = useApiQuery([...interactionsKey(runId), project], (r) => r.listRunInteractions(runId, project), { enabled: hasRun });
  const graph = useRunGraph(run);

  // 이벤트 상태는 실행 id·공간과 함께 저장한다(다른 실행·공간으로 바뀌면 effect에서 동기 setState 없이 비어 보이게).
  const storeKey = `${runId}\u0000${project ?? ""}`;
  const [store, setStore] = useState<{ key: string; events: readonly RunEvent[]; status: LoadState }>({ key: storeKey, events: [], status: "loading" });
  const events = store.key === storeKey ? store.events : NO_EVENTS;
  const eventsStatus: LoadState = !hasRun ? "loading" : store.key === storeKey ? store.status : "loading";
  const [resyncs, setResyncs] = useState(0);
  const eventsRef = useRef<readonly RunEvent[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pendingFlags = useRef({ snapshot: false, trace: false, interactions: false });
  const [reloadToken, setReloadToken] = useState(0);

  const flush = useCallback(() => {
    timer.current = undefined;
    const flags = pendingFlags.current;
    pendingFlags.current = { snapshot: false, trace: false, interactions: false };
    // 지금 공간의 스냅샷만(찾기 전에 404를 받은 공간은 다시 부르지 않는다)
    if (flags.snapshot) void qc.invalidateQueries({ queryKey: snapshotKey(runId, project), exact: true });
    if (flags.trace) void qc.invalidateQueries({ queryKey: traceKey(runId) });
    if (flags.interactions) void qc.invalidateQueries({ queryKey: interactionsKey(runId) });
  }, [qc, runId, project]);

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
    if (!hasRun) return;
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    eventsRef.current = [];
    const params = project === null ? {} : { project };

    const apply = (incoming: readonly RunEvent[]) => {
      const merged = mergeEvents(eventsRef.current, incoming);
      if (merged.added > 0) {
        eventsRef.current = merged.events;
        setStore((cur) => ({ key: storeKey, events: merged.events, status: cur.key === storeKey ? cur.status : "loading" }));
        schedule(incoming);
      }
      if (merged.gap) {
        setResyncs((n) => n + 1);
        void rest.listRunEvents(runId, { since_seq: lastSeqOf(eventsRef.current), ...params }).then((list) => {
          if (!cancelled) apply(list);
        });
      }
    };

    rest
      .listRunEvents(runId, project === null ? undefined : params)
      .then((list) => {
        if (cancelled) return;
        apply(list);
        setStore((cur) => ({ key: storeKey, events: cur.key === storeKey ? cur.events : eventsRef.current, status: "ready" }));
        const sub = ws.subscribeRun(runId, (e) => apply([e]), { sinceSeq: lastSeqOf(eventsRef.current) });
        unsubscribe = () => sub?.unsubscribe();
      })
      .catch(() => {
        if (!cancelled) setStore((cur) => ({ key: storeKey, events: cur.key === storeKey ? cur.events : NO_EVENTS, status: "error" }));
      });
    return () => {
      cancelled = true;
      unsubscribe?.();
      if (timer.current !== undefined) clearTimeout(timer.current);
      timer.current = undefined;
    };
  }, [rest, ws, runId, project, storeKey, hasRun, schedule, reloadToken]);

  return {
    run,
    nodeRuns: snapshot.data?.node_runs ?? [],
    children: snapshot.data?.children ?? undefined,
    snapshotStatus: scope.ready ? status(snapshot) : "loading",
    snapshotError: scope.ready ? snapshot.error : null,
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
