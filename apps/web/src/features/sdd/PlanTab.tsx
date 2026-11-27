/**
 * 계획 탭(screen-sdd §8): 서버가 계산한 계획(층·병목·준비·막힘·순환)을 의존 그래프(`PlanGraph`, 읽기 전용)와 같은 내용의 글 목록으로 보인다.
 * 그래프를 못 보는 사용자도 오른쪽 글 목록만으로 같은 정보를 얻는다. 층·병목은 서버 값을 그대로 쓰고 클라이언트는 다시 계산하지 않는다.
 * 작업이 많으면(`PLAN_GRAPH_AUTO_LIMIT`) 그래프를 자동으로 그리지 않고 글 목록을 권한다.
 */
import { useMemo, useState } from "react";
import { Banner, Button, EmptyState, Switch } from "@agent-console/ui";
import { PlanBundles, PlanGraph } from "@agent-console/sdd-view";
import type { ParsedTask } from "@agent-console/contracts/sdd";
import { ListSkeleton, FailureBlock } from "./parts";
import { PrereqState, useTaskPrereq } from "./taskPrereq";
import { PLAN_GRAPH_AUTO_LIMIT, SDD_PARAMS } from "./sddConfig";
import { RunNoticeView } from "./RunNoticeView";
import { TaskActionsMenu } from "./TaskActionsMenu";
import { useSddViewMessages } from "./useViewMessages";
import type { SddTabProps } from "./sddTabs";
import { useSpecPlan } from "./useSddApi";
import { useTaskRunner } from "./useTaskRunner";
import { useT } from "@agent-console/i18n";

const P = SDD_PARAMS;

export function PlanTab({ specId, view, ctx, goTab }: SddTabProps) {
  const t = useT("sdd");
  const viewMessages = useSddViewMessages();
  const prereq = useTaskPrereq(specId, view);
  const planQ = useSpecPlan(specId, prereq.state === "ok");
  const runner = useTaskRunner({ specId, ctx });
  const [selected, setSelected] = useState<string | null>(null);
  const [drawBig, setDrawBig] = useState(false);
  const [onlyCritical, setOnlyCritical] = useState(false);

  const tasks = useMemo(() => view.index?.tasks ?? [], [view.index?.tasks]);
  const statuses = useMemo(() => view.task_statuses ?? [], [view.task_statuses]);
  const byKey = useMemo(() => new Map(tasks.map((t) => [t.key, t] as const)), [tasks]);
  const doneIds = useMemo(() => new Set(statuses.filter((s) => s.done === true).map((s) => s.id)), [statuses]);
  const plan = planQ.data;

  const cycleKeys = useMemo(() => new Set((plan?.cycles ?? []).flat()), [plan]);
  const remaining = tasks.filter((t) => !doneIds.has(t.status));
  // 그래프는 끝나지 않은 작업만 그린다. 그리지 않은 완료 작업 수를 도구줄에 알린다
  const hiddenDone = tasks.length - remaining.length;
  const docTitles = useMemo(() => Object.fromEntries((view.spec.documents ?? []).map((d) => [d.id, d.title])), [view.spec.documents]);
  const openRules = () => goTab("rules");
  const openTask = (key: string) => goTab("tasks", { [P.task]: key });
  const title = (key: string) => byKey.get(key)?.title ?? key;

  if (prereq.state !== "ok") return <PrereqState prereq={prereq} onOpenRules={openRules} loadFailed={t("plan.loadFailed")} />;
  if (planQ.isPending) return <ListSkeleton rows={6} />;
  if (planQ.isError) return <FailureBlock error={planQ.error} title={t("plan.loadFailed")} onRetry={() => void planQ.refetch()} />;
  if (tasks.length === 0 || remaining.length === 0) {
    return (
      <div className="sdd-state" data-testid="sdd-plan-done">
        <EmptyState title={tasks.length === 0 ? t("tasks.empty.title") : t("plan.allDone")} description={tasks.length === 0 ? t("tasks.empty.body") : undefined} />
      </div>
    );
  }

  const ready = (plan?.ready ?? []).map((k) => byKey.get(k)).filter((t): t is ParsedTask => t !== undefined);
  const blocked = (plan?.blocked ?? []).map((k) => byKey.get(k)).filter((t): t is ParsedTask => t !== undefined);
  const critical = plan?.critical_path ?? [];
  const tooBig = remaining.length > PLAN_GRAPH_AUTO_LIMIT && !drawBig;
  const runsOn = ctx.capabilities.runs;
  const startBlocked = ctx.runBlockedReason ?? (ctx.readOnly ? ctx.readOnlyReason : undefined);
  const pick = selected === null ? undefined : byKey.get(selected);

  return (
    <div className="sdd-plan" data-testid="sdd-plan">
      <RunNoticeView runner={runner} documentTitles={docTitles} onOpenDocument={(id) => goTab("documents", { [P.doc]: id })} onOpenRules={openRules} canImport={ctx.projectId !== null} />
      {cycleKeys.size > 0 ? <Banner tone="danger" data-testid="sdd-plan-cycles">{t("plan.cycleBar", { count: cycleKeys.size })}</Banner> : null}
      <div className="sdd-plan-body">
        <div className="sdd-plan-graph">
          <div className="sdd-toolbar" role="group" aria-label={t("plan.graphLabel")}>
            <Switch checked={onlyCritical} onChange={setOnlyCritical} label={t("plan.onlyCritical")} onText={t("on")} offText={t("off")} />
            {pick === undefined ? null : (
              <span className="sdd-inline" role="status">
                <span>{t("plan.selected", { title: pick.title ?? pick.key })}</span>
                <Button size="sm" onClick={() => openTask(pick.key)}>{t("plan.openTask")}</Button>
              </span>
            )}
            <span className="sdd-spacer" />
            {hiddenDone > 0 ? <span className="app-muted sdd-note" data-testid="sdd-plan-hidden-done">{t("plan.hiddenDone", { count: hiddenDone })}</span> : null}
          </div>
          {tooBig ? (
            <div className="sdd-state" data-testid="sdd-plan-toobig">
              <p role="status">{t("plan.tooBig", { n: remaining.length })}</p>
              <Button size="sm" onClick={() => { setDrawBig(true); setOnlyCritical(true); }}>{t("plan.drawAnyway")}</Button>
            </div>
          ) : (
            <PlanGraph plan={plan ?? {}} tasks={remaining} statuses={statuses} selectedKey={selected} onSelect={setSelected} height={420} onlyCritical={onlyCritical} messages={viewMessages} />
          )}
        </div>
        <aside className="sdd-plan-side" aria-label={t("plan.bundles")}>
          {critical.length > 0 ? (
            <section aria-label={t("plan.bottleneck")}>
              <h2 className="sdd-section-title">{t("plan.bottleneck")}</h2>
              <p data-testid="sdd-plan-critical">{t("plan.bottleneckLine", { chain: critical.join(" → "), n: critical.length })}</p>
            </section>
          ) : null}
          <section aria-label={t("plan.ready")}>
            <h2 className="sdd-section-title">{t("plan.ready")} ({ready.length})</h2>
            <ul className="sdd-plan-list">
              {ready.map((t) => (
                <li key={t.key}>
                  <button type="button" className="app-link-btn" onClick={() => openTask(t.key)}><span className="sdd-mono">{t.key}</span> {t.title ?? t.key}</button>
                  {runsOn ? <TaskActionsMenu specId={specId} task={t} busy={runner.busyKey === t.key} blockedReason={startBlocked} onRun={(task, action) => void runner.run(task, action)} onBlockedPick={runner.showIssue} /> : null}
                </li>
              ))}
            </ul>
          </section>
          <PlanBundles plan={plan ?? {}} tasks={remaining} onSelect={openTask} messages={viewMessages} />
          <section aria-label={t("plan.blocked")}>
            <h2 className="sdd-section-title">{t("plan.blocked")} ({blocked.length})</h2>
            <ul className="sdd-plan-list">
              {blocked.map((task) => {
                const waiting = (task.dependencies ?? []).filter((d) => {
                  const dep = byKey.get(d);
                  return dep !== undefined && !doneIds.has(dep.status);
                });
                return (
                  <li key={task.key}>
                    <button type="button" className="app-link-btn" onClick={() => openTask(task.key)}><span className="sdd-mono">{task.key}</span> {title(task.key)}</button>
                    {waiting.length > 0 ? <span className="app-muted sdd-note"> {t("plan.blockedBy", { keys: waiting.join(", ") })}</span> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        </aside>
      </div>
      {runner.dialog}
    </div>
  );
}
