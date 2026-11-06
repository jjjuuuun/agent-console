/**
 * 추적 탭(screen-sdd §9): 요구 ↔ 작업 ↔ 실행 ↔ 검증 표(`TraceMatrix`, 가상 목록). 서버가 계산한 표를 그대로 쓰고, 검색·빈 곳 거르기는 보이는 행만 가른다.
 * 빈 곳 코드·검증 결과의 톤과 문구는 표시 데이터(`sddData.json` + messages)에서 읽고, 모르는 코드는 경고 톤 + 원문으로 보인다.
 * 작업 칩은 작업 탭으로, 요구는 아래 상세(위치·연결 작업·검증 결과·빈 곳 설명)로 이동한다. 거르기·선택은 주소(`q`·`only`·`gaps`·`req`)가 진실이다.
 */
import { useMemo } from "react";
import { useNavigate } from "react-router";
import { Button, Disclosure, EmptyState, Switch } from "@agent-console/ui";
import { ToneChip, TraceMatrix } from "@agent-console/sdd-view";
import { KNOWN_DOCUMENT_ROLES } from "@agent-console/contracts/constants";
import type { CodeDisplayTable } from "@agent-console/sdd-view";
import type { TaskLink, TraceRow } from "@agent-console/contracts/sdd";
import { ROUTE_ROLES, routePath } from "../library";
import { FailureBlock, ListSkeleton, MultiFilter, SearchBox } from "./parts";
import { PrereqState, useTaskPrereq } from "./taskPrereq";
import { gapDisplay, OPENABLE_LINK_KINDS, SDD_PARAMS, verificationDisplay } from "./sddConfig";
import { lookupSpecKey, sddMessages as m, viewMessages } from "./messages";
import { setList } from "./params";
import type { SddTabProps } from "./sddTabs";
import { useSpecTrace } from "./useSddApi";

const P = SDD_PARAMS;

/** 코드 → 보일 값 표: 톤은 표시 데이터, 문구는 messages(키가 없으면 비워 두어 컴포넌트가 원문을 쓴다). */
function displayTable(codes: Iterable<string>, of: (code: string) => { tone: string; labelKey?: string; hintKey?: string }): CodeDisplayTable {
  const out: Record<string, { tone: string; label?: string; hint?: string }> = {};
  for (const code of codes) {
    const d = of(code);
    const label = lookupSpecKey(d.labelKey);
    const hint = lookupSpecKey(d.hintKey);
    out[code] = { tone: d.tone, ...(label === undefined ? {} : { label }), ...(hint === undefined ? {} : { hint }) };
  }
  return out;
}

export function TraceTab({ specId, view, ctx, params, setParams, goTab }: SddTabProps) {
  const navigate = useNavigate();
  const prereq = useTaskPrereq(specId, view);
  const traceQ = useSpecTrace(specId, prereq.state === "ok");
  const matrix = traceQ.data;
  const rows = useMemo(() => matrix?.rows ?? [], [matrix]);

  const q = params.get(P.q) ?? "";
  const only = params.get(P.only) === "1";
  const gapKey = params.getAll(P.gaps).join(",");
  const gapSel = useMemo(() => (gapKey === "" ? [] : gapKey.split(",")), [gapKey]);
  const reqId = params.get(P.req);

  const patch = (next: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(params);
    next(p);
    setParams(p, { replace: true });
  };

  const gapCodes = useMemo(() => [...new Set(rows.flatMap((r) => r.gaps ?? []))], [rows]);
  const verifyCodes = useMemo(() => [...new Set(rows.flatMap((r) => (r.verification ? [r.verification.status] : [])))], [rows]);
  const gapTable = useMemo(() => displayTable(gapCodes, gapDisplay), [gapCodes]);
  const verifyTable = useMemo(() => displayTable(verifyCodes, verificationDisplay), [verifyCodes]);
  const gapLabel = (code: string) => gapTable[code]?.label ?? code;

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (needle !== "" && !`${r.id} ${r.title ?? ""}`.toLowerCase().includes(needle)) return false;
      if (gapSel.length > 0 && !(r.gaps ?? []).some((g) => gapSel.includes(g))) return false;
      return true;
    });
  }, [rows, q, gapSel]);

  const totalGaps = rows.reduce((n, r) => n + (r.gaps ?? []).length, 0);
  const docTitles = useMemo(() => Object.fromEntries((view.spec.documents ?? []).map((d) => [d.id, d.title])), [view.spec.documents]);
  const reqDoc = (view.spec.documents ?? []).find((d) => (d.roles ?? []).includes(KNOWN_DOCUMENT_ROLES.REQUIREMENTS));
  const openRules = () => goTab("rules");
  const openTask = (key: string) => goTab("tasks", { [P.task]: key });
  const openLink = (link: TaskLink) => {
    if (OPENABLE_LINK_KINDS.includes(link.kind)) void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(link.ref)}`);
  };

  if (prereq.state !== "ok") return <PrereqState prereq={prereq} onOpenRules={openRules} loadFailed={m.trace.loadFailed} />;
  if (traceQ.isPending) return <ListSkeleton rows={8} />;
  if (traceQ.isError) return <FailureBlock error={traceQ.error} title={m.trace.loadFailed} onRetry={() => void traceQ.refetch()} />;
  if (rows.length === 0) {
    return (
      <div className="sdd-state" data-testid="sdd-trace-empty">
        <EmptyState
          title={m.trace.emptyTitle}
          description={m.trace.emptyBody}
          action={
            <>
              {reqDoc === undefined ? null : <Button size="sm" onClick={() => goTab("documents", { [P.doc]: reqDoc.id })}>{m.trace.openRequirement}</Button>}
              <Button size="sm" onClick={openRules}>{m.trace.openRules}</Button>
            </>
          }
        />
      </div>
    );
  }

  const selectedRow: TraceRow | undefined = reqId === null ? undefined : rows.find((r) => r.id === reqId);
  const showVerification = ctx.capabilities.verification || rows.some((r) => r.verification != null);
  const orphans = matrix?.orphans;
  const orphanCount = (orphans?.tasks_without_requirements?.length ?? 0) + (orphans?.unknown_requirement_refs?.length ?? 0) + (orphans?.unknown_task_links?.length ?? 0);
  const filtering = q.trim() !== "" || gapSel.length > 0 || only;
  const shownRows = only ? visible.filter((r) => (r.gaps ?? []).length > 0) : visible;

  return (
    <div className="sdd-trace" data-testid="sdd-trace">
      <div className="sdd-toolbar" role="group" aria-label={m.trace.search}>
        <SearchBox value={q} onCommit={(next) => patch((p) => (next.trim() === "" ? p.delete(P.q) : p.set(P.q, next)))} label={m.trace.search} />
        {gapCodes.length === 0 ? null : <MultiFilter label={m.trace.gapFilter} options={gapCodes.map((c) => ({ id: c, label: gapLabel(c) }))} selected={gapSel} onChange={(next) => patch((p) => setList(p, P.gaps, next))} />}
        <Switch checked={only} onChange={(on) => patch((p) => (on ? p.set(P.only, "1") : p.delete(P.only)))} label={m.trace.gapsOnly} onText={m.on} offText={m.off} />
        <span className="sdd-spacer" />
        <span role="status" data-testid="sdd-trace-summary">
          {m.trace.summary(rows.length, totalGaps)}
          {filtering ? <span className="app-muted"> · {m.trace.shown(shownRows.length)}</span> : null}
        </span>
        {totalGaps === 0 ? <ToneChip label={m.trace.noGaps} tone="success" /> : null}
      </div>
      {filtering && shownRows.length === 0 ? (
        <div className="sdd-state">
          <p role="status">{m.trace.noMatch}</p>
          <button type="button" className="app-link-btn" onClick={() => patch((p) => [P.q, P.gaps, P.only].forEach((k) => p.delete(k)))}>{m.trace.clear}</button>
        </div>
      ) : (
        <div className="sdd-trace-table">
          <TraceMatrix
            matrix={{ ...(matrix ?? {}), rows: visible }}
            gapDisplay={gapTable}
            verificationDisplay={verifyTable}
            showRuns={ctx.capabilities.runs}
            showVerification={showVerification}
            openableKinds={OPENABLE_LINK_KINDS}
            onOpenLink={openLink}
            onOpenTask={(key) => openTask(key)}
            onOpenRequirement={(row) => patch((p) => p.set(P.req, row.id))}
            onlyGaps={only}
            onOnlyGapsChange={(on) => patch((p) => (on ? p.set(P.only, "1") : p.delete(P.only)))}
            messages={viewMessages}
          />
        </div>
      )}
      {selectedRow === undefined ? null : (
        <section className="sdd-trace-detail" aria-label={m.trace.selectedReq(selectedRow.id)} data-testid="sdd-trace-detail">
          <h3 className="sdd-section-title">{m.trace.selectedReq(selectedRow.id)} {selectedRow.title ?? ""}</h3>
          <dl className="sdd-detail-list">
            <dt>{m.trace.detail.location}</dt>
            <dd>
              <button type="button" className="app-link-btn" onClick={() => goTab("documents", { [P.doc]: selectedRow.document, [P.line]: String(selectedRow.line) })}>
                {docTitles[selectedRow.document] ?? selectedRow.document}:{selectedRow.line}
              </button>
            </dd>
            <dt>{m.trace.detail.tasks}</dt>
            <dd>{(selectedRow.tasks ?? []).length === 0 ? <span className="app-muted">{m.trace.detail.none}</span> : (selectedRow.tasks ?? []).map((k) => <button key={k} type="button" className="app-link-btn sdd-mono" onClick={() => openTask(k)}>{k}</button>)}</dd>
            <dt>{m.trace.detail.results}</dt>
            <dd>
              {(selectedRow.results ?? []).length === 0 ? <span className="app-muted">{m.trace.detail.none}</span> : (
                <ul className="sdd-plan-list">
                  {(selectedRow.results ?? []).map((r, i) => {
                    const d = verificationDisplay(r.status);
                    return (
                      <li key={`${r.source}:${r.status}:${i}`}>
                        <ToneChip label={lookupSpecKey(d.labelKey) ?? r.status} tone={d.tone} /> <span className="app-muted">{r.label ?? ""} {r.source}</span>
                        {r.ref?.run_id ? <button type="button" className="app-link-btn sdd-mono" onClick={() => void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(r.ref?.run_id ?? "")}`)}>{r.ref.run_id}</button> : null}
                        {r.ref?.path ? <span className="sdd-mono">{r.ref.path}</span> : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </dd>
            <dt>{m.trace.detail.gaps}</dt>
            <dd>
              {(selectedRow.gaps ?? []).length === 0 ? <span className="app-muted">{m.trace.detail.none}</span> : (
                <ul className="sdd-plan-list">
                  {(selectedRow.gaps ?? []).map((g) => <li key={g}><strong>{gapLabel(g)}</strong> <span className="app-muted">{gapTable[g]?.hint ?? ""}</span></li>)}
                </ul>
              )}
            </dd>
          </dl>
          <Button size="sm" onClick={() => patch((p) => p.delete(P.req))}>{m.trace.detail.close}</Button>
        </section>
      )}
      {orphanCount === 0 ? null : (
        <Disclosure summary={`${m.trace.orphans} ${orphanCount}`}>
          <div data-testid="sdd-trace-orphans">
            {(orphans?.tasks_without_requirements ?? []).length > 0 ? (
              <section><h4>{m.trace.orphanTasksNoReq}</h4><ul className="sdd-plan-list">{(orphans?.tasks_without_requirements ?? []).map((k) => <li key={k}><button type="button" className="app-link-btn sdd-mono" onClick={() => openTask(k)}>{k}</button></li>)}</ul></section>
            ) : null}
            {(orphans?.unknown_requirement_refs ?? []).length > 0 ? (
              <section><h4>{m.trace.orphanUnknownReq}</h4><ul className="sdd-plan-list">{(orphans?.unknown_requirement_refs ?? []).map((u) => <li key={`${u.task_key}:${u.requirement_id}`}><span className="sdd-mono">{u.task_key}</span> → <span className="sdd-mono">{u.requirement_id}</span></li>)}</ul></section>
            ) : null}
            {(orphans?.unknown_task_links ?? []).length > 0 ? (
              <section><h4>{m.trace.orphanUnknownTask}</h4><p className="app-muted sdd-note">{m.trace.orphanUnknownTaskHint}</p><ul className="sdd-plan-list">{(orphans?.unknown_task_links ?? []).map((l) => <li key={`${l.ref}:${l.task_key ?? ""}`}><span className="sdd-mono">{l.ref}</span> → <span className="sdd-mono">{l.task_key ?? ""}</span></li>)}</ul></section>
            ) : null}
          </div>
        </Disclosure>
      )}
    </div>
  );
}
