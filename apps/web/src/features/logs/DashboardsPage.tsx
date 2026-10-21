import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { Banner, Button, ConfirmDialog, Dialog, useShortcuts, useToast } from "@agent-console/ui";
import { DashboardGrid, TemplatePicker, builtinWidgets, createWidgetRegistry, updateWidget, type DashboardChangeMeta, type TemplateApplyRequest } from "@agent-console/log-view";
import type { LogDashboard, LogWidget, WorkspaceSettings } from "@agent-console/contracts";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { messages as appMessages } from "../../app/messages";
import { queryKeys } from "../../app/queries";
import { DOCUMENT_REQUIRES } from "../../app/requirements";
import { useStorage } from "../../app/StorageContext";
import { ConflictBanner } from "../../definition/ConflictBanner";
import { SaveStatus } from "../../definition/SaveStatus";
import { UnsavedGuard } from "../../definition/unsaved";
import { useDefinitionEditor } from "../../definition/useDefinitionEditor";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { useRequires } from "../../modules";
import { JsonView } from "./JsonView";
import { LogMenu, type LogMenuItem } from "./LogMenu";
import { LogsPageFrame } from "./LogsPageFrame";
import { RangeControl } from "./LogFilters";
import { useLogsIngested } from "./LogsLive";
import { WidgetEditorDrawer } from "./WidgetEditorDrawer";
import { DASHBOARD_COLUMNS, LOGS_LIMITS, LOGS_SCOPES, LOGS_STORAGE, SCREEN_PARAMS } from "./logsConfig";
import { cloneWidgets, dashboardsOf, enabledCount, isTypingTarget, newDashboardId, parseRange, rangeToWindow, uniqueTitle, unknownKindCount, withDashboards } from "./logsLib";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { settingsLogsHref } from "./LogsEmpty";
import { useFilterOptions } from "./useFilterOptions";
import { useLogUrlState } from "./useLogFilterState";
import { useLogSchema, useLogSources, useLogTaxonomyView, useLogTemplates } from "./useLogsApi";
import { useWidgetResults } from "./useWidgetResults";
import { buildFilterFields } from "./LogFilters";

const FIELDS = buildFilterFields();
const REGISTRY = createWidgetRegistry(builtinWidgets);
const TEMPLATE_FORM_ID = "dashboard-template-form";
const NO_WIDGETS: readonly LogWidget[] = [];

function makeId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
function browserTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}
/** 새 위젯의 시작값: 종류는 레지스트리 첫 항목, 지표는 서버 목록 첫 항목(없으면 빈 값 → 자유 입력). */
function blankWidget(kind: string, metric: string): LogWidget {
  return { id: makeId(), kind, query: { group_by: [], metric, filter: {} }, options: {} };
}

/** 대시보드(`/logs/dashboards/:id?`): 설정 `logs.dashboards`를 읽어 위젯 격자로 그리고, 편집은 로컬 복사본에 쌓았다가 [저장]에서만 설정 문서에 병합 저장한다. */
export function DashboardsPage() {
  const { id: idParam } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const storage = useStorage();
  const url = useLogUrlState(FIELDS);
  const docPhase = useRequires(DOCUMENT_REQUIRES).phase;
  const editor = useDefinitionEditor<WorkspaceSettings>({
    enabled: docPhase === "met",
    queryKey: queryKeys.settings(),
    load: (rest) => rest.getSettingsVersioned(),
    save: (rest, value, hash) => rest.putSettingsVersioned(value, hash),
  });
  const sources = useLogSources();
  const taxonomy = useLogTaxonomyView();
  const schema = useLogSchema();
  const [editing, setEditing] = useState(false);
  const [auto, setAuto] = useState(() => storage.get(LOGS_STORAGE.autoRefresh) === "1");
  const [anchor, setAnchor] = useState(() => Date.now());
  const [menu, setMenu] = useState<{ anchor: { x: number; y: number; element?: HTMLElement | undefined } } | null>(null);
  const [newMenu, setNewMenu] = useState<{ x: number; y: number; element?: HTMLElement | undefined } | null>(null);
  const [panel, setPanel] = useState<{ widget: LogWidget; isNew: boolean } | undefined>();
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [jsonOpen, setJsonOpen] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmTemplate, setConfirmTemplate] = useState<TemplateApplyRequest | null>(null);
  const [jsonEdit, setJsonEdit] = useState<LogWidget | null>(null);
  const [jsonText, setJsonText] = useState("");
  const deleted = useRef<{ dashboardId: string; widget: LogWidget; index: number }[]>([]);
  const pendingCopy = useRef<LogDashboard | null>(null);
  const narrow = useMediaQuery(`(max-width: ${DASHBOARD_COLUMNS.narrowBelow - 1}px)`);
  const tz = useMemo(() => browserTz(), []);

  const dashboards = dashboardsOf(editor.draft);
  const rangeValue = url.screen[SCREEN_PARAMS.range]?.[0];
  const window = useMemo(() => (rangeValue === undefined ? null : rangeToWindow(parseRange(rangeValue, "7d"), anchor)), [rangeValue, anchor]);

  // 현재 대시보드: 주소 id → 마지막에 본 id → 첫 대시보드
  const current = idParam === undefined ? undefined : dashboards.find((d) => d.id === idParam);
  const lastId = storage.get(LOGS_STORAGE.lastDashboard);
  useEffect(() => {
    if (current !== undefined) storage.set(LOGS_STORAGE.lastDashboard, current.id);
  }, [current, storage]);

  const ownedKeys = useCallback((kind: string) => Object.keys(((REGISTRY.get(kind)?.optionsSchema["properties"] ?? {}) as Record<string, unknown>)), []);
  const commit = useCallback(
    (next: readonly LogDashboard[]) => editor.setDraft((cur) => withDashboards(cur, next, { prev: editor.base?.logs?.dashboards ?? [], ownedOptionKeys: ownedKeys })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editor.setDraft, editor.base, ownedKeys],
  );
  const setWidgets = (id: string, widgets: readonly LogWidget[]) => commit(dashboards.map((d) => (d.id === id ? { ...d, widgets: [...widgets] } : d)));

  const results = useWidgetResults({ widgets: current?.widgets ?? NO_WIDGETS, registry: REGISTRY, window, tz, paused: false });
  useLogsIngested(() => results.refreshAll(), LOGS_LIMITS.dashboardDebounceMs, auto && !editing);
  const options = useFilterOptions(taxonomy, []);
  const templates = useLogTemplates(templatesOpen);

  // ---- 편집 동작
  const startEdit = () => setEditing(true);
  const finishEdit = () => {
    if (editor.dirty) setConfirmCancel(true);
    else setEditing(false);
  };
  const cancelEdit = () => {
    editor.revert();
    deleted.current = [];
    setEditing(false);
    setConfirmCancel(false);
  };
  const save = useCallback(async () => {
    const ok = await editor.save();
    if (ok) {
      toast({ tone: "success", text: t.dashboards.savedToast });
      setEditing(false);
    }
  }, [editor, toast]);
  const goto = (id: string) => void navigate(`/logs/dashboards/${encodeURIComponent(id)}`);
  const addDashboard = (d: LogDashboard) => {
    commit([...dashboards, d]);
    setEditing(true);
    goto(d.id);
  };
  const createBlank = () => addDashboard({ id: newDashboardId(dashboards, makeId), title: uniqueTitle(t.dashboards.newName, dashboards.map((d) => d.title), t.dashboards.numbered), widgets: [] });
  const openAdd = () => {
    if (current === undefined) return;
    const kind = [...REGISTRY.keys()][0] ?? "";
    setEditing(true);
    setPanel({ widget: blankWidget(kind, schema.data?.metrics?.[0]?.id ?? ""), isNew: true });
  };
  const onGridChange = (next: LogWidget[], meta: DashboardChangeMeta) => {
    if (current === undefined) return;
    if (meta.reason === "remove") {
      const idx = (current.widgets ?? []).findIndex((w) => w.id === meta.id);
      const widget = (current.widgets ?? [])[idx];
      if (widget !== undefined) {
        deleted.current = [...deleted.current, { dashboardId: current.id, widget, index: idx }].slice(-LOGS_LIMITS.deleteHistory);
        toast({ tone: "info", text: t.dashboards.removedToast, durationMs: LOGS_LIMITS.deleteToastMs, action: { label: t.dashboards.undo, onClick: undoDelete } });
      }
    }
    setWidgets(current.id, next);
  };
  const undoDelete = useCallback(() => {
    const last = deleted.current.pop();
    if (last === undefined) return;
    const target = dashboards.find((d) => d.id === last.dashboardId);
    if (target === undefined) return;
    const widgets = [...(target.widgets ?? [])];
    widgets.splice(Math.min(last.index, widgets.length), 0, last.widget);
    commit(dashboards.map((d) => (d.id === target.id ? { ...d, widgets } : d)));
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-widget-id="${CSS.escape(last.widget.id)}"]`)?.focus());
  }, [dashboards, commit]);
  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z" && !isTypingTarget(e.target)) {
        e.preventDefault();
        undoDelete();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [editing, undoDelete]);

  const applyWidget = (w: LogWidget) => {
    if (current === undefined || panel === undefined) return;
    const list = current.widgets ?? [];
    const exists = list.some((x) => x.id === w.id);
    setWidgets(current.id, exists ? list.map((x) => (x.id === w.id ? w : x)) : [...list, w]);
    setPanel(undefined);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-widget-id="${CSS.escape(w.id)}"]`)?.focus());
  };
  const applyTemplate = (req: TemplateApplyRequest) => {
    const tpl = (templates.data ?? []).find((x) => x.id === req.templateId);
    if (tpl === undefined) return;
    if (req.mode === "new") {
      addDashboard({ id: newDashboardId(dashboards, makeId), title: uniqueTitle(req.title?.trim() || tpl.title, dashboards.map((d) => d.title), t.dashboards.numbered), widgets: cloneWidgets(tpl.widgets ?? [], makeId) });
    } else if (current !== undefined) {
      setWidgets(current.id, [...(current.widgets ?? []), ...cloneWidgets(tpl.widgets ?? [], makeId)]);
      setEditing(true);
    }
    setTemplatesOpen(false);
    setConfirmTemplate(null);
  };
  const requestTemplate = (req: TemplateApplyRequest) => (editor.dirty ? setConfirmTemplate(req) : applyTemplate(req));

  // ---- 사본으로 저장(충돌 해결): 서버 버전을 다시 읽은 뒤 내 대시보드를 새 대시보드로 얹는다. 저장은 사용자가 한다.
  const saveCopy = async () => {
    if (current === undefined) return;
    pendingCopy.current = { ...structuredClone(current), id: makeId(), title: t.dashboards.copyOf(current.title) };
    await editor.loadServerVersion();
  };
  useEffect(() => {
    const copy = pendingCopy.current;
    if (copy !== null && editor.status === "ready" && editor.conflict === null && !editor.dirty) {
      pendingCopy.current = null;
      commit([...dashboardsOf(editor.draft), copy]);
      setEditing(true);
      goto(copy.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor.status, editor.conflict, editor.dirty, editor.base]);

  const widgetsNow = current?.widgets ?? NO_WIDGETS;
  const idx = current === undefined ? -1 : dashboards.findIndex((d) => d.id === current.id);
  useShortcuts([
    { id: "logs.d.edit", scope: LOGS_SCOPES.dashboard, keys: "e", titleKey: "shortcuts.logsEditToggle", run: () => (editing ? finishEdit() : startEdit()) },
    { id: "logs.d.add", scope: LOGS_SCOPES.dashboard, keys: "n", titleKey: "shortcuts.logsAddWidget", run: openAdd },
    { id: "logs.d.refresh", scope: LOGS_SCOPES.dashboard, keys: "r", titleKey: "shortcuts.logsRefresh", run: results.refreshAll },
    { id: "logs.d.prev", scope: LOGS_SCOPES.dashboard, keys: "[", titleKey: "shortcuts.logsPrevDashboard", run: () => idx > 0 && goto(dashboards[idx - 1]?.id ?? "") },
    { id: "logs.d.next", scope: LOGS_SCOPES.dashboard, keys: "]", titleKey: "shortcuts.logsNextDashboard", run: () => idx >= 0 && idx < dashboards.length - 1 && goto(dashboards[idx + 1]?.id ?? "") },
    { id: "logs.d.save", scope: LOGS_SCOPES.dashboard, keys: "Mod+S", titleKey: "shortcuts.save", modifierRequired: true, run: () => editing && void save() },
  ]);

  // ---- 화면 상태
  const headerActions = (
    <>
      <Button size="sm" onClick={() => { setAnchor(Date.now()); results.refreshAll(); }}>{t.dashboards.refresh} ⟳</Button>
    </>
  );
  if (docPhase === "unmet" || editor.status === "error") {
    const v = describeError(editor.error, t.dashboards.loadSettingsFailed);
    return (
      <LogsPageFrame tab="dashboards">
        <ErrorBlock title={t.dashboards.loadSettingsFailed} message={v.message} retryLabel={appMessages.common.retry} onRetry={editor.reload} />
      </LogsPageFrame>
    );
  }
  if (editor.status === "loading") {
    return (
      <LogsPageFrame tab="dashboards">
        <div className="logs-dash-skeleton" role="status" aria-busy="true" aria-label={t.loading}>
          {[0, 1, 2].map((i) => <div key={i} className="app-skeleton-row" style={{ height: 120 }} />)}
        </div>
      </LogsPageFrame>
    );
  }
  if (idParam === undefined && dashboards.length > 0) {
    const target = dashboards.find((d) => d.id === lastId) ?? dashboards[0];
    return <Navigate to={`/logs/dashboards/${encodeURIComponent(target?.id ?? "")}`} replace />;
  }

  const toolbar = (
    <div className="logs-dashtools" role="toolbar" aria-label={t.dashboards.title}>
      {dashboards.length > 0 ? (
        <label className="logs-range-label">
          <span>{t.dashboards.select}</span>
          <select value={current?.id ?? ""} onChange={(e) => goto(e.target.value)}>
            {current === undefined ? <option value="" /> : null}
            {dashboards.map((d) => (
              <option key={d.id} value={d.id}>{d.title || t.dashboards.untitled}</option>
            ))}
          </select>
        </label>
      ) : null}
      <RangeControl value={rangeValue} fallbackId="7d" settingsOption={t.dashboards.rangeSettings} onChange={(v) => url.setScreen({ [SCREEN_PARAMS.range]: v === "" ? null : v })} label={t.dashboards.range} />
      {rangeValue !== undefined ? (
        <span className="logs-chip">
          {t.dashboards.rangeOverride(t.filters.rangeNames[rangeValue] ?? rangeValue)}
          <button type="button" className="logs-chipx" aria-label={t.dashboards.clearOverride} onClick={() => url.setScreen({ [SCREEN_PARAMS.range]: null })}>×</button>
        </span>
      ) : null}
      <span className="app-muted">{t.dashboards.timezone(tz)}</span>
      <label className="app-check">
        <input type="checkbox" checked={auto} disabled={editing} onChange={(e) => { setAuto(e.target.checked); storage.set(LOGS_STORAGE.autoRefresh, e.target.checked ? "1" : "0"); }} />
        {t.dashboards.auto}
      </label>
      <span className="logs-spacer" />
      {editing ? (
        <>
          <SaveStatus dirty={editor.dirty} phase={editor.savePhase} onRetry={() => void save()} />
          <Button size="sm" onClick={finishEdit}>{t.dashboards.cancel}</Button>
          <Button size="sm" variant="primary" loading={editor.savePhase === "saving"} disabled={!editor.dirty || editor.conflict !== null} title={t.dashboards.saveShortcut} onClick={() => void save()}>{t.dashboards.save}</Button>
        </>
      ) : (
        <>
          {current !== undefined ? <Button size="sm" onClick={startEdit}>{t.dashboards.edit}</Button> : null}
        </>
      )}
      <Button
        size="sm"
        aria-haspopup="menu"
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setNewMenu({ x: r.left, y: r.bottom, element: e.currentTarget });
        }}
      >
        + {t.dashboards.create} ▾
      </Button>
      {current !== undefined ? (
        <Button size="sm" aria-haspopup="menu" aria-label={t.dashboards.more} onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setMenu({ anchor: { x: r.left, y: r.bottom, element: e.currentTarget } }); }}>⋯</Button>
      ) : null}
    </div>
  );

  const moreItems: LogMenuItem[] = current === undefined ? [] : [
    { id: "rename", label: t.dashboards.rename, onSelect: () => setRenaming(current.title) },
    { id: "dup", label: t.dashboards.duplicate, onSelect: () => addDashboard({ ...structuredClone(current), id: newDashboardId(dashboards, makeId), title: uniqueTitle(t.dashboards.copyOf(current.title), dashboards.map((d) => d.title), t.dashboards.numbered), widgets: cloneWidgets(current.widgets ?? [], makeId) }) },
    { id: "delete", label: t.dashboards.remove, onSelect: () => setConfirmDelete(true) },
    { id: "json", label: t.dashboards.viewJson, onSelect: () => setJsonOpen(true) },
  ];
  const newItems: LogMenuItem[] = [
    { id: "blank", label: t.dashboards.createBlank, onSelect: createBlank },
    { id: "tpl", label: t.dashboards.createFromTemplate, onSelect: () => setTemplatesOpen(true) },
  ];

  let body;
  if (dashboards.length === 0) {
    body = (
      <div className="logs-empty" data-testid="logs-dash-empty">
        <h2 className="app-block-title">{t.dashboards.emptyTitle}</h2>
        <p>{t.dashboards.emptyBody}</p>
        <div className="logs-empty-actions">
          <Button variant="primary" onClick={() => setTemplatesOpen(true)}>{t.dashboards.emptyFromTemplate}</Button>
          <Button onClick={createBlank}>{t.dashboards.emptyBlank}</Button>
        </div>
        {sources.data !== undefined && enabledCount(sources.data) === 0 ? <Banner tone="info">{t.dashboards.noSourcesNote} <Link to={settingsLogsHref()}>{t.dashboards.noSourcesAction}</Link></Banner> : null}
      </div>
    );
  } else if (current === undefined) {
    body = (
      <div className="logs-empty" role="alert">
        <h2 className="app-block-title">{t.dashboards.notFoundTitle}</h2>
        <Link className="logs-linkbtn" to={`/logs/dashboards/${encodeURIComponent(dashboards[0]?.id ?? "")}`}>{t.dashboards.toList}</Link>
      </div>
    );
  } else {
    const addCard = (
      <button type="button" className="logs-addwidget" onClick={openAdd} aria-label={t.dashboards.addWidgetLabel}>{t.dashboards.addWidget}</button>
    );
    body = (
      <>
        {widgetsNow.length === 0 ? (
          <p className="app-muted logs-widgets-empty">
            {t.dashboards.widgetsEmpty} <Button size="sm" onClick={() => setTemplatesOpen(true)}>{t.dashboards.emptyFromTemplate}</Button>
          </p>
        ) : null}
        <DashboardGrid
          widgets={widgetsNow}
          registry={REGISTRY}
          results={results.results}
          editing={editing}
          onChange={onGridChange}
          onEditWidget={(id) => {
            const w = widgetsNow.find((x) => x.id === id);
            if (w !== undefined) setPanel({ widget: structuredClone(w), isNew: false });
          }}
          onRefreshWidget={results.refresh}
          onVisible={results.onVisible}
          onEditWidgetJson={(w) => { setJsonEdit(w); setJsonText(JSON.stringify(w, null, 2)); }}
          columns={narrow ? DASHBOARD_COLUMNS.narrow : DASHBOARD_COLUMNS.wide}
          metrics={schema.data?.metrics ?? []}
          dimensions={schema.data?.dimensions ?? []}
          newId={makeId}
          slotFor={slotFor}
          addCard={editing || widgetsNow.length === 0 ? addCard : undefined}
          ariaLabel={current.title || t.dashboards.untitled}
        />
      </>
    );
  }

  let jsonParseError: string | null = null;
  let jsonObject: LogWidget | null = null;
  if (jsonEdit !== null) {
    try {
      const parsed: unknown = JSON.parse(jsonText);
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) jsonObject = parsed as LogWidget;
      else jsonParseError = t.dashboards.jsonInvalid;
    } catch (e) {
      jsonParseError = t.dashboards.jsonParseError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <LogsPageFrame tab="dashboards" actions={headerActions}>
      <UnsavedGuard dirty={editor.dirty} />
      {editor.conflict === null ? null : (
        <ConflictBanner details={editor.conflict} busy={editor.savePhase === "saving"} onLoadServer={() => void editor.loadServerVersion()} onSaveCopy={() => void saveCopy()} onOverwrite={() => void editor.overwrite()} />
      )}
      {editor.saveError !== null && editor.fieldErrors.length === 0 ? <Banner tone="danger">{editor.saveError}</Banner> : null}
      {toolbar}
      <div className="logs-dash-body" data-editing={editing ? "true" : undefined}>{body}</div>

      {menu === null ? null : <LogMenu label={t.dashboards.more} anchor={menu.anchor} items={moreItems} onClose={() => setMenu(null)} />}
      {newMenu === null ? null : <LogMenu label={t.dashboards.create} anchor={newMenu} items={newItems} onClose={() => setNewMenu(null)} />}

      {panel === undefined ? null : (
        <WidgetEditorDrawer
          key={panel.widget.id}
          initial={panel.widget}
          isNew={panel.isNew}
          registry={REGISTRY}
          dimensions={schema.data?.dimensions}
          metrics={schema.data?.metrics}
          filterOptions={options}
          tz={tz}
          onApply={applyWidget}
          onCancel={() => setPanel(undefined)}
        />
      )}

      <Dialog
        open={templatesOpen}
        title={t.dashboards.createFromTemplate}
        onClose={() => setTemplatesOpen(false)}
        size="lg"
        actions={
          <>
            <Button onClick={() => setTemplatesOpen(false)}>{appMessages.common.cancel}</Button>
            {(templates.data ?? []).length > 0 ? (
              <Button variant="primary" type="submit" form={TEMPLATE_FORM_ID}>
                {t.dashboards.templateApply}
              </Button>
            ) : null}
          </>
        }
      >
        <TemplatePicker
          formId={TEMPLATE_FORM_ID}
          showActions={false}
          templates={templates.data ?? []}
          canAppend={current !== undefined}
          unknownKinds={(d) => unknownKindCount(d, (k) => REGISTRY.has(k))}
          onApply={requestTemplate}
          onCreateBlank={() => { setTemplatesOpen(false); createBlank(); }}
        />
      </Dialog>
      <ConfirmDialog open={confirmTemplate !== null} title={t.dashboards.templateUnsavedTitle} confirmLabel={t.dashboards.templateUnsavedConfirm} cancelLabel={appMessages.common.cancel} onConfirm={() => confirmTemplate && applyTemplate(confirmTemplate)} onCancel={() => setConfirmTemplate(null)}>
        {t.dashboards.templateUnsavedBody}
      </ConfirmDialog>
      <ConfirmDialog open={confirmCancel} title={t.dashboards.discardTitle} confirmLabel={t.dashboards.discardConfirm} cancelLabel={t.dashboards.keepEditing} danger onConfirm={cancelEdit} onCancel={() => setConfirmCancel(false)}>
        {t.dashboards.discardBody}
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmDelete}
        title={t.dashboards.deleteTitle(current?.title ?? "")}
        confirmLabel={t.dashboards.deleteConfirm}
        cancelLabel={appMessages.common.cancel}
        danger
        onConfirm={() => {
          if (current !== undefined) {
            const rest = dashboards.filter((d) => d.id !== current.id);
            commit(rest);
            setEditing(true);
            setConfirmDelete(false);
            goto(rest[0]?.id ?? "");
            if (rest.length === 0) void navigate("/logs/dashboards", { replace: true });
          }
        }}
        onCancel={() => setConfirmDelete(false)}
      >
        {t.dashboards.deleteBody}
      </ConfirmDialog>
      <Dialog
        open={renaming !== null}
        title={t.dashboards.rename}
        onClose={() => setRenaming(null)}
        actions={
          <>
            <Button onClick={() => setRenaming(null)}>{appMessages.common.cancel}</Button>
            <Button variant="primary" onClick={() => { if (current !== undefined && renaming !== null) { commit(dashboards.map((d) => (d.id === current.id ? { ...d, title: renaming.trim() || t.dashboards.untitled } : d))); setEditing(true); } setRenaming(null); }}>{t.dashboards.save}</Button>
          </>
        }
      >
        <RenameInput value={renaming ?? ""} onChange={setRenaming} />
      </Dialog>
      <Dialog open={jsonOpen} title={t.dashboards.jsonTitle} onClose={() => setJsonOpen(false)} wide>
        <JsonView value={current} label={t.dashboards.jsonTitle} height={420} />
      </Dialog>
      <Dialog
        open={jsonEdit !== null}
        title={t.dashboards.unknownWidgetJson}
        onClose={() => setJsonEdit(null)}
        wide
        actions={
          <>
            <Button onClick={() => setJsonEdit(null)}>{appMessages.common.cancel}</Button>
            <Button
              variant="primary"
              disabled={jsonObject === null}
              onClick={() => {
                if (jsonEdit !== null && jsonObject !== null && current !== undefined) {
                  setWidgets(current.id, updateWidget(current.widgets ?? [], jsonEdit.id, () => ({ ...jsonObject, id: jsonEdit.id })));
                  setJsonEdit(null);
                }
              }}
            >
              {t.dashboards.jsonApply}
            </Button>
          </>
        }
      >
        <textarea className="logs-jsonedit" data-ac-editable aria-label={t.dashboards.unknownWidgetJson} value={jsonText} onChange={(e) => setJsonText(e.target.value)} spellCheck={false} />
        <p className="app-muted" role="status">{jsonParseError ?? ""}</p>
      </Dialog>
    </LogsPageFrame>
  );
}

function RenameInput({ value, onChange }: { value: string; onChange(v: string): void }) {
  const [composing, setComposing] = useState(false);
  return (
    <input
      className="logs-input"
      aria-label={t.dashboards.titleField}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onCompositionStart={() => setComposing(true)}
      onCompositionEnd={() => setComposing(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && composing) e.stopPropagation();
      }}
    />
  );
}
