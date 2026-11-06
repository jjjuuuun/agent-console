/**
 * 작업 탭(screen-sdd §7): 도구줄(검색·상태·단계·준비만, 모두 주소에 담긴다) + 작업 표(`TaskTable`, 가상 목록·단계 묶음·인라인 펼침).
 * 상태 바꾸기는 "그 줄 하나 고치기"라 낙관적으로 바꾸지 않고 서버 응답·`sdd.changed`로 닫는다. 줄이 바뀌었으면(409) 최신 줄로 다시 그린다.
 * 상태·단계·필드 이름은 서버 데이터다. 실행 연동(동작 메뉴·한꺼번에 시작)은 `renderActions` 자리만 남아 있다(실행 연결 작업이 채운다).
 */
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { KNOWN_DOCUMENT_ROLES } from "@agent-console/contracts/constants";
import { Banner, EmptyState, Switch, useToast } from "@agent-console/ui";
import { TaskTable } from "@agent-console/sdd-view";
import type { ParsedTask, SddGateBlockedDetails, SddTaskChangedDetails, TaskLink } from "@agent-console/contracts/sdd";
import { messages as appMessages } from "../../app/messages";
import { ROUTE_ROLES, routePath } from "../library";
import { BulkStartDialog } from "./BulkStartDialog";
import { RunNoticeView } from "./RunNoticeView";
import { FailureBlock, GuardedButton, ListSkeleton, MultiFilter, SearchBox } from "./parts";
import { OPENABLE_LINK_KINDS, RUN_STATUS_TONES, SDD_PARAMS } from "./sddConfig";
import { TaskActionsMenu } from "./TaskActionsMenu";
import { useTaskRunner } from "./useTaskRunner";
import { sddMessages as m, viewMessages } from "./messages";
import type { SddTabProps } from "./sddTabs";
import { sddKeys, useSddSpace, useSpecSyntax, useSpecTasks } from "./useSddApi";
import { readTaskFilter, setList, taskQueryOf } from "./params";

const P = SDD_PARAMS;

/** 실행 칩의 상태 라벨·톤: 라벨은 앱 공용 실행 상태 표, 톤은 표시 데이터(`sddData.json`). 모르는 상태는 원문 + 중립. */
const LINK_STATUSES = Object.entries(appMessages.runStatus).map(([id, label]) => ({ id, label, tone: RUN_STATUS_TONES[id] ?? null }));

export interface TasksTabProps extends SddTabProps {
  /** 행 오른쪽 동작 자리. 주지 않으면 연동 동작 메뉴(`TaskActionsMenu`)를 쓴다. 실행 연동이 꺼졌으면 그리지 않는다 */
  renderActions?: (task: ParsedTask) => ReactNode;
  /** 도구줄 오른쪽 자리(기본 [준비된 작업 시작…] 앞에 더해진다) */
  toolbarExtra?: ReactNode;
}

export function TasksTab({ specId, view, ctx, params, setParams, goTab, ownHashes, refresh, renderActions, toolbarExtra }: TasksTabProps) {
  const space = useSddSpace();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const syntax = useSpecSyntax(specId);
  const [conflicts, setConflicts] = useState<Readonly<Record<string, SddTaskChangedDetails>>>({});
  const [gate, setGate] = useState<SddGateBlockedDetails | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const runsOn = ctx.capabilities.runs;
  const runner = useTaskRunner({
    specId,
    ctx,
    onTaskChanged: (task, details) => {
      setConflicts((c) => ({ ...c, [task.key]: details }));
      toast({ tone: "warning", text: m.tasks.statusFail409(task.title ?? task.key), durationMs: 8000, action: { label: m.tasks.openInDoc, onClick: () => goTab("documents", { [P.doc]: task.document, [P.line]: String(task.line) }) } });
      void tasksQ.refetch();
      void refresh();
    },
  });

  const statuses = useMemo(() => (view.task_statuses ?? []).length > 0 ? view.task_statuses ?? [] : syntax.data?.statuses ?? [], [view.task_statuses, syntax.data]);
  const stages = view.index?.stages ?? [];
  const docs = useMemo(() => view.spec.documents ?? [], [view.spec.documents]);
  const hasTaskDoc = docs.some((d) => (d.roles ?? []).includes(KNOWN_DOCUMENT_ROLES.TASKS));
  const syntaxEmpty = syntax.data?.empty === true;

  const filter = useMemo(() => readTaskFilter(params), [params]);
  const query = useMemo(() => taskQueryOf(filter), [filter]);
  const filtering = Object.keys(query).length > 0;
  const tasksQ = useSpecTasks(specId, query, hasTaskDoc && !syntaxEmpty && syntax.isSuccess);
  const tasks = useMemo(() => tasksQ.data ?? [], [tasksQ.data]);

  const patch = (next: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(params);
    next(p);
    setParams(p, { replace: true });
  };

  const changeStatus = async (task: ParsedTask, statusId: string) => {
    setFailure(null);
    setGate(null);
    try {
      const result = await space.client.patchSpecTask(specId, task.key, { status: statusId, expected_line_hash: task.line_hash });
      ownHashes.current.add(result.version_hash);
      setConflicts((c) => {
        const { [task.key]: _gone, ...rest } = c;
        void _gone;
        return rest;
      });
      void qc.invalidateQueries({ queryKey: sddKeys.root });
    } catch (e) {
      if (e instanceof ApiError && e.code === ERROR_CODES.SDD_TASK_CHANGED) {
        setConflicts((c) => ({ ...c, [task.key]: e.details as unknown as SddTaskChangedDetails }));
        toast({ tone: "warning", text: m.tasks.statusFail409(task.title ?? task.key), durationMs: 8000, action: { label: m.tasks.openInDoc, onClick: () => openDocument(task) } });
        void tasksQ.refetch();
        void refresh();
      } else if (e instanceof ApiError && e.code === ERROR_CODES.SDD_GATE_BLOCKED) {
        setGate(e.details as unknown as SddGateBlockedDetails);
      } else {
        setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.tasks.statusFailed);
      }
    }
  };
  const openDocument = (task: ParsedTask) => goTab("documents", { [P.doc]: task.document, [P.line]: String(task.line) });
  const openLink = (link: TaskLink) => {
    if (OPENABLE_LINK_KINDS.includes(link.kind)) void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(link.ref)}`);
  };

  const doneIds = useMemo(() => new Set(statuses.filter((s) => s.done === true).map((s) => s.id)), [statuses]);
  const readyTasks = useMemo(() => (view.index?.tasks ?? []).filter((x) => x.ready === true && !doneIds.has(x.status)), [view.index?.tasks, doneIds]);
  const startBlocked = ctx.runBlockedReason ?? (ctx.readOnly ? ctx.readOnlyReason : undefined);

  const docTitles = useMemo(() => Object.fromEntries(docs.map((d) => [d.id, d.title])), [docs]);
  const openRules = () => goTab("rules");

  if (syntax.isPending) return <ListSkeleton rows={8} />;
  if (syntax.isError) return <FailureBlock error={syntax.error} title={m.tasks.loadFailed} onRetry={() => void syntax.refetch()} />;
  if (syntaxEmpty) {
    return (
      <div className="sdd-state" data-testid="sdd-syntax-missing">
        <EmptyState title={m.tasks.syntaxMissing.title} description={m.tasks.syntaxMissing.body} action={<button type="button" className="app-link-btn" onClick={openRules}>{m.tasks.syntaxMissing.open}</button>} />
      </div>
    );
  }
  if (!hasTaskDoc) {
    return (
      <div className="sdd-state" data-testid="sdd-no-task-doc">
        <EmptyState title={m.tasks.noTaskDoc.title} description={m.tasks.noTaskDoc.body} action={<button type="button" className="app-link-btn" onClick={openRules}>{m.tasks.noTaskDoc.open}</button>} />
      </div>
    );
  }

  const issues = (view.index?.issues ?? []).filter((i) => i.document !== undefined && i.document !== null && docs.some((d) => d.id === i.document && (d.roles ?? []).includes(KNOWN_DOCUMENT_ROLES.TASKS)));

  return (
    <div className="sdd-tasks">
      <div className="sdd-toolbar" role="group" aria-label={m.tasks.search}>
        <SearchBox value={filter.q} onCommit={(q) => patch((p) => (q.trim() === "" ? p.delete(P.q) : p.set(P.q, q)))} label={m.tasks.search} />
        <MultiFilter label={m.tasks.status} options={statuses.map((s) => ({ id: s.id, label: s.label }))} selected={filter.status} onChange={(next) => patch((p) => setList(p, P.status, next))} />
        {stages.length === 0 ? null : <MultiFilter label={m.tasks.stage} options={stages.map((s) => ({ id: s.id, label: s.title ?? s.id }))} selected={filter.stage} onChange={(next) => patch((p) => setList(p, P.stage, next))} />}
        <Switch checked={filter.ready} onChange={(on) => patch((p) => (on ? p.set(P.ready, "1") : p.delete(P.ready)))} label={m.tasks.readyOnly} onText={m.on} offText={m.off} />
        <span className="sdd-spacer" />
        {toolbarExtra}
        {view.automation_state?.enabled === true ? <button type="button" className="sdd-auto-chip" onClick={openRules} data-testid="sdd-auto-chip">⟳ {m.automation.on}</button> : null}
        {runsOn ? (
          <GuardedButton blockedReason={readyTasks.length === 0 ? m.bulk.selectReady : startBlocked} onClick={() => setBulkOpen(true)}>{m.bulk.open}</GuardedButton>
        ) : null}
        <span className="app-muted" role="status">{m.tasks.count(tasks.length)}</span>
      </div>
      {!runsOn ? <p className="app-muted sdd-note" data-testid="sdd-runs-off">{m.runsOff}</p> : null}
      <RunNoticeView runner={runner} extraGate={gate} onDismissExtra={() => setGate(null)} documentTitles={docTitles} onOpenDocument={(id) => goTab("documents", { [P.doc]: id })} onOpenRules={openRules} canImport={ctx.projectId !== null} />
      {failure === null ? null : <Banner tone="danger">{failure}</Banner>}
      {issues.length > 0 ? (
        <details className="sdd-issues">
          <summary>{m.tasks.issuesBar(issues.length)}</summary>
          <ul>{issues.map((i, idx) => <li key={`${i.code}:${i.line ?? ""}:${idx}`}>{i.message}</li>)}</ul>
        </details>
      ) : null}
      {tasksQ.isPending ? (
        <ListSkeleton rows={8} />
      ) : tasksQ.isError ? (
        <FailureBlock error={tasksQ.error} title={m.tasks.loadFailed} onRetry={() => void tasksQ.refetch()} />
      ) : filtering && tasks.length === 0 ? (
        <div className="sdd-state">
          <p role="status">{m.tasks.noMatch}</p>
          <button type="button" className="app-link-btn" onClick={() => patch((p) => [P.status, P.stage, P.ready, P.q].forEach((k) => p.delete(k)))}>{m.tasks.clear}</button>
        </div>
      ) : (
        <div className="sdd-task-table">
          <TaskTable
            tasks={tasks}
            statuses={statuses}
            stages={stages}
            onOpenRules={openRules}
            {...(ctx.readOnly && ctx.readOnlyReason !== undefined ? { blockedReason: ctx.readOnlyReason } : {})}
            onStatusChange={(task, id) => void changeStatus(task, id)}
            conflicts={conflicts}
            onDismissConflict={(key) => setConflicts((c) => { const { [key]: _gone, ...rest } = c; void _gone; return rest; })}
            onOpenDocument={openDocument}
            documentTitles={docTitles}
            showLinks={runsOn}
            openableKinds={OPENABLE_LINK_KINDS}
            onOpenLink={openLink}
            linkStatuses={LINK_STATUSES}
            {...(runsOn
              ? {
                  renderActions:
                    renderActions ??
                    ((task: ParsedTask) => (
                      <TaskActionsMenu specId={specId} task={task} busy={runner.busyKey === task.key} blockedReason={startBlocked} onRun={(tk, action) => void runner.run(tk, action)} onBlockedPick={runner.showIssue} />
                    )),
                }
              : {})}
            expandedKey={params.get(P.task)}
            onExpandedChange={(key) => patch((p) => (key === null ? p.delete(P.task) : p.set(P.task, key)))}
            messages={viewMessages}
          />
        </div>
      )}
      {bulkOpen ? <BulkStartDialog open onClose={() => setBulkOpen(false)} specId={specId} readyTasks={readyTasks} limit={ctx.info?.limits.max_bulk_start} blockedReason={startBlocked} /> : null}
      {runner.dialog}
    </div>
  );
}
