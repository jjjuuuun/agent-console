import { useMemo, useState } from "react";
import { Button, ConfirmDialog, Disclosure } from "@agent-console/ui";
import { ColorSlotPicker, slotColor } from "@agent-console/log-view";
import type { LogCategory, LogTaxonomy, WorkspaceSettings } from "@agent-console/contracts";
import { ErrorBlock } from "../../../../app/ErrorBlock";
import { messages as m } from "../../../../app/messages";
import { useApi } from "../../../../app/ApiContext";
import { FILTER_KEYS, TONE_VOCABULARY, logsMessages as t, slotFor, useLogSchema, useLogTaxonomy } from "../../../logs";
import { Skeleton } from "../../Skeleton";
import type { SectionEditProps } from "../FormSections";
import { patchLogs } from "./helpers";

const MAX_ID = 64;

function mergedColor(key: string, color: string | null | undefined): string {
  if (color && /^(cat-[1-8]|neutral)$/.test(color)) return color === "neutral" ? "var(--ac-text-muted)" : `var(--ac-${color})`;
  return slotColor(slotFor(key));
}

/** 분류 체계 편집: 범주 id별 표시 이름·설명·보임·색·톤. 목록에 없는 범주는 데이터에서 찾아 추가할 수 있다. */
export function LogsTaxonomyBlock({ value, onChange, disabled, errors }: SectionEditProps) {
  const effective = useLogTaxonomy();
  const schema = useLogSchema();
  const { rest } = useApi();
  const overrides: Record<string, LogCategory> = (value.logs?.taxonomy?.categories ?? {}) as Record<string, LogCategory>;
  const [confirmClear, setConfirmClear] = useState(false);
  const [newId, setNewId] = useState("");
  const [missing, setMissing] = useState<string[] | "loading" | null>(null);
  const eff: LogTaxonomy = useMemo(() => effective.data ?? { categories: {} }, [effective.data]);
  const effIds = useMemo(() => [...new Set([...(eff.order ?? []), ...Object.keys(eff.categories ?? {})])], [eff]);
  const customIds = Object.keys(overrides).filter((id) => !effIds.includes(id));
  const ids = [...effIds, ...customIds];

  const setTaxonomy = (cats: Record<string, LogCategory>) => {
    const keep = Object.fromEntries(Object.entries(cats).filter(([, c]) => Object.keys(c).length > 0));
    const prev = value.logs?.taxonomy ?? {};
    const next = Object.keys(keep).length === 0 && prev.order === undefined ? undefined : { ...prev, categories: keep };
    onChange({ ...value, logs: patchLogs(value.logs, { taxonomy: next }) } as WorkspaceSettings);
  };
  const setCat = (id: string, patch: Partial<Record<keyof LogCategory, unknown>>) => {
    const cur: Record<string, unknown> = { ...(overrides[id] ?? {}) };
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined || v === "" || v === null) delete cur[k];
      else cur[k] = v;
    }
    const cats = { ...overrides };
    if (Object.keys(cur).length === 0) delete cats[id];
    else cats[id] = cur as LogCategory;
    setTaxonomy(cats);
  };
  const addCategory = (id: string) => {
    const name = id.trim();
    if (name === "" || /\s/.test(name) || name.length > MAX_ID || ids.includes(name)) return;
    setTaxonomy({ ...overrides, [name]: { label: name } });
    setNewId("");
  };
  const idProblem = newId === "" ? null : /\s/.test(newId) || newId.length > MAX_ID ? t.settings.taxonomy.idInvalid : ids.includes(newId) ? t.settings.taxonomy.idDuplicate : null;

  const dimension = schema.data?.dimensions?.find((d) => d.id === FILTER_KEYS.category)?.id;
  const metric = schema.data?.metrics?.find((x) => x.unit === "count")?.id;
  // 펼칠 때 한 번만 데이터에서 찾는다(차원·지표 이름은 서버 목록에서 찾은 것)
  const loadMissing = () => {
    if (missing !== null || dimension === undefined || metric === undefined) return;
    setMissing("loading");
    rest
      .aggregateLogs({ group_by: [dimension], metric, filter: {} })
      .then((rows) => setMissing(rows.map((r) => r.keys?.[dimension]).filter((k): k is string => typeof k === "string" && !ids.includes(k))))
      .catch(() => setMissing([]));
  };

  if (effective.isPending && effective.fetchStatus !== "idle") return <Skeleton rows={4} />;
  const text = t.settings.taxonomy;
  const toneChoices = (cur: string | null | undefined) => (cur && !TONE_VOCABULARY.includes(cur) ? [...TONE_VOCABULARY, cur] : TONE_VOCABULARY);
  return (
    <div className="logs-taxonomy">
      <p className="app-muted">{text.description}</p>
      {effective.isError && Object.keys(eff.categories ?? {}).length === 0 ? <ErrorBlock title={text.loadFailed} retryLabel={m.common.retry} onRetry={() => void effective.refetch()} /> : null}
      {ids.length === 0 ? <p className="app-muted">{text.empty}</p> : (
        <div className="logs-taxonomy-scroll">
          <table className="logs-table" role="grid" aria-label={text.grid}>
            <thead>
              <tr>
                {(["id", "name", "description", "visible", "color", "tone", "preview", "state"] as const).map((c) => <th key={c} scope="col">{text.columns[c]}</th>)}
              </tr>
            </thead>
            <tbody>
              {ids.map((id) => {
                const o = overrides[id];
                const e = eff.categories?.[id];
                const custom = !effIds.includes(id);
                const visible = o?.visible ?? e?.visible ?? true;
                const tone = o?.tone ?? undefined;
                const label = o?.label?.trim() ? o.label : (e?.label ?? id);
                const rowErrors = (errors ?? []).filter((x) => x.path.startsWith(`/logs/taxonomy/categories/${id}`)).map((x) => x.message);
                return (
                  <tr key={id}>
                    <th scope="row"><code className="logs-mono">{id}</code></th>
                    <td>
                      <input className="logs-input" aria-label={`${id} ${text.columns.name}`} value={o?.label ?? ""} placeholder={e?.label ?? id} disabled={disabled} onChange={(ev) => setCat(id, { label: ev.target.value })} />
                      {o?.label === undefined && !custom ? <span className="logs-chip">{text.defaultBadge}</span> : null}
                    </td>
                    <td><input className="logs-input" aria-label={`${id} ${text.columns.description}`} title={o?.description ?? e?.description ?? ""} value={o?.description ?? ""} placeholder={e?.description ?? ""} disabled={disabled} onChange={(ev) => setCat(id, { description: ev.target.value })} /></td>
                    <td>
                      <label className="app-check"><input type="checkbox" checked={visible} disabled={disabled} aria-label={`${id} ${text.columns.visible}`} onChange={(ev) => setCat(id, { visible: ev.target.checked === (e?.visible ?? true) && !custom ? undefined : ev.target.checked })} />{visible ? "" : text.hidden}</label>
                    </td>
                    <td><ColorSlotPicker value={o?.color ?? e?.color ?? undefined} ariaLabel={`${id} ${text.colorLabel}`} onChange={(c) => setCat(id, { color: c })} /></td>
                    <td>
                      <select aria-label={`${id} ${text.toneLabel}`} value={tone ?? ""} disabled={disabled} onChange={(ev) => setCat(id, { tone: ev.target.value })}>
                        <option value="">{e?.tone ? `${text.toneDefault} (${text.toneNames[e.tone] ?? e.tone})` : text.toneDefault}</option>
                        {toneChoices(tone).map((tn) => <option key={tn} value={tn}>{text.toneNames[tn] ?? `${tn} — ${text.toneUnknown}`}</option>)}
                      </select>
                    </td>
                    <td><span className="logs-chip"><span className="logs-dot" aria-hidden="true" style={{ background: mergedColor(id, o?.color ?? e?.color) }} />{label}</span></td>
                    <td>
                      {custom ? (
                        <Button size="sm" disabled={disabled} onClick={() => setCat(id, { label: null, description: null, visible: null, color: null, tone: null })}>{text.deleteRow}</Button>
                      ) : o !== undefined ? (
                        <>
                          <span className="logs-chip">{text.specifiedBadge}</span>
                          <Button size="sm" variant="ghost" disabled={disabled} aria-label={`${id} ${text.resetRow}`} onClick={() => setCat(id, { label: null, description: null, visible: null, color: null, tone: null })}>↺</Button>
                        </>
                      ) : <span className="logs-chip">{text.defaultBadge}</span>}
                      {rowErrors.map((msg, i) => <p key={i} className="app-field-error" role="alert">{msg}</p>)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="logs-taxonomy-add">
        <input className="logs-input" aria-label={text.newId} placeholder={text.newId} value={newId} maxLength={MAX_ID + 8} disabled={disabled} onChange={(e) => setNewId(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); addCategory(newId); } }} />
        <Button size="sm" disabled={disabled || newId.trim() === "" || idProblem !== null} onClick={() => addCategory(newId)}>{text.addCategory}</Button>
        {idProblem ? <span className="app-field-error" role="alert">{idProblem}</span> : null}
        <Button size="sm" disabled={disabled || Object.keys(overrides).length === 0} onClick={() => setConfirmClear(true)}>{text.clearAll}</Button>
      </div>
      <p className="app-muted logs-note">{text.emptyNote}</p>
      {dimension !== undefined && metric !== undefined ? (
        <Disclosure summary={text.missingTitle} onOpenChange={(o) => o && loadMissing()}>
          {missing === "loading" ? <p className="app-muted">{text.missingLoading}</p> : Array.isArray(missing) && missing.length > 0 ? (
            <ul className="logs-chiplist">
              {missing.map((id) => (
                <li key={id}><span className="logs-chip">{id}</span> <Button size="sm" disabled={disabled} onClick={() => { addCategory(id); setMissing(missing.filter((x) => x !== id)); }}>{text.missingAdd}</Button></li>
              ))}
            </ul>
          ) : <p className="app-muted">{text.missingNone}</p>}
        </Disclosure>
      ) : null}
      <ConfirmDialog open={confirmClear} title={text.clearTitle} confirmLabel={text.clearConfirm} cancelLabel={m.common.cancel} danger onConfirm={() => { onChange({ ...value, logs: patchLogs(value.logs, { taxonomy: undefined }) } as WorkspaceSettings); setConfirmClear(false); }} onCancel={() => setConfirmClear(false)}>
        {text.clearBody}
      </ConfirmDialog>
    </div>
  );
}
