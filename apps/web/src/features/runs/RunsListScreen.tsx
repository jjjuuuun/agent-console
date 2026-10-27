import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import type { Run } from "@agent-console/contracts";
import { Button, ConfirmDialog, EmptyState, PageHeader, Tabs, useShortcuts, useToast } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { messages as appMessages } from "../../app/messages";
import { queryKeys, useApiQuery } from "../../app/queries";
import { useNow } from "../../app/useNow";
import { usePendingInteractions } from "../../shell/pending";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { HandoffMatrixView } from "./HandoffMatrixView";
import { useScopedList } from "../projects";
import { ROUTE_ROLES, routeIconNode, routePath } from "../library";
import { RunsFilterBar, type RunsFilters } from "./RunsFilterBar";
import { RunsTable } from "./RunsTable";
import { useRunLookups } from "./useRunLookups";
import { runStatusLabels, runsMessages as t } from "./messages";
import { DEFAULT_PERIOD, PERIOD_OPTIONS, RUN_LIST_LIMIT, RUN_LIST_POLL_MS, WAITING_RUN_STATUS } from "./runsConfig";
import { activeCounts, filterRuns, inputSummary, isActiveRun } from "./runsLib";
import "./runs.css";

const scopeOfRun = (r: Run) => r.project_id;
const idOfRun = (r: Run) => r.id;

/** 화면이 알아야 하는 경로 규칙(라우트 설정과 맞춘다). 컨테이너만 쓴다. */
export const runHrefs = {
  run: (id: string) => `/runs/${encodeURIComponent(id)}`,
  graph: (id: string) => `/teams/${encodeURIComponent(id)}`,
  conversation: (id: string) => `/chat/${encodeURIComponent(id)}`,
};

const loadHandoffs = (params: Record<string, string>) => (rest: RestClient) => rest.getHandoffs(params);

function readFilters(params: URLSearchParams): RunsFilters {
  const statuses = (params.get("status") ?? "").split(",").filter((s) => s !== "");
  const period = params.get("period") ?? DEFAULT_PERIOD;
  return {
    graph: params.get("graph") ?? "",
    agent: params.get("agent_id") ?? "",
    conversation: params.get("conv") ?? "",
    statuses,
    period: PERIOD_OPTIONS.some((p) => p.id === period) ? period : DEFAULT_PERIOD,
    query: params.get("q") ?? "",
    children: params.get("children") === "1",
    root: params.get("root") ?? "",
  };
}

function writeFilters(prev: URLSearchParams, f: RunsFilters): URLSearchParams {
  const next = new URLSearchParams(prev);
  const set = (key: string, v: string, def = "") => (v === def ? next.delete(key) : next.set(key, v));
  set("graph", f.graph);
  set("agent_id", f.agent);
  set("conv", f.conversation);
  set("status", f.statuses.join(","));
  set("period", f.period, DEFAULT_PERIOD);
  set("q", f.query);
  set("children", f.children ? "1" : "");
  set("root", f.root);
  return next;
}

/** 실행 기록 화면(컨테이너): URL 쿼리 필터 + 목록 질의 + 위임 집계. */
export function RunsListScreen() {
  const { rest } = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  // 위임 집계 보기는 추적 연동이 켜져 있을 때만 있다(꺼졌으면 보기 전환 자체가 없다)
  const handoffPart = useLinkPart(LINK_PART_IDS.runsHandoffView);
  const view = handoffPart.visible && params.get("view") === "handoffs" ? "handoffs" : "list";
  const [cancelTarget, setCancelTarget] = useState<Run | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const firstRef = useRef<HTMLSelectElement>(null);

  const serverParams = useMemo(
    () => ({
      limit: RUN_LIST_LIMIT,
      ...(filters.graph ? { graph_id: filters.graph } : {}),
      ...(filters.agent ? { agent_id: filters.agent } : {}),
      ...(filters.conversation ? { conversation_id: filters.conversation } : {}),
      ...(filters.root ? { root: filters.root } : {}),
    }),
    [filters.graph, filters.agent, filters.conversation, filters.root],
  );
  const runsQ = useApiQuery(queryKeys.list("runs", serverParams), (r) => r.listRuns(serverParams), {
    refetchInterval: (q) => (q.state.data?.some((r) => isActiveRun(r.status)) ? RUN_LIST_POLL_MS : false),
  });
  const lookups = useRunLookups();
  const handoffParams = useMemo(() => {
    const p: Record<string, string> = {};
    if (filters.graph) p["graph_id"] = filters.graph;
    if (filters.agent) p["agent_id"] = filters.agent;
    if (filters.conversation) p["conversation_id"] = filters.conversation;
    return p;
  }, [filters.graph, filters.agent, filters.conversation]);
  const handoffsQ = useApiQuery(queryKeys.list("run-handoffs", handoffParams), loadHandoffs(handoffParams), { enabled: view === "handoffs" });

  const pending = usePendingInteractions();
  useEffect(() => {
    void qc.invalidateQueries({ queryKey: ["list", "runs"] });
  }, [pending.count, qc]);

  const scopedRuns = useScopedList(runsQ.data, { scopeOf: scopeOfRun, idOf: idOfRun, nameOf: idOfRun });
  const runs = scopedRuns.items;
  const anyActive = runs?.some((r) => isActiveRun(r.status)) ?? false;
  const nowMs = useNow(anyActive, 1000);
  const graphName = lookups.graphName;
  const conversationTitle = lookups.conversationTitle;
  const agentName = (id: string) => lookups.agentName(id);

  const statusKey = filters.statuses.join(",");
  const minuteBucket = Math.floor(nowMs / 60000);
  const visible = useMemo(
    () =>
      filterRuns(
        runs ?? [],
        { statuses: filters.statuses, period: filters.period, query: filters.query },
        nowMs / 1000,
        PERIOD_OPTIONS,
        (run) => [graphName(run.graph_id), conversationTitle(run.conversation_id), inputSummary(run.input)].filter(Boolean).join("\n"),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runs, statusKey, filters.period, filters.query, lookups.graphs, lookups.conversations, minuteBucket],
  );
  // 자식 실행(중첩 팀)은 기본으로 가린다. 서버 필터를 새로 만들지 않고 응답에서 거른다(D11)
  const isChildRun = (r: Run) => r.root_run_id != null && r.root_run_id !== r.id;
  const shown = useMemo(() => (filters.children ? visible : visible.filter((r) => !isChildRun(r))), [visible, filters.children]);
  const onlyChildren = !filters.children && visible.length > 0 && shown.length === 0;
  const parentIds = useMemo(() => new Set((runs ?? []).map((r) => r.parent_run_id).filter((x): x is string => x != null)), [runs]);
  const counts = activeCounts(runs ?? [], WAITING_RUN_STATUS);

  const statusOptions = useMemo(() => {
    const fromMessages = Object.keys(runStatusLabels);
    const extra = [...new Set((runs ?? []).map((r) => r.status))].filter((s) => !fromMessages.includes(s));
    return [...fromMessages, ...extra];
  }, [runs]);

  const setFilters = (next: RunsFilters) => setParams((prev) => writeFilters(prev, next), { replace: true });
  const clearFilters = () => setFilters({ graph: "", agent: "", conversation: "", statuses: [], period: DEFAULT_PERIOD, query: "", children: false, root: "" });
  const setView = (v: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (v === "list") next.delete("view");
      else next.set("view", v);
      return next;
    });

  useShortcuts([
    { id: "runs.search", scope: "runs", keys: "/", titleKey: "shortcuts.runsSearch", run: () => searchRef.current?.focus() },
    { id: "runs.filters", scope: "runs", keys: "f", titleKey: "shortcuts.runsFilters", run: () => firstRef.current?.focus() },
  ]);

  const confirmCancel = () => {
    const target = cancelTarget;
    setCancelTarget(null);
    if (target === null) return;
    rest
      .cancelRun(target.id)
      .then(() => {
        toast({ tone: "success", text: t.list.cancelled });
        void qc.invalidateQueries({ queryKey: ["list", "runs"] });
      })
      .catch((e: unknown) => toast({ tone: "danger", text: describeError(e, t.list.cancelFailed).message }));
  };

  const hasFilter = filters.graph !== "" || filters.agent !== "" || filters.conversation !== "" || filters.statuses.length > 0 || filters.query !== "" || filters.period !== DEFAULT_PERIOD || filters.children || filters.root !== "";

  let body;
  if (runsQ.isPending) {
    body = (
      <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.list.loading}>
        {Array.from({ length: 8 }, (_, i) => <div key={i} className="app-skeleton-row" />)}
      </div>
    );
  } else if (runsQ.isError && runs === undefined) {
    const e = describeError(runsQ.error, t.list.loadFailed);
    body = <ErrorBlock title={t.list.loadFailed} message={e.message} details={errorDetails(e)} detailsLabel={appMessages.common.details} retryLabel={appMessages.common.retry} onRetry={() => void runsQ.refetch()} />;
  } else if ((runs ?? []).length === 0 && !hasFilter) {
    body = <EmptyState icon={routeIconNode(ROUTE_ROLES.runs)} title={t.list.empty} description={t.list.emptyBody} action={<Button variant="primary" onClick={() => void navigate(routePath(ROUTE_ROLES.conversations))}>{t.list.toChat}</Button>} />;
  } else if (onlyChildren) {
    body = <EmptyState title={t.list.childrenOnly} action={<Button onClick={() => setFilters({ ...filters, children: true })}>{t.list.includeChildren}</Button>} />;
  } else if (shown.length === 0) {
    body = <EmptyState title={t.list.noMatch} action={<Button onClick={clearFilters}>{t.list.clearFilters}</Button>} />;
  } else {
    body = (
      <>
        <RunsTable
          runs={shown}
          nowMs={nowMs}
          graphName={graphName}
          conversationTitle={conversationTitle}
          onOpen={(r) => void navigate(runHrefs.run(r.id))}
          onCancel={setCancelTarget}
          hrefs={runHrefs}
          nested={{ isChild: isChildRun, hasChildren: (r) => parentIds.has(r.id), onShowChildren: (r) => setFilters({ ...filters, root: r.id, children: true }) }}
        />
        {(runs ?? []).length >= RUN_LIST_LIMIT ? <p className="app-muted">{t.list.capped(RUN_LIST_LIMIT)}</p> : null}
      </>
    );
  }

  const handoffBody = (() => {
    if (handoffsQ.isPending) return <div role="status" className="app-loading">{t.handoffs.loading}</div>;
    if (handoffsQ.isError) {
      const e = describeError(handoffsQ.error, t.handoffs.loadFailed);
      return <ErrorBlock title={t.handoffs.loadFailed} message={e.message} retryLabel={appMessages.common.retry} onRetry={() => void handoffsQ.refetch()} />;
    }
    return (
      <>
        <p className="app-muted">{t.handoffs.periodNote}</p>
        <HandoffMatrixView
          matrix={handoffsQ.data}
          nameOf={agentName}
          methodOf={(k) => lookups.edgeTitle(k) ?? k}
          onSelectCell={(cell) => setFilters({ ...filters, agent: cell.from })}
        />
      </>
    );
  })();

  return (
    <div className="app-screen-frame" data-screen="runs">
      <PageHeader
        title={t.list.title}
        status={<span className="app-muted" aria-live="polite">{t.list.summary(counts.running, counts.waiting)}</span>}
        actions={
          <Button size="sm" loading={runsQ.isFetching && !runsQ.isPending} onClick={() => void runsQ.refetch()}>
            {t.list.refresh}
          </Button>
        }
      />
      <div className="app-screen-body runs-body">
        {handoffPart.visible ? (
          <Tabs
            ariaLabel={t.list.views.label}
            activeId={view}
            onChange={setView}
            tabs={[
              { id: "list", label: t.list.views.list, content: null },
              ...(handoffsQ.isError && (handoffsQ.error as { status?: number }).status === 404 ? [] : [{ id: "handoffs", label: t.list.views.handoffs, content: null }]),
            ]}
          />
        ) : null}
        <RunsFilterBar
          value={filters}
          onChange={setFilters}
          graphs={lookups.graphs.map((g) => ({ id: g.id, label: g.name }))}
          agents={lookups.agents.map((a) => ({ id: a.id, label: a.name }))}
          conversations={lookups.conversations.map((c) => ({ id: c.id, label: c.title || c.id }))}
          statuses={statusOptions}
          waitingStatus={WAITING_RUN_STATUS}
          searchRef={searchRef}
          firstRef={firstRef}
        />
        {view === "handoffs" ? handoffBody : (<>{scopedRuns.bar}{body}</>)}
      </div>
      <ConfirmDialog
        open={cancelTarget !== null}
        title={t.list.cancelTitle}
        confirmLabel={t.list.cancelConfirm}
        cancelLabel={t.list.cancelKeep}
        danger
        onConfirm={confirmCancel}
        onCancel={() => setCancelTarget(null)}
      >
        {t.list.cancelBody}
      </ConfirmDialog>
    </div>
  );
}
