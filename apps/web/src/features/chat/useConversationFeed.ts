import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import type { WsClient } from "@agent-console/api-client";
import type { ChatTurn, ConversationSummary, EdgeTypeDescriptor, Graph, Interaction, RunEvent, TeamPlanSummary } from "@agent-console/contracts";
import { chatPaths } from "./paths";
import type { ProgressStep } from "@agent-console/chat";
import { useApi } from "../../app/ApiContext";
import { useConnectionStatus } from "../../app/useConnectionStatus";
import { useApiQuery } from "../../app/queries";
import { chatKeys } from "./chatData";
import { assembleTurns } from "./lib/assemble";
import { upsertConversation } from "./lib/conversations";
import { applyRunEvent, emptyLiveRun, foldRunEvents, hasReachedEnd, isActiveStatus, mergeLiveRuns, type LiveRun } from "./lib/liveRun";
import { buildProgressSteps } from "./lib/progress";
import { chatMessages } from "./chatMessages";
import { agentOfNode as agentOfNodeSpec, nodeName, replyEdgesOf, type NamingContext } from "./lib/team";

/** 한 번에 가져오는 턴 수와, 진행 줄을 위해 이벤트를 읽는 최근 끝난 턴 수. */
export const TURN_PAGE = 20;
export const HISTORY_RUNS = 5;
const noop = () => {};

type LiveAction = { runId: string; event: RunEvent };

function liveReducer(state: Readonly<Record<string, LiveRun>>, { runId, event }: LiveAction): Readonly<Record<string, LiveRun>> {
  const cur = state[runId] ?? emptyLiveRun(runId);
  const next = applyRunEvent(cur, event);
  return next === cur && state[runId] !== undefined ? state : { ...state, [runId]: next };
}

/**
 * WS `run:<id>` 구독으로 진행 중인 Run의 상태를 쌓는다. 구독은 재생부터 시작하므로 중복 seq는 reducer가 버린다.
 * 이미 이벤트를 받기 시작한 Run은 `runIds`에서 빠져도(서버 상태가 먼저 "끝"으로 보여도) 종료 이벤트(`run.<종료>`)를
 * 받을 때까지 구독을 유지한다. 완료 알림은 다른 토픽이라 마지막 이벤트보다 먼저 올 수 있고, 서버 계약상
 * 종료 이벤트가 그 Run의 마지막 이벤트다(5.2R.39·40).
 */
export function useActiveRunEvents(ws: WsClient, runIds: readonly string[], onEvent: (event: RunEvent) => void): Readonly<Record<string, LiveRun>> {
  const [state, dispatch] = useReducer(liveReducer, {});
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  });
  const open = Object.values(state).filter((lv) => !hasReachedEnd(lv)).map((lv) => lv.runId);
  const key = [...new Set([...runIds, ...open])].join(",");
  useEffect(() => {
    const subs = (key === "" ? [] : key.split(",")).map((runId) =>
      ws.subscribeRun(runId, (event) => {
        dispatch({ runId, event });
        onEventRef.current(event);
      }),
    );
    return () => subs.forEach((s) => s?.unsubscribe());
  }, [ws, key]);
  return state;
}

/** 이미 끝난 최근 Run의 이벤트를 한 번 읽어 진행 줄·오류 문구를 만든다. */
export function useHistoryRuns(runIds: readonly string[]): Readonly<Record<string, LiveRun>> {
  const { rest } = useApi();
  const key = runIds.join(",");
  const combine = useCallback(
    (results: { data: RunEvent[] | undefined }[]): Record<string, LiveRun> => {
      const ids = key === "" ? [] : key.split(",");
      const out: Record<string, LiveRun> = {};
      ids.forEach((runId, i) => {
        const data = results[i]?.data;
        if (data) out[runId] = foldRunEvents(runId, data);
      });
      return out;
    },
    [key],
  );
  return useQueries({
    queries: runIds.map((runId) => ({
      queryKey: chatKeys.runEvents(runId),
      queryFn: () => rest.listRunEvents(runId),
      staleTime: Infinity,
    })),
    combine,
  });
}

/**
 * 열린 대화의 상호작용 최신 상태. 전역 `interactions` 토픽(모든 상태 변화)에서 이 대화의 것을 모으고,
 * 응답 호출의 결과(`apply`)도 같은 곳에 반영한다.
 */
export function useInteractionStore(ws: WsClient, conversationId: string, enabled = true, rootRunIds: ReadonlySet<string> = EMPTY_SET) {
  const [map, setMap] = useState<ReadonlyMap<string, Interaction>>(new Map());
  const apply = useCallback((interaction: Interaction) => setMap((cur) => new Map(cur).set(interaction.id, interaction)), []);
  // 중첩 팀 자식 실행의 요청은 대화 id가 없을 수 있다. 루트 실행(= 이 대화의 턴)에 속하면 이 대화의 것이다.
  const rootsRef = useRef(rootRunIds);
  useEffect(() => {
    rootsRef.current = rootRunIds;
  });
  useEffect(() => {
    if (!enabled) return;
    const sub = ws.subscribeInteractions((i) => {
      if (i.conversation_id === conversationId || (i.root_run_id != null && rootsRef.current.has(i.root_run_id))) apply(i);
    });
    return () => sub?.unsubscribe();
  }, [ws, conversationId, apply, enabled]);
  return { map, apply };
}
const EMPTY_SET: ReadonlySet<string> = new Set();

export interface FeedInput {
  conversationId: string;
  ws: WsClient;
  graph: Graph | undefined;
  /** 계획 요약(답변 자리). 아직 못 받았으면 undefined */
  plan: TeamPlanSummary | undefined;
  kinds: ReadonlyMap<string, EdgeTypeDescriptor>;
  naming: NamingContext;
  /** 상호작용 구독 여부(연동 부분이 꺼졌으면 false, 기본 true) */
  interactions?: boolean;
}

export interface Feed {
  /** 서버 턴 + 실시간 상태로 조립한 화면 턴(오래된 순) */
  turns: ChatTurn[];
  loading: boolean;
  error: Error | null;
  refetch: () => void;
  loadOlder: () => void;
  loadingOlder: boolean;
  hasMore: boolean;
  progress: Record<string, readonly ProgressStep[]>;
  streaming: Record<string, string>;
  errors: Record<string, string>;
  applyInteraction: (interaction: Interaction) => void;
  /**
   * 중첩 팀 자식 실행 안 요청이면 그 위치: 부모 노드 이름들(루트에 가까운 쪽부터)과, 요청의 `node_path`가 속한 그래프(알 때만).
   * 자식 요청의 `node_path`는 자식 안 상대 경로라 루트 그래프로는 이름을 못 찾는다(5R.13 QA). 루트 실행 안 요청이면 undefined.
   */
  nestedOrigin: (interaction: Interaction) => { path: string[]; graph: Graph | undefined } | undefined;
  /** 독립 위임으로 불린 대상 노드 id → 위임자 노드 이름(답변 머리 "{위임자}가 맡긴 {대상}"). 호출 NodeRun 이벤트가 있는 턴만 */
  delegators: ReadonlyMap<string, string>;
  /** 턴·대기열·대화 요약을 다시 읽는다(짧게 모아서) */
  refresh: () => void;
}

/**
 * 한 대화의 턴 목록 + 실시간 상태. 데이터 연결 전용(표현은 `@agent-console/chat`).
 * - 최근 `TURN_PAGE`개를 읽고 위로 스크롤하면 `before`(가장 오래된 턴의 run id)로 더 읽는다.
 * - 진행 중인 턴은 `run:<id>`를 구독하고, 재접속하면 WS 클라이언트가 `since_seq`로 이어 받는다.
 * - 요약(`conversation:<id>`)이 바뀌면 턴·대기열을 다시 읽어 보정한다.
 */
export function useConversationFeed({ conversationId, ws, graph, plan, kinds, naming, interactions: interactionsEnabled = true }: FeedInput): Feed {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const [older, setOlder] = useState<ChatTurn[]>([]);
  const [moreBefore, setMoreBefore] = useState<boolean | undefined>(undefined);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const latest = useApiQuery(chatKeys.turns(conversationId), (r) => r.listTurns(conversationId, { limit: TURN_PAGE }));
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const refresh = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void queryClient.invalidateQueries({ queryKey: chatKeys.turns(conversationId) });
      void queryClient.invalidateQueries({ queryKey: chatKeys.queue(conversationId) });
      void queryClient.invalidateQueries({ queryKey: chatKeys.conversation(conversationId) });
      void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    }, 120);
  }, [queryClient, conversationId]);
  useEffect(() => () => clearTimeout(timer.current), []);

  // 요약 구독: 새 턴·상태·대기 수가 바뀌면 목록 캐시를 갱신하고 턴을 보정한다.
  useEffect(() => {
    const sub = ws.subscribeConversation(conversationId, (summary: ConversationSummary) => {
      queryClient.setQueryData<ConversationSummary[]>(chatKeys.conversations(), (cur) => (cur ? upsertConversation(cur, summary) : cur));
      refresh();
    });
    return () => sub?.unsubscribe();
  }, [ws, conversationId, queryClient, refresh]);

  // 연결이 끊겼다가 돌아오면 턴을 다시 읽어 놓친 변화를 보정한다(실행 이벤트는 클라이언트가 since_seq로 이어 받는다).
  const connection = useConnectionStatus(ws);
  const wasOpen = useRef(connection === "open");
  useEffect(() => {
    if (connection === "open" && !wasOpen.current) refresh();
    wasOpen.current = connection === "open";
  }, [connection, refresh]);

  const serverTurns = useMemo(() => {
    const head = latest.data ?? [];
    const seen = new Set(head.map((t) => t.run_id));
    return [...older.filter((t) => !seen.has(t.run_id)), ...head];
  }, [older, latest.data]);

  const hasMore = moreBefore ?? (latest.data !== undefined && latest.data.length >= TURN_PAGE);
  const loadOlder = useCallback(() => {
    const first = serverTurns[0];
    if (!first || loadingOlder) return;
    setLoadingOlder(true);
    rest
      .listTurns(conversationId, { before: first.run_id, limit: TURN_PAGE })
      .then((page) => {
        setOlder((cur) => [...page, ...cur]);
        setMoreBefore(page.length >= TURN_PAGE);
      })
      .catch(() => setMoreBefore(false))
      .finally(() => setLoadingOlder(false));
  }, [rest, conversationId, serverTurns, loadingOlder]);

  const turnRunIds = useMemo(() => new Set(serverTurns.map((t) => t.run_id)), [serverTurns]);
  const interactions = useInteractionStore(ws, conversationId, interactionsEnabled, turnRunIds);

  const onEvent = useCallback(
    (event: RunEvent) => {
      if (event.type.startsWith("run.") || event.type.startsWith("interaction.")) refresh();
    },
    [refresh],
  );
  // 진행 중인 턴을 구독한다. 서버가 먼저 끝났다고 해도 종료 이벤트를 못 받은 Run은 훅이 구독을 유지한다(useActiveRunEvents).
  const activeIds = useMemo(() => serverTurns.filter((t) => isActiveStatus(t.status)).map((t) => t.run_id), [serverTurns]);
  const wsLive = useActiveRunEvents(ws, activeIds, onEvent);
  const historyIds = useMemo(
    () => serverTurns.filter((t) => !isActiveStatus(t.status)).slice(-HISTORY_RUNS).map((t) => t.run_id),
    [serverTurns],
  );
  const history = useHistoryRuns(historyIds);
  const live = useMemo(() => mergeLiveRuns(history, wsLive), [history, wsLive]);

  // 서버가 끝났다고 한 턴의 기록이 종료 이벤트까지 안 채워졌으면(구독을 끊은 뒤이거나 먼저 읽은 경우) 한 번 다시 읽는다.
  const reread = useRef(new Set<string>());
  useEffect(() => {
    for (const t of serverTurns) {
      if (isActiveStatus(t.status) || hasReachedEnd(live[t.run_id]) || reread.current.has(t.run_id)) continue;
      if (!historyIds.includes(t.run_id) || history[t.run_id] === undefined) continue; // 아직 첫 읽기 전이면 기다린다
      reread.current.add(t.run_id);
      void queryClient.invalidateQueries({ queryKey: chatKeys.runEvents(t.run_id) });
    }
  }, [serverTurns, live, history, historyIds, queryClient]);

  // 중첩 팀 자식 실행: 부모 이벤트(자식 실행 시작 이벤트)로 알게 된 자식의 이벤트를 따로 읽어 칩의 하위 단계를 만든다.
  // 진행 중인 자식은 구독하고, 끝난 자식은 한 번 읽는다. 부모 턴이 이미 끝났으면 자식도 끝난 것으로 본다.
  const { activeChildIds, doneChildIds, childGraphIds } = useMemo(() => {
    const active: string[] = [];
    const done: string[] = [];
    const graphIds = new Set<string>();
    for (const turn of serverTurns) {
      const lv = live[turn.run_id];
      if (lv === undefined) continue;
      const rootActive = isActiveStatus(turn.status);
      for (const c of lv.children) {
        if (c.graphId !== undefined) graphIds.add(c.graphId);
        (c.finishedStatus === undefined && rootActive ? active : done).push(c.runId);
      }
    }
    return { activeChildIds: active, doneChildIds: done, childGraphIds: [...graphIds] };
  }, [serverTurns, live]);
  const childWs = useActiveRunEvents(ws, activeChildIds, noop);
  const childHistory = useHistoryRuns(doneChildIds);
  const childLive = useMemo(() => mergeLiveRuns(childHistory, childWs), [childHistory, childWs]);
  const childGraphResults = useQueries({
    queries: childGraphIds.map((gid) => ({ queryKey: chatKeys.graph(gid), queryFn: () => rest.getGraph(gid), staleTime: 60_000 })),
    combine: (results) => results.map((r) => r.data),
  });
  const childGraphs = useMemo(() => {
    const out: Record<string, Graph> = {};
    childGraphIds.forEach((gid, i) => {
      const g = childGraphResults[i]?.graph;
      if (g !== undefined) out[gid] = g;
    });
    return out;
  }, [childGraphIds, childGraphResults]);

  const replyEdges = useMemo(() => replyEdgesOf(plan), [plan]);
  const nodesById = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);
  const agentOfNode = useCallback(
    (nodeId: string) => {
      const node = nodesById.get(nodeId);
      return node ? (agentOfNodeSpec(node, naming)?.id ?? null) : null;
    },
    [nodesById, naming],
  );

  const turns = useMemo(
    () => assembleTurns({ serverTurns, live, interactions: interactions.map, replyEdges, agentOfNode }),
    [serverTurns, live, interactions.map, replyEdges, agentOfNode],
  );

  const progress = useMemo(() => {
    const out: Record<string, readonly ProgressStep[]> = {};
    for (const t of turns) {
      const lv = live[t.run_id];
      if (lv) {
        const steps = buildProgressSteps({
          live: lv,
          graph,
          kinds,
          naming,
          skippedWith: chatMessages.progress.skippedWith,
          runId: t.run_id,
          childLive,
          childGraphs,
          childHref: chatPaths.run,
          executableOf: (typeId) => naming.nodeTypes.get(typeId)?.executable !== false,
        });
        if (steps.length > 0) out[t.run_id] = steps;
      }
    }
    return out;
  }, [turns, live, graph, kinds, naming, childLive, childGraphs]);

  // 스트리밍은 진행 중인 마지막 턴의 것을, 스트림이 켜진 답변 노드 것만 보인다.
  const streaming = useMemo(() => {
    const active = [...turns].reverse().find((t) => isActiveStatus(t.status));
    const lv = active ? live[active.run_id] : undefined;
    const out: Record<string, string> = {};
    if (lv) for (const re of replyEdges) if (re.stream && lv.streaming[re.nodeId] !== undefined) out[re.nodeId] = lv.streaming[re.nodeId]!;
    return out;
  }, [turns, live, replyEdges]);

  const errors = useMemo(() => {
    const out: Record<string, string> = {};
    for (const t of turns) {
      const message = live[t.run_id]?.error?.message;
      if (message) out[t.run_id] = message;
    }
    return out;
  }, [turns, live]);

  // 자식 Run id → 부모 Run·부모 노드·자식 팀 구성(부모의 자식 실행 시작 이벤트에서)
  const origins = useMemo(() => {
    const map = new Map<string, { parent: string; nodeId: string; graphId: string | undefined }>();
    for (const lv of [...Object.values(live), ...Object.values(childLive)]) for (const c of lv.children) map.set(c.runId, { parent: lv.runId, nodeId: c.nodeId, graphId: c.graphId });
    return map;
  }, [live, childLive]);
  const nestedOrigin = useCallback(
    (i: Interaction) => {
      if (i.root_run_id == null || i.root_run_id === i.run_id) return undefined;
      const path: string[] = [];
      let graphOfRun: Graph | undefined;
      let cur: string | undefined = i.run_id;
      for (let guard = 0; cur !== undefined && cur !== i.root_run_id && guard < 16; guard += 1) {
        const o = origins.get(cur);
        if (o === undefined) break;
        if (cur === i.run_id) graphOfRun = o.graphId === undefined ? undefined : childGraphs[o.graphId];
        const parentOrigin = origins.get(o.parent);
        const parentGraph = o.parent === i.root_run_id ? graph : parentOrigin?.graphId === undefined ? undefined : childGraphs[parentOrigin.graphId];
        const node = parentGraph?.nodes?.find((n) => n.id === o.nodeId);
        path.unshift(nodeName(node, o.nodeId, naming));
        cur = o.parent;
      }
      return { path: path.length > 0 ? path : [""], graph: graphOfRun };
    },
    [origins, childGraphs, graph, naming],
  );

  const delegators = useMemo(() => {
    const out = new Map<string, string>();
    const nodes = new Map((graph?.nodes ?? []).map((n) => [n.id, n]));
    for (const lv of Object.values(live)) for (const c of lv.calls) out.set(c.target, nodeName(nodes.get(c.delegator), c.delegator, naming));
    return out;
  }, [live, graph, naming]);

  return {
    turns,
    delegators,
    nestedOrigin,
    loading: latest.isLoading,
    error: latest.error,
    refetch: () => void latest.refetch(),
    loadOlder,
    loadingOlder,
    hasMore,
    progress,
    streaming,
    errors,
    applyInteraction: interactions.apply,
    refresh,
  };
}
