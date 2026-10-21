import { useState } from "react";
import { Button, Disclosure } from "@agent-console/ui";
import type { LogProjectGroup, WorkspaceSettings } from "@agent-console/contracts";
import { useApi } from "../../../../app/ApiContext";
import { FILTER_KEYS, UNGROUPED_OPTIONS, logsMessages as t, useLogSchema } from "../../../logs";
import type { SectionEditProps } from "../FormSections";
import { patchLogs } from "./helpers";

/** 프로젝트 묶기: 작업 폴더(cwd) 글롭 → 그룹(순서가 의미), 묶이지 않은 항목 정책, Git 작업 트리 묶기. 글롭은 서버가 평가한다. */
export function LogsProjectsBlock({ value, onChange, disabled, errors }: SectionEditProps) {
  const text = t.settings.projects;
  const projects = value.logs?.projects ?? {};
  const groups: LogProjectGroup[] = (projects.groups ?? []) as LogProjectGroup[];
  const schema = useLogSchema();
  const { rest } = useApi();
  const [rows, setRows] = useState<{ path: string; group: string; events: number }[] | "loading" | null>(null);
  const setProjects = (patch: Record<string, unknown>) => {
    const next: Record<string, unknown> = { ...projects };
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined) delete next[k];
      else next[k] = v;
    }
    onChange({ ...value, logs: patchLogs(value.logs, { projects: Object.keys(next).length === 0 ? undefined : next }) } as WorkspaceSettings);
  };
  const setGroups = (next: LogProjectGroup[]) => setProjects({ groups: next.length === 0 ? undefined : next });
  const patchGroup = (i: number, patch: Partial<LogProjectGroup>) => setGroups(groups.map((g, j) => (j === i ? { ...g, ...patch } : g)));
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= groups.length) return;
    const next = [...groups];
    [next[i], next[j]] = [next[j] as LogProjectGroup, next[i] as LogProjectGroup];
    setGroups(next);
  };
  const dupIds = new Set(groups.map((g) => g.id).filter((id, i, a) => id !== "" && a.indexOf(id) !== i));
  const ungrouped = projects.ungrouped ?? undefined;
  const known = UNGROUPED_OPTIONS.some((o) => o.value === ungrouped);

  const cwdDim = schema.data?.dimensions?.find((d) => d.id === FILTER_KEYS.cwd)?.id;
  const projDim = schema.data?.dimensions?.find((d) => d.id === FILTER_KEYS.project)?.id;
  const metric = schema.data?.metrics?.find((x) => x.unit === "count")?.id;
  // 펼칠 때 한 번만 읽는다(저장된 규칙 기준 확인용)
  const loadPreview = () => {
    if (rows !== null || cwdDim === undefined || projDim === undefined || metric === undefined) return;
    setRows("loading");
    rest
      .aggregateLogs({ group_by: [cwdDim, projDim], metric, filter: {} })
      .then((r) => setRows(r.slice(0, 50).map((x) => ({ path: x.keys?.[cwdDim] ?? "", group: x.keys?.[projDim] ?? "", events: x.value ?? 0 }))))
      .catch(() => setRows([]));
  };

  return (
    <div className="logs-projects">
      <p className="app-muted">{text.description}</p>
      <h4 className="app-block-subtitle">{text.groups}</h4>
      {groups.length === 0 ? <p className="app-muted">{text.empty}</p> : null}
      <ol className="logs-grouplist">
        {groups.map((g, i) => {
          const lines = (g.match ?? []) as string[];
          const emptyLine = lines.some((l) => l.trim() === "");
          const rowErrors = (errors ?? []).filter((e) => e.path.startsWith(`/logs/projects/groups/${i}`)).map((e) => e.message);
          return (
            <li
              key={i}
              className="logs-group"
              onKeyDown={(e) => {
                if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
                  e.preventDefault();
                  move(i, e.key === "ArrowUp" ? -1 : 1);
                }
              }}
            >
              <span className="logs-badge" aria-label={`${i + 1}`}>{i + 1}</span>
              <input className="logs-input" aria-label={`${i + 1} ${text.groupId}`} placeholder={text.groupId} value={g.id} disabled={disabled} onChange={(e) => patchGroup(i, { id: e.target.value })} />
              <input className="logs-input" aria-label={`${i + 1} ${text.groupLabel}`} placeholder={text.groupLabel} value={g.label ?? ""} disabled={disabled} onChange={(e) => patchGroup(i, { label: e.target.value === "" ? null : e.target.value })} />
              <textarea className="logs-input logs-glob" rows={2} aria-label={`${i + 1} ${text.groupMatch}`} placeholder={text.groupMatch} value={lines.join("\n")} disabled={disabled} spellCheck={false} onChange={(e) => patchGroup(i, { match: e.target.value === "" ? [] : e.target.value.split("\n") })} />
              <Button size="sm" disabled={disabled || i === 0} aria-label={`${i + 1} ${text.moveUp}`} onClick={() => move(i, -1)}>↑</Button>
              <Button size="sm" disabled={disabled || i === groups.length - 1} aria-label={`${i + 1} ${text.moveDown}`} onClick={() => move(i, 1)}>↓</Button>
              <Button size="sm" disabled={disabled} aria-label={`${i + 1} ${text.remove}`} onClick={() => setGroups(groups.filter((_, j) => j !== i))}>{text.remove}</Button>
              {g.id === "" ? <p className="app-field-error" role="alert">{text.idEmpty}</p> : dupIds.has(g.id) ? <p className="app-field-error" role="alert">{text.idDuplicate}</p> : null}
              {emptyLine ? <p className="app-field-error" role="alert">{text.globEmptyLine}</p> : null}
              {rowErrors.map((msg, k) => <p key={k} className="app-field-error" role="alert">{msg}</p>)}
            </li>
          );
        })}
      </ol>
      <p className="app-muted logs-note">{text.globHelp}</p>
      <Button size="sm" disabled={disabled} onClick={() => setGroups([...groups, { id: "", label: null, match: [] }])}>{text.addGroup}</Button>

      <fieldset className="logs-ungrouped">
        <legend>{text.ungroupedTitle}</legend>
        <p className="app-muted">{ungrouped === undefined ? text.ungroupedDefault : ""}</p>
        {[...UNGROUPED_OPTIONS, ...(ungrouped !== undefined && !known ? [{ value: String(ungrouped), label: `${text.ungroupedOriginal}: ${String(ungrouped)}`, description: "" }] : [])].map((o) => (
          <label key={o.value} className="logs-choice">
            <input type="radio" name="logs-ungrouped" checked={ungrouped === o.value} disabled={disabled} onChange={() => setProjects({ ungrouped: o.value })} />
            <strong>{o.label}</strong>
            {o.description ? <span className="app-muted"> {o.description}</span> : null}
          </label>
        ))}
        {ungrouped !== undefined ? <Button size="sm" variant="ghost" disabled={disabled} onClick={() => setProjects({ ungrouped: undefined })}>↺</Button> : null}
      </fieldset>

      <label className="app-check">
        <input type="checkbox" checked={projects.git_worktrees ?? true} disabled={disabled} onChange={(e) => setProjects({ git_worktrees: e.target.checked === true ? undefined : false })} />
        {text.worktrees}{projects.git_worktrees == null ? ` (${text.worktreesDefault})` : ""}
      </label>
      <p className="app-muted logs-note">{text.worktreesNote}</p>

      {cwdDim !== undefined && projDim !== undefined && metric !== undefined ? (
        <Disclosure summary={text.preview} onOpenChange={(o) => o && loadPreview()}>
          <p className="app-muted">{text.previewNote}</p>
          {rows === "loading" ? <p className="app-muted">{text.previewLoading}</p> : Array.isArray(rows) && rows.length > 0 ? (
            <table className="logs-table">
              <thead><tr><th scope="col">{text.previewColumns.path}</th><th scope="col">{text.previewColumns.group}</th><th scope="col">{text.previewColumns.events}</th></tr></thead>
              <tbody>{rows.map((r, i) => <tr key={i}><td className="ac-ellipsis" title={r.path}>{r.path}</td><td>{r.group || "–"}</td><td>{r.events.toLocaleString("ko-KR")}</td></tr>)}</tbody>
            </table>
          ) : <p className="app-muted">{text.previewEmpty}</p>}
        </Disclosure>
      ) : null}
    </div>
  );
}
