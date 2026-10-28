import { requesterName } from "../../lib/requester";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError } from "@agent-console/api-client";
import type { Interaction, NodeRun, RunEvent, TraceLink, TraceSpan } from "@agent-console/contracts";
import type { GroupBadge, LinkBadge, MethodBadge, SpanLabel, TraceGroupInfo } from "@agent-console/trace-view";
import type { NodeRunBadge } from "@agent-console/graph-editor";
import { Badge, Banner, ConfirmDialog, PageHeader, Tabs, useShortcuts, useToast } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { messages as appMessages } from "../../app/messages";
import { useConnectionStatus } from "../../app/useConnectionStatus";
import { useNow } from "../../app/useNow";
import { formatClockTime, formatDuration, formatRelative } from "../../lib/format";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { usePageTitle } from "../../shell/titles";
import { delegationMessages as dm, CONFIG_WIDGETS, conditionPayloadOf, deriveAllEdgeChips, deriveEdgeChips, edgeStrategyIds, mapConditionOutcome, shortRunId, summarizeDelegationEvent, useConditionOperators, useRenderIcon } from "../delegation";
import { useDelegationStrategies } from "../settings";
import { DEFINITION_KINDS, nodeAvatarsOf } from "../library";
import { useApiQuery } from "../../app/queries";
import { AgentsTab } from "./AgentsTab";
import { ChildRunsMenu, type ChildRunRow } from "./ChildRunsMenu";
import { EdgeJudgementView } from "./EdgeJudgementView";
import { NodeRunList } from "./NodeRunList";
import { RunBreadcrumb } from "./RunBreadcrumb";
import { edgeRecords, edgeStatus } from "./edgeRecords";
import { groupNodeRuns, nodeRunKey, runBadge, runOrdinalText, visibleRuns } from "./nodeRuns";
import { buildEdgeBadges, childForNodeRun, childNodeText, exhaustedLines, nestedRunSummaries } from "./runDelegation";
import { failedChildCount } from "./runTree";
import { useRunTree } from "./useRunTree";
import { loadRunGraph } from "./useRunView";
import { InteractionsTab } from "./InteractionsTab";
import { NodeTab } from "./NodeTab";
import { ObserveTab } from "./ObserveTab";
import { RunGraphPane } from "./RunGraphPane";
import { RunHeader } from "./RunHeader";
import { TraceTab } from "./TraceTab";
import { runHrefs } from "./RunsListScreen";
import { runStatusLabels, runsMessages as t } from "./messages";
import { EDGE_SKIPPED_EVENT, EDGE_TRAVERSED_EVENT } from "./runsConfig";
import { useObservePrefixes } from "./useObservePrefixes";
import { delegationEdgeFor, deriveRunOverlay, isActiveRun, latestNodeRuns, runDurationMs, summarizeEvent, waitSeconds, formatTokensShort, totalTokens } from "./runsLib";
import { useInteractionRespond } from "../interactions";
import { useRunLookups } from "./useRunLookups";
import { useRunView } from "./useRunView";
import "./runs.css";

// 세션 로그 탭은 로그 기능의 공개 API이며, 탭을 열 때만 내려받는다.
const SessionLogsTab = lazy(() => import("../logs").then((m) => ({ default: m.RunSessionLogsTab })));
const ArchitectureTab = lazy(() => import("../logs").then((m) => ({ default: m.RunArchitectureTab })));
// 요약 줄의 메모리 칩은 메모리-실행 연동이 있을 때만 내려받는다.
const MemoryChips = lazy(() => import("../memory").then((m) => ({ default: m.RunMemoryChips })));

/** 검사 패널 탭 순서(Alt+번호). 이 목록이 탭 id의 유일한 원천이다. */
export const INSPECTOR_TABS = ["trace", "agents", "observe", "interactions", "node", "logs", "architecture"] as const;
type InspectorTab = (typeof INSPECTOR_TABS)[number];
/** 추적 연동이 만드는 탭(`INSPECTOR_TABS`의 첫 항목). 이 탭만 연동 부분 규칙을 따른다. */
const TRACE_TAB: InspectorTab = INSPECTOR_TABS[0];
/** 로그 연동이 만드는 탭(마지막). 이 탭만 로그-실행 연동 부분 규칙을 따른다. */
const LOGS_TAB: InspectorTab = INSPECTOR_TABS[5];
/** 관측 탭(`INSPECTOR_TABS`의 세 번째). 서버가 접두어 목록을 비우면 탭이 없다(5.5R.13). */
const OBSERVE_TAB: InspectorTab = INSPECTOR_TABS[2];
/** 구조도 탭(마지막). 로그 구조도와 로그-실행 연동 역할이 모두 있을 때만 있다. */
const ARCH_TAB: InspectorTab = INSPECTOR_TABS[6];

/** 이벤트 탭의 type 접두 필터를 주소에 싣는 인자 이름 */
const TYPE_PREFIX_PARAM = "type_prefix";

const TERMINAL_NODE_STATUSES = ["succeeded", "failed", "skipped", "cancelled"];

function isTab(v: string | null, tabs: readonly InspectorTab[]): v is InspectorTab {
  return v !== null && (tabs as readonly string[]).includes(v);
}

/** 실행 상세 화면(컨테이너): 서버 상태(`useRunView`) + URL 상태를 읽어 헤더·그래프·검사 패널에 나눠 준다. */
export function RunDetailScreen() {
  const { id = "" } = useParams();
  const { rest, ws } = useApi();
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const lookups = useRunLookups();
  // 위임 흐름 탭은 추적 연동이 켜져 있을 때만 있다. 꺼졌으면 탭 줄에서 빠지고 기본 탭은 남은 첫 탭이다.
  const flowPart = useLinkPart(LINK_PART_IDS.runsFlowTab);
  const logsPart = useLinkPart(LINK_PART_IDS.logsRunsTab);
  const archPart = useLinkPart(LINK_PART_IDS.runsArchitectureTab);
  const memoryPart = useLinkPart(LINK_PART_IDS.runsMemoryChips);
  const view = useRunView(id, { trace: flowPart.visible });
  const observe = useObservePrefixes();
  const tabIds = useMemo(
    () => INSPECTOR_TABS.filter((tabId) => (tabId !== TRACE_TAB || flowPart.visible) && (tabId !== LOGS_TAB || logsPart.visible) && (tabId !== OBSERVE_TAB || observe.enabled) && (tabId !== ARCH_TAB || archPart.visible)),
    [flowPart.visible, logsPart.visible, observe.enabled, archPart.visible],
  );
  const defaultTab: InspectorTab = tabIds[0] ?? TRACE_TAB;
  const connection = useConnectionStatus(ws);

  const tabParam = params.get("tab");
  const tab: InspectorTab = isTab(tabParam, tabIds) ? tabParam : defaultTab;
  const nodeId = params.get("node");
  const spanId = params.get("span");
  const actorsParam = (params.get("actor") ?? "").split(",").filter((a) => a !== "");

  const edgeId = params.get("edge");
  // 채팅 진행 줄 칩이 `#node=`·`#edge=` 해시로 연다. 해시를 읽어 선택으로 바꾼다(한 번).
  const location = useLocation();
  const hashApplied = useRef("");
  useEffect(() => {
    if (location.hash === "" || hashApplied.current === location.hash) return;
    hashApplied.current = location.hash;
    const hp = new URLSearchParams(location.hash.slice(1));
    const node = hp.get("node");
    const edge = hp.get("edge");
    if (node === null && edge === null) return;
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (edge !== null) {
          next.set("edge", edge);
          next.delete("node");
          next.set("tab", "node");
        } else if (node !== null) {
          next.set("node", node);
          next.delete("edge");
        }
        return next;
      },
      { replace: true },
    );
  }, [location.hash, setParams]);
  /** 노드별로 사용자가 고른 실행(키). 고르지 않은 노드는 최신 실행을 따라간다(D10). */
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [showResources, setShowResources] = useState(false);
  const [focusRequest, setFocusRequest] = useState<{ nodeId: string; token: number } | undefined>();
  const [focusInteraction, setFocusInteraction] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const run = view.run;
  const active = run !== undefined && isActiveRun(run.status);
  // 자식 실행(중첩 팀): 후손 목록·활성 자식 구독. 루트 실행이면 후손의 대기 요청을 이 실행의 목록에 더한다(screen-delegation 3.7).
  const hasKids = (view.children?.length ?? 0) > 0;
  const kidPending = useApiQuery(["run", id, "descendant-pending"], (r) => r.listInteractions({ root: id, status: "pending" }), { enabled: run !== undefined && hasKids, refetchInterval: active ? 5000 : false });
  const tree = useRunTree(run, view.children, () => {
    if (flowPart.visible) view.reloadTrace();
    view.reloadSnapshot();
    void kidPending.refetch();
  });
  const interactions = useMemo<readonly Interaction[]>(() => {
    const own = new Set(view.interactions.map((i) => i.id));
    const kids = (kidPending.data ?? []).filter((i) => i.run_id !== id && !own.has(i.id));
    return [...kids, ...view.interactions];
  }, [view.interactions, kidPending.data, id]);
  const hasPending = interactions.some((i) => i.status === "pending");
  const nowMs = useNow(active || hasPending, 1000);
  const nowSec = nowMs / 1000;

  usePageTitle(run ? (tree.isChild ? `${dm.run.child.title} ${shortRunId(id)}` : `${id} · ${runStatusLabels[run.status] ?? run.status}`) : id);

  const setParam = (patch: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(patch)) {
          if (v === null || v === "") next.delete(k);
          else next.set(k, v);
        }
        return next;
      },
      { replace: true },
    );
  const setTab = (next: string) => setParam({ tab: next === defaultTab ? null : next });
  const focusNode = (node: string) => {
    setParam({ node, edge: null });
    setFocusRequest((cur) => ({ nodeId: node, token: (cur?.token ?? 0) + 1 }));
  };

  const graph = view.graph?.graph;
  const graphNodes = useMemo(() => graph?.nodes ?? [], [graph]);
  const pendingList = useMemo(() => interactions.filter((i) => i.status === "pending"), [interactions]);
  const groups = useMemo(() => groupNodeRuns(view.nodeRuns), [view.nodeRuns]);
  const visible = useMemo(() => visibleRuns(groups, picks), [groups, picks]);
  const baseOverlay = useMemo(
    () =>
      deriveRunOverlay({
        graph,
        edgeTypes: lookups.edgeTypes,
        nodeRuns: view.nodeRuns,
        events: view.events,
        pending: pendingList,
        visible,
        summarize: (n: NodeRun) => {
          const tokens = totalTokens(n.usage);
          const parts = [n.duration_ms != null ? formatDuration(n.duration_ms) : undefined, tokens !== undefined ? `${formatTokensShort(tokens)} 토큰` : undefined].filter(Boolean);
          return parts.length === 0 ? undefined : parts.join(" · ");
        },
      }),
    [graph, lookups.edgeTypes, view.nodeRuns, view.events, pendingList, visible],
  );
  // 반복 한도에 닿은 연결의 출발 노드 카드 아래에 한 줄을 더한다(상태 요약 칸 재사용)
  const overlay = useMemo(() => {
    const lines = exhaustedLines(graph, baseOverlay);
    if (Object.keys(lines).length === 0) return baseOverlay;
    const nodeStates = { ...baseOverlay.nodeStates };
    for (const [node, line] of Object.entries(lines)) {
      const cur = nodeStates[node];
      if (cur !== undefined) nodeStates[node] = { ...cur, summary: [cur.summary, line].filter(Boolean).join(" · ") };
    }
    return { ...baseOverlay, nodeStates };
  }, [graph, baseOverlay]);

  // ---- 이름 해석 (노드 label · 에이전트 이름). 목록에 없으면 id 원문.
  const actorByNode = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of view.events) {
      const n = e.node_path[e.node_path.length - 1];
      if (n !== undefined && e.actor && !map.has(n)) map.set(n, e.actor);
    }
    return map;
  }, [view.events]);
  const nodeLabel = useCallback(
    (node: string): string => {
      const spec = graphNodes.find((n) => n.id === node);
      if (spec?.label) return spec.label;
      const actor = actorByNode.get(node);
      return actor ? lookups.agentName(actor) : node;
    },
    [graphNodes, actorByNode, lookups],
  );
  const kindMap = useMemo(() => new Map(lookups.edgeTypes.map((e) => [e.id, e])), [lookups.edgeTypes]);
  const subagentNodes = useMemo(() => new Set(Object.keys(overlay.subagentCalls)), [overlay.subagentCalls]);
  const subagentActors = useMemo(() => {
    const out = new Set<string>();
    for (const e of view.events) {
      const n = e.node_path[e.node_path.length - 1];
      if (e.actor && n !== undefined && subagentNodes.has(n)) out.add(e.actor);
    }
    return out;
  }, [view.events, subagentNodes]);

  const labelFor = (span: TraceSpan): SpanLabel => {
    const title = span.node_id ? nodeLabel(span.node_id) : (span.actor ? lookups.agentName(span.actor) : span.id);
    const actorName = span.actor ? lookups.agentName(span.actor) : undefined;
    const interaction = span.interaction_id ? interactions.find((i) => i.id === span.interaction_id) : undefined;
    const sub = interaction ? (lookups.kindOf(interaction.kind)?.title ?? interaction.kind) : actorName !== undefined && actorName !== title ? actorName : undefined;
    return sub === undefined ? { title } : { title, sub };
  };
  const methodBadgeFor = (span: TraceSpan): MethodBadge | undefined => {
    if (span.interaction_id) return undefined;
    // 위임자 → 호출 span 링크(독립 위임)와 넘기기 링크가 연결 종류를 직접 알려 준다. 없으면 같은 세션 위임(서브에이전트)을 그래프 연결에서 찾는다.
    const link = view.trace?.links?.find((l) => l.target === span.id);
    const linkTitle = link?.kind ? lookups.edgeTitle(link.kind) : undefined;
    const linkIcon = link?.kind ? lookups.edgeIcon(link.kind) : undefined;
    if (linkTitle) return { text: linkTitle, ...(linkIcon ? { iconName: linkIcon } : {}) };
    if (span.parent_id && span.node_id) {
      const edge = delegationEdgeFor(graph?.edges ?? [], kindMap, span.node_id);
      const title = edge ? lookups.edgeTitle(edge.kind) : undefined;
      const icon = edge ? lookups.edgeIcon(edge.kind) : undefined;
      return title ? { text: title, ...(icon ? { iconName: icon } : {}) } : undefined;
    }
    return undefined;
  };
  // 자식 실행(Run) 안 요청의 부모 노드 경로: 이 실행의 자식은 이 그래프의 노드 label, 더 깊은 단계는 그 단계 그래프를 몰라 노드 id를 쓴다
  const childPathOf = (runId: string): string[] => {
    const names: string[] = [];
    const byId = new Map(tree.descendants.map((r) => [r.id, r]));
    for (let cur = byId.get(runId); cur !== undefined && cur.id !== id; cur = cur.parent_run_id == null ? undefined : byId.get(cur.parent_run_id)) {
      const node = cur.parent_node_id ?? "";
      names.unshift(cur.parent_run_id === id ? nodeLabel(node) : node);
    }
    return names;
  };
  const actorLabel = (i: Interaction): string => {
    const own = requesterName(i, i.actor ? lookups.agentName(i.actor) : undefined, nodeLabel(i.node_id));
    const nested = i.run_id === id ? [] : childPathOf(i.run_id);
    if (nested.length > 0) return dm.run.child.nestedActor(nested.length > 3 ? `${nested[0]} › … › ${nested[nested.length - 1]}` : nested.join(" › "), own);
    const path = i.node_path ?? [];
    return path.length > 1 ? t.interactions.nestedActor(nodeLabel(path[0]!), own) : own;
  };
  const teamNameOfRun = (runId: string): string | undefined => {
    const r = runId === id ? run : tree.descendants.find((x) => x.id === runId) ?? tree.chain.find((x) => x.id === runId);
    return r === undefined ? undefined : lookups.graphName(r.graph_id);
  };
  const runHref = (runId: string, extra = "") => `/runs/${encodeURIComponent(runId)}${extra}`;
  const openRun = (runId: string, extra = "") => void navigate(runHref(runId, extra));

  // ---- 응답 / 취소
  const reloadAllInteractions = () => {
    view.reloadInteractions();
    void kidPending.refetch();
  };
  const responder = useInteractionRespond({ refresh: reloadAllInteractions, messages: { closed: t.interactions.alreadyClosed, failed: t.interactions.respondFailed } });
  // 필드 오류로 막힌 응답은 카드가 오류 영역에 한 줄로도 알리도록 던진다
  const onRespond = async (i: Interaction, response: unknown) => {
    if (!(await responder.respond(i, response))) throw new Error(t.interactions.validation);
  };
  const confirmCancel = () => {
    setCancelOpen(false);
    setCancelling(true);
    rest
      .cancelRun(id)
      .then(() => view.reloadSnapshot())
      .catch((e: unknown) => {
        setCancelling(false);
        toast({ tone: "danger", text: describeError(e, t.detail.cancelFailed).message });
      });
  };
  const cancelBusy = cancelling && run !== undefined && isActiveRun(run.status);

  // ---- 노드 순서 이동
  const orderedNodes = useMemo(
    () =>
      [...latestNodeRuns(view.nodeRuns).values()]
        .sort((a, b) => (a.started_at ?? Infinity) - (b.started_at ?? Infinity))
        .map((n) => n.node_id),
    [view.nodeRuns],
  );
  const stepNode = (delta: number) => {
    if (orderedNodes.length === 0) return;
    const at = nodeId === null ? -1 : orderedNodes.indexOf(nodeId);
    const next = orderedNodes[(at + delta + orderedNodes.length) % orderedNodes.length];
    if (next !== undefined) focusNode(next);
  };
  // ---- 실행(회차·호출) 고르기: 사용자가 고른 실행은 새 실행이 생겨도 유지되고, 고르지 않았으면 최신을 따라간다
  const [liveNote, setLiveNote] = useState("");
  const pickRun = useCallback((node: string, key: string) => setPicks((cur) => ({ ...cur, [node]: key })), []);
  const followLatest = useCallback(
    (node: string) =>
      setPicks((cur) => {
        const { [node]: _gone, ...rest } = cur;
        void _gone;
        return rest;
      }),
    [],
  );
  const stepRun = (delta: -1 | 1) => {
    if (nodeId === null) return;
    const list = groups.get(nodeId);
    const v = visible.get(nodeId);
    if (list === undefined || list.length < 2 || v === undefined) return;
    const to = v.index + delta;
    if (to < 0) return setLiveNote(dm.run.list.first);
    if (to >= list.length) return setLiveNote(dm.run.list.latest);
    if (to === list.length - 1) followLatest(nodeId);
    else pickRun(nodeId, nodeRunKey(list[to]!));
    setLiveNote(dm.run.list.moved(runOrdinalText(list[to]!, list), to + 1, list.length));
  };
  const openNodeList = (node: string) => {
    focusNode(node);
    setParam({ tab: "node", node, edge: null });
    setTimeout(() => document.querySelector<HTMLElement>(".dlg-runlist tr[aria-selected='true']")?.focus(), 50);
  };
  const delegationStrategies = useDelegationStrategies();
  const operators = useConditionOperators();
  const renderIcon = useRenderIcon();
  const parentRun = tree.chain.length >= 2 ? tree.chain[tree.chain.length - 2] : undefined;
  const parentGraph = useApiQuery(["run", parentRun?.id ?? "", "graph", parentRun?.graph_id, parentRun?.graph_version], (r) => loadRunGraph(r, parentRun!.graph_id, parentRun!.graph_version), { enabled: parentRun !== undefined, staleTime: Infinity });
  const statusOf = (status: string) => appMessages.nodeStatus[status] ?? appMessages.runStatus[status] ?? status;
  const nodeRunBadges = useMemo(() => {
    const out: Record<string, NodeRunBadge> = {};
    for (const [node, list] of groups) {
      const v = visible.get(node);
      if (v === undefined) continue;
      const b = runBadge(list, v, nodeLabel(node), appMessages.nodeStatus[v.run.status] ?? v.run.status);
      if (b !== undefined) out[node] = { text: b.text, ariaLabel: b.ariaLabel, picked: b.picked, onClick: () => openNodeList(node) };
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- openNodeList는 setParam/focusNode(렌더마다 새 함수)를 부를 뿐이라 의존에서 뺀다
  }, [groups, visible, nodeLabel]);
  const edgeBadges = useMemo(() => buildEdgeBadges(graph, lookups.edgeTypes, overlay), [graph, lookups.edgeTypes, overlay]);
  const edgeChips = useMemo(
    () => (graph === undefined ? {} : deriveAllEdgeChips(graph, lookups.edgeTypes, { strategies: delegationStrategies.data ?? [], operators: operators.operators, teamSettings: graph.settings, widgets: CONFIG_WIDGETS })),
    [graph, lookups.edgeTypes, delegationStrategies.data, operators.operators],
  );
  const strategyIds = useMemo(() => (graph === undefined ? {} : edgeStrategyIds(graph, lookups.edgeTypes)), [graph, lookups.edgeTypes]);
  const nodeAvatars = useMemo(() => nodeAvatarsOf(graph?.nodes ?? [], lookups.nodeTypes, lookups.agents), [graph, lookups.nodeTypes, lookups.agents]);
  const nestedSummaries = useMemo(
    () =>
      nestedRunSummaries({
        nodes: graph?.nodes,
        nodeTypes: lookups.nodeTypes,
        currentKind: DEFINITION_KINDS.graph,
        children: tree.children,
        nodeRunsOf: (n) => groups.get(n) ?? [],
        visibleIndexOf: (n) => visible.get(n)?.index ?? 0,
        teamName: (gid) => lookups.graphName(gid) ?? gid,
        statusLabel: (st) => runStatusLabels[st] ?? st,
        shortId: shortRunId,
        onOpen: (rid) => void navigate(`/runs/${encodeURIComponent(rid)}`),
      }),
    [graph, lookups, tree.children, groups, visible, navigate],
  );
  const extraNodeBadges = useMemo(() => Object.fromEntries(Object.keys(overlay.handledNodes).map((n) => [n, [dm.run.handled]])), [overlay.handledNodes]);

  useShortcuts([
    ...(tree.isChild && parentRun !== undefined ? [{ id: "runs.up", scope: "run-detail", keys: "u", titleKey: "shortcuts.runsParent", run: () => openRun(parentRun.id) }] : []),
    {
      id: "runs.child.open",
      scope: "run-detail",
      keys: "d",
      titleKey: "shortcuts.runsOpenChild",
      run: () => {
        if (nodeId === null) return;
        const found = childForNodeRun(nodeId, groups.get(nodeId) ?? [], visible.get(nodeId)?.index ?? 0, tree.children);
        if (found.child !== undefined) openRun(found.child.id);
        else if (found.all.length > 0) setTab("node");
      },
    },
    { id: "runs.run.prev", scope: "run-detail", keys: ",", titleKey: "shortcuts.runsRunPrev", run: () => stepRun(-1) },
    { id: "runs.run.next", scope: "run-detail", keys: ".", titleKey: "shortcuts.runsRunNext", run: () => stepRun(1) },
    ...tabIds.map((tabId, index) => ({
      id: `runs.tab.${tabId}`,
      scope: "run-detail",
      keys: `Alt+${index + 1}`,
      titleKey: `shortcuts.runsTab${index + 1}`,
      modifierRequired: true,
      run: () => setTab(tabId),
    })),
    { id: "runs.node.next", scope: "run-detail", keys: "]", titleKey: "shortcuts.runsNodeNext", run: () => stepNode(1) },
    { id: "runs.node.prev", scope: "run-detail", keys: "[", titleKey: "shortcuts.runsNodePrev", run: () => stepNode(-1) },
    { id: "runs.cancel", scope: "run-detail", keys: "Ctrl+Shift+X", titleKey: "shortcuts.runsCancel", modifierRequired: true, run: () => run && isActiveRun(run.status) && setCancelOpen(true) },
  ]);

  // ---- 로딩/오류/404
  if (view.snapshotStatus === "error" && run === undefined) {
    const err = view.snapshotError;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <div className="app-screen-frame" data-screen="run-detail">
          <PageHeader title={t.detail.notFoundTitle} />
          <div className="app-screen-body">
            <ErrorBlock title={t.detail.notFoundTitle}>
              <Link to="/runs" className="ac-btn" data-variant="primary">{t.detail.toList}</Link>
            </ErrorBlock>
          </div>
        </div>
      );
    }
    const e = describeError(err, t.detail.loadFailed);
    return (
      <div className="app-screen-frame" data-screen="run-detail">
        <PageHeader title={t.detail.loadFailed} />
        <div className="app-screen-body">
          <ErrorBlock title={t.detail.loadFailed} message={e.message} details={errorDetails(e)} detailsLabel={appMessages.common.details} retryLabel={appMessages.common.retry} onRetry={view.reloadSnapshot} />
        </div>
      </div>
    );
  }
  if (run === undefined) {
    return (
      <div className="app-screen-frame" data-screen="run-detail" aria-busy="true">
        <PageHeader title={id} />
        <div className="app-screen-body">
          <div className="app-skeleton" role="status" aria-label={t.detail.loading}>
            {Array.from({ length: 6 }, (_, i) => <div key={i} className="app-skeleton-row" />)}
          </div>
        </div>
      </div>
    );
  }

  const latest = latestNodeRuns(view.nodeRuns);
  const executableTotal = graphNodes.filter((n) => lookups.nodeTypes.find((d) => d.id === n.type)?.executable !== false).length;
  // 서브에이전트처럼 NodeRun이 없는 노드도 이벤트에서 계산한 상태(overlay)로 센다.
  const doneCount = Object.values(overlay.nodeStates).filter((n) => TERMINAL_NODE_STATUSES.includes(n.status)).length;
  const runningNode = [...latest.values()].find((n) => n.status === "running");
  const failedNode = [...latest.values()].find((n) => n.status === "failed");
  const userWait = interactions.reduce((s, i) => s + waitSeconds(i, nowSec), 0);
  const conv = run.conversation_id;
  const idleSeconds = view.lastEventTs === undefined ? undefined : Math.max(0, nowSec - view.lastEventTs);
  const nodeActors = nodeId === null ? [] : [...new Set(view.events.filter((e) => e.actor && e.node_path.includes(nodeId)).map((e) => e.actor as string))];
  const agentActors = actorsParam.length > 0 ? actorsParam : nodeActors;
  const nodeEvents = nodeId === null ? [] : view.events.filter((e) => e.node_path.includes(nodeId));
  const firstTs = view.events[0]?.ts ?? run.started_at ?? undefined;

  const selectNodeFromGraph = (node: string | null) => {
    if (node === nodeId) return;
    const waitingHere = node !== null && overlay.waitingNodes[node] !== undefined;
    if (waitingHere) setFocusInteraction(pendingList.find((i) => i.node_id === node)?.id ?? null);
    // 노드를 고르면 연결 선택은 풀린다. 선택을 비우는 호출(null)은 연결 선택을 건드리지 않는다(연결을 막 골랐을 수 있다)
    setParam({ node, ...(node === null ? {} : { edge: null }), ...(waitingHere ? { tab: "interactions" } : {}), span: null });
  };
  const selectEdgeFromGraph = (edge: string | null) => {
    if (edge === edgeId) return;
    setParam(edge === null ? { edge: null } : { edge, node: null, span: null, tab: "node" });
  };

  const tabItem = (tabId: InspectorTab, label: string, badge?: number) => ({
    id: tabId,
    label: (
      <>
        {label}
        {badge ? <Badge tone="warning" aria-label={t.detail.waitingBanner(badge)}>{badge}</Badge> : null}
      </>
    ),
  });

  // ---- 자식 실행 메뉴·상위 링크·실행 목록·연결 상세
  const clock = (ts: number | null | undefined) => (ts == null ? "–" : formatClockTime(ts));
  const childRows: ChildRunRow[] = tree.children.map((c) => ({
    run: c,
    teamName: lookups.graphName(c.graph_id) ?? c.graph_id,
    nodeText: childNodeText(tree.children, c, nodeLabel),
    statusLabel: runStatusLabels[c.status] ?? c.status,
    startedText: formatRelative(c.started_at ?? c.created_at, nowMs),
    durationText: formatDuration(runDurationMs(c, nowSec)),
  }));
  const childMenuNode = <ChildRunsMenu rows={childRows} onOpen={(rid) => openRun(rid)} />;
  const actorNote = (actor: string): string | undefined => {
    // 위임으로 불린 NodeRun(invoked_by)의 대상 actor에 "(← 위임자 위임)"을 덧붙인다
    for (const n of view.nodeRuns) {
      const caller = n.invoked_by?.[n.invoked_by.length - 1];
      if (caller !== undefined && actorByNode.get(n.node_id) === actor) return `(← ${nodeLabel(caller)} 위임)`;
    }
    return undefined;
  };
  const selectedRuns = nodeId === null ? [] : (groups.get(nodeId) ?? []);
  const selectedVisible = nodeId === null ? undefined : visible.get(nodeId);
  const invokedBy = selectedVisible?.run.invoked_by;
  const invokedNote = invokedBy != null && invokedBy.length > 0 ? dm.run.list.invokedNote(nodeLabel(invokedBy[invokedBy.length - 1]!)) : undefined;
  const runListNode =
    nodeId !== null && selectedVisible !== undefined && selectedRuns.length >= 2 ? (
      <NodeRunList
        runs={selectedRuns}
        selectedKey={nodeRunKey(selectedVisible.run)}
        onSelect={(key) => (key === nodeRunKey(selectedRuns[selectedRuns.length - 1]!) && picks[nodeId] === undefined ? undefined : pickRun(nodeId, key))}
        onLatest={() => followLatest(nodeId)}
        statusLabel={statusOf}
        startedText={(r) => clock(r.started_at)}
        callerLabel={(r) => (r.invoked_by != null && r.invoked_by.length > 0 ? nodeLabel(r.invoked_by[r.invoked_by.length - 1]!) : undefined)}
        onSelectCaller={(r) => {
          const caller = r.invoked_by?.[r.invoked_by.length - 1];
          if (caller !== undefined) focusNode(caller);
        }}
        childrenOf={(r) => {
          const i = selectedRuns.indexOf(r);
          const found = childForNodeRun(nodeId, selectedRuns, i, tree.children);
          return (found.child === undefined ? found.all : [found.child]).map((c) => ({ runId: c.id, short: shortRunId(c.id) }));
        }}
        onOpenChild={(rid) => openRun(rid)}
        onAnswer={() => setTab("interactions")}
      />
    ) : undefined;
  const edgeSpec = edgeId === null ? undefined : graph?.edges?.find((e) => e.id === edgeId);
  const edgeViewNode = (() => {
    if (edgeSpec === undefined) return undefined;
    const kind = kindMap.get(edgeSpec.kind);
    const records = edgeRecords(view.events, edgeSpec.id);
    const st = edgeStatus(records);
    const chips = deriveEdgeChips(edgeSpec, kind, { strategies: delegationStrategies.data ?? [], operators: operators.operators, teamSettings: graph?.settings, widgets: CONFIG_WIDGETS }).map((c) => c.fullTitle ?? c.title);
    return (
      <EdgeJudgementView
        fromLabel={nodeLabel(edgeSpec.source.node)}
        toLabel={nodeLabel(edgeSpec.target.node)}
        kindTitle={kind?.title ?? edgeSpec.kind}
        chips={chips}
        status={st.status}
        statusTime={st.at === undefined ? undefined : clock(st.at)}
        passes={st.passes}
        condition={st.condition}
        rawCondition={st.rawCondition}
        operators={operators.operators}
        records={records}
        isCycle={kind?.cycle != null}
        timeText={(ts) => clock(ts)}
        nodeLabel={nodeLabel}
        onSeeIteration={(node, iteration) => {
          const list = groups.get(node);
          const target = list?.find((r) => (r.iteration ?? 0) === iteration);
          if (target !== undefined) pickRun(node, nodeRunKey(target));
          openNodeList(node);
        }}
      />
    );
  })();

  const groupBadgeFor = (group: TraceGroupInfo): GroupBadge | undefined => {
    const team = teamNameOfRun(group.runId);
    return { title: team === undefined ? `${dm.run.child.title} ${shortRunId(group.runId)}` : `${dm.run.child.title} ${shortRunId(group.runId)} · ${team}` };
  };
  const linkBadgeFor = (link: TraceLink): LinkBadge | undefined => {
    const kind = link.kind ? kindMap.get(link.kind) : undefined;
    return kind?.cycle == null ? undefined : { text: "↻" };
  };
  const edgeLabelOf = (eid: string): string => {
    const e = graph?.edges?.find((x) => x.id === eid);
    return e === undefined ? eid : `${nodeLabel(e.source.node)} → ${nodeLabel(e.target.node)}`;
  };
  const summaryOf = (ev: RunEvent): string | undefined => {
    const sum = summarizeDelegationEvent(ev, { nodeLabel, edgeLabel: edgeLabelOf, teamName: teamNameOfRun, statusLabel: statusOf, shortId: shortRunId });
    if (sum !== null) return sum.text;
    const cond = conditionPayloadOf(ev);
    if ((ev.type === EDGE_TRAVERSED_EVENT || ev.type === EDGE_SKIPPED_EVENT) && cond !== undefined) {
      const mapped = mapConditionOutcome(cond);
      if (mapped !== null) return `${summarizeEvent(ev)} · ${mapped.result ? dm.run.event.conditionPass : dm.run.event.conditionFalse}`;
    }
    return undefined;
  };

  const content: Record<InspectorTab, React.ReactNode> = {
    logs: null,
    architecture: null,
    trace: (
      <TraceTab
        trace={view.trace}
        status={view.traceStatus}
        onRetry={view.reloadTrace}
        running={active}
        nowSec={nowSec}
        labelFor={labelFor}
        methodBadgeFor={methodBadgeFor}
        groupBadgeFor={groupBadgeFor}
        linkBadgeFor={linkBadgeFor}
        onOpenChildRun={(rid) => openRun(rid)}
        selectedSpanId={spanId}
        onSelect={(sid) => {
          const span = view.trace?.spans?.find((s) => s.id === sid);
          setParam({ span: sid });
          if (span?.node_id) setFocusRequest((cur) => ({ nodeId: span.node_id as string, token: (cur?.token ?? 0) + 1 }));
        }}
        highlightNodeId={nodeId}
        onSeeLog={(actor) => setParam({ tab: "agents", actor })}
        onSeeNode={(n, runId) => {
          // 자식 실행 안 span의 [노드 보기]는 현재 Run의 그래프가 아니라 그 자식 실행 화면으로 간다
          if (runId !== undefined && runId !== id) return openRun(runId, `?tab=node&node=${encodeURIComponent(n)}`);
          focusNode(n);
          setParam({ tab: "node", node: n });
        }}
        onSeeInteraction={(iid) => {
          setFocusInteraction(iid);
          setTab("interactions");
        }}
        statusLabel={(s) => appMessages.nodeStatus[s] ?? appMessages.runStatus[s] ?? s}
      />
    ),
    agents: (
      <AgentsTab
        events={view.events}
        status={view.eventsStatus}
        onRetry={view.reloadEvents}
        actors={agentActors}
        onActorsChange={(next) => setParam({ actor: next.join(",") })}
        typePrefix={params.get(TYPE_PREFIX_PARAM) ?? ""}
        onTypePrefixChange={(next) => setParam({ [TYPE_PREFIX_PARAM]: next === "" ? null : next })}
        agentName={lookups.agentName}
        isSubagent={(a) => subagentActors.has(a)}
        startedAt={firstTs}
        running={active}
        summaryOf={summaryOf}
        actorNote={actorNote}
        topNote={
          tree.active.length > 0 ? (
            <p className="app-muted runs-note" role="status">
              {dm.run.child.eventsNote(tree.active.length)} {childMenuNode}
            </p>
          ) : null
        }
      />
    ),
    observe: (
      <ObserveTab
        events={view.events}
        status={view.eventsStatus}
        onRetry={view.reloadEvents}
        prefixes={observe.prefixes}
        agentName={lookups.agentName}
        startedAt={firstTs}
        settingsHref="/settings"
        {...(flowPart.visible
          ? {
              onSeeTrace: (toolUseId: string) => {
                const span = view.trace?.spans?.find((s) => s.tool_use_id === toolUseId);
                setParam({ tab: TRACE_TAB, ...(span ? { span: span.id } : {}) });
              },
            }
          : {})}
      />
    ),
    interactions: (
      <InteractionsTab
        interactions={interactions}
        status={view.interactionsStatus}
        onRetry={reloadAllInteractions}
        kindOf={lookups.kindOf}
        actorLabel={actorLabel}
        agentName={lookups.agentName}
        nowSec={nowSec}
        onRespond={onRespond}
        errorsOf={responder.errorsOf}
        disabled={connection !== "open"}
        {...(conv ? { conversationHref: runHrefs.conversation(conv) } : {})}
        nodeFilter={nodeId}
        focusId={focusInteraction}
        contextChipOf={(i) => (i.run_id === id ? undefined : { text: dm.run.child.fromChild(shortRunId(i.run_id), teamNameOfRun(i.run_id) ?? ""), title: dm.run.child.fromChild(i.run_id, teamNameOfRun(i.run_id) ?? ""), href: runHref(i.run_id) })}
        footer={hasKids ? <p className="app-muted runs-note">{dm.run.child.pastNote}</p> : undefined}
      />
    ),
    node: (
      <NodeTab
        run={run}
        nodeId={nodeId}
        nodeLabel={nodeLabel}
        nodeRun={nodeId === null ? undefined : (visible.get(nodeId)?.run ?? latest.get(nodeId))}
        ordinalText={nodeId === null || visible.get(nodeId) === undefined ? undefined : runOrdinalText(visible.get(nodeId)!.run, groups.get(nodeId) ?? [])}
        invokedNote={invokedNote}
        runList={runListNode}
        edgeView={edgeViewNode}
        isSubagentNode={nodeId !== null && subagentNodes.has(nodeId)}
        waiting={nodeId !== null && overlay.waitingNodes[nodeId] !== undefined}
        events={nodeEvents}
        onSeeInteractions={() => setTab("interactions")}
      />
    ),
  };

  content.logs = (
    <Suspense fallback={<div className="app-loading" role="status">{appMessages.common.loadingScreen}</div>}>
      <SessionLogsTab runId={id} running={active} selectedNodeId={nodeId} onSelectNode={(n) => selectNodeFromGraph(n)} />
    </Suspense>
  );

  content.architecture = (
    <Suspense fallback={<div className="app-loading" role="status">{appMessages.common.loadingScreen}</div>}>
      <ArchitectureTab runId={id} running={active} hasChildren={tree.children.length > 0} refreshKey={view.events.length} />
    </Suspense>
  );

  return (
    <div className="app-screen-frame runs-detail" data-screen="run-detail">
      <RunHeader
        run={run}
        nowSec={nowSec}
        graphName={lookups.graphName(run.graph_id)}
        graphHref={runHrefs.graph(run.graph_id)}
        listHref="/runs"
        {...(conv ? { conversation: { title: lookups.conversationTitle(conv) ?? conv, href: runHrefs.conversation(conv) } } : {})}
        nodeProgress={{ done: doneCount, total: executableTotal }}
        userWaitSeconds={userWait}
        waitingCount={pendingList.length}
        waitingSuffix={hasKids && pendingList.some((i) => i.run_id !== id) ? dm.run.child.includesChildren : undefined}
        hasSubagents={subagentNodes.size > 0}
        {...(runningNode ? { runningNode: { id: runningNode.node_id, label: nodeLabel(runningNode.node_id) } } : {})}
        {...(failedNode ? { failedNode: { id: failedNode.node_id, label: nodeLabel(failedNode.node_id) } } : {})}
        onFocusNode={focusNode}
        onSeeInteractions={() => setTab("interactions")}
        onCancel={() => setCancelOpen(true)}
        cancelling={cancelBusy}
        disconnected={connection === "reconnecting" || connection === "closed"}
        idleSeconds={idleSeconds}
        {...(memoryPart.visible
          ? {
              extra: (
                <Suspense fallback={null}>
                  <MemoryChips runId={id} active={active} onOpenReads={(typePrefix) => setParam({ tab: "agents", [TYPE_PREFIX_PARAM]: typePrefix })} />
                </Suspense>
              ),
            }
          : {})}
        {...(tree.isChild && tree.chain.length > 1
          ? {
              breadcrumb: (
                <RunBreadcrumb
                  items={tree.chain.map((r) => ({ id: r.id, short: shortRunId(r.id), teamName: lookups.graphName(r.graph_id) }))}
                  hrefOf={(rid) => runHref(rid)}
                />
              ),
            }
          : {})}
        {...(tree.isChild && parentRun !== undefined
          ? {
              parent: {
                text: dm.run.child.parentLink(shortRunId(parentRun.id), run.parent_node_id == null ? "" : (parentGraph.data?.graph.nodes?.find((n) => n.id === run.parent_node_id)?.label ?? run.parent_node_id)),
                href: runHref(parentRun.id),
                openLabel: dm.run.child.parentOpen,
                cancelLabel: dm.run.child.cancelFromParent,
              },
            }
          : {})}
        {...(childRows.length > 0 ? { childMenu: childMenuNode } : {})}
        notes={[
          ...(failedChildCount(tree.children) > 0 ? [{ key: "child-failed", text: dm.run.child.failedSome(tree.children.length, failedChildCount(tree.children)), tone: "danger" as const }] : []),
          ...(run.status === "completed" && Object.keys(overlay.handledNodes).length > 0 ? [{ key: "handled", text: dm.run.handledLine(Object.keys(overlay.handledNodes).length), tone: "info" as const }] : []),
        ]}
        {...(hasKids ? { interruptedNote: dm.run.child.interruptedNote } : {})}
      />
      <div className="runs-detail-body">
        <div className="runs-detail-graph">
          {graph === undefined ? (
            view.graphStatus === "error" ? (
              <Banner tone="danger">{t.detail.graphFailed}</Banner>
            ) : (
              <div className="app-loading" role="status">{t.detail.graphLoading}</div>
            )
          ) : (
            <RunGraphPane
              graph={graph}
              nodeTypes={lookups.nodeTypes}
              edgeTypes={lookups.edgeTypes}
              overlay={overlay}
              versionMissing={view.graph?.exact === false}
              showResources={showResources}
              onShowResourcesChange={setShowResources}
              onSelectNode={selectNodeFromGraph}
              onSelectEdge={selectEdgeFromGraph}
              nodeRunBadges={nodeRunBadges}
              edgeBadges={edgeBadges}
              edgeExtraChips={edgeChips}
              bindSummaries={nestedSummaries}
              nodeAvatars={nodeAvatars}
              delegationStrategies={delegationStrategies.data ?? []}
              edgeStrategyIds={strategyIds}
              renderIcon={renderIcon}
              extraNodeBadges={extraNodeBadges}
              {...(focusRequest ? { focusRequest } : {})}
              nowMs={nowMs}
              resolvePorts={(typeId, config) => rest.resolvePorts(typeId, (config ?? {}) as Record<string, unknown>)}
            />
          )}
        </div>
        <div className="runs-inspector" role="region" aria-label={t.detail.panelLabel} onKeyDown={(e) => e.key === "Escape" && (spanId !== null ? setParam({ span: null }) : nodeId !== null && setParam({ node: null }))}>
          <Tabs
            ariaLabel={t.tabs.label}
            activeId={tab}
            onChange={setTab}
            lazy
            tabs={[
              ...(flowPart.visible ? [{ ...tabItem(TRACE_TAB, t.tabs.trace), content: content.trace }] : []),
              { ...tabItem("agents", t.tabs.agents), content: content.agents },
              ...(observe.enabled ? [{ ...tabItem(OBSERVE_TAB, t.tabs.observe), content: content.observe }] : []),
              { ...tabItem("interactions", t.tabs.interactions, pendingList.length), content: content.interactions },
              { ...tabItem("node", t.tabs.node), content: content.node },
              ...(logsPart.visible ? [{ ...tabItem(LOGS_TAB, t.tabs.logs), content: content.logs }] : []),
              ...(archPart.visible ? [{ ...tabItem(ARCH_TAB, t.tabs.architecture), content: content.architecture }] : []),
            ]}
          />
        </div>
      </div>
      <ConfirmDialog open={cancelOpen} title={t.detail.cancelTitle} confirmLabel={t.detail.cancelConfirm} cancelLabel={t.detail.cancelKeep} danger onConfirm={confirmCancel} onCancel={() => setCancelOpen(false)}>
        {t.detail.cancelBody(pendingList.length)}
        {tree.active.length > 0 ? <p>{dm.run.child.cancelNote(tree.active.length)}</p> : null}
      </ConfirmDialog>
      <span className="ac-sr-only" role="status" aria-live="polite">{liveNote}</span>
    </div>
  );
}
