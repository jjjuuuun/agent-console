/**
 * 메모리 화면(컨테이너): 범위 나무 | 항목 표 | 상세 편집기 3칸(본문 폭 1180 미만이면 나무가 [범위 ▾] 팝오버가 되는 2칸).
 * 선택·필터는 주소가 진실이다(`memoryUrl`). 데이터는 `useMemoryApi`, 실시간은 `useMemoryLive`, 그림은 `@agent-console/memory-view`가 맡고
 * 이 파일은 그것들을 잇는 얇은 조립이다. 범위 종류·범위 이름·도구 이름은 코드에 없다(서버 데이터).
 */
import "@agent-console/memory-view/styles.css";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Banner, Button, ChipRow, EmptyState, Icon, IconButton, Menu, PageHeader, Popover, Spinner, type ChipItem, type MenuItemDef } from "@agent-console/ui";
import type { MemoryEntry, MemoryEntrySummary, MemoryScopeRef } from "@agent-console/contracts/memory";
import {
  MemoryEntryTable,
  MemoryScopeTree,
  sameScope,
  scopeKey,
  scopeLabel,
  visibleScopes,
  type ScopeLabel,
} from "@agent-console/memory-view";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { queryKeys, useApiQuery } from "../../app/queries";
import { useStorage } from "../../app/StorageContext";
import { usePageTitle } from "../../shell/titles";
import { ROUTE_ROLES, routeIconNode, routePath, useRouteOn } from "../library";
import { useProjects } from "../projects";
import { ClearScopeDialog, PurgeDialog } from "./PurgeDialogs";
import { EntryDetail, type EntryDetailHandle } from "./EntryDetail";
import { HistoryDialog } from "./HistoryDialog";
import { ImportDialog } from "./ImportDialog";
import { MoveDialog } from "./MoveDialog";
import { NewEntryForm } from "./NewEntryForm";
import { FloatingMenu, PaneSeparator, ScopeSummaryPanel } from "./MemoryParts";
import { MemoryToolbar } from "./MemoryToolbar";
import { IMPORTED_AUTHOR_KIND, MEMORY_LIMITS, MEMORY_STORAGE, SETTINGS_SECTION, SORT_KEYS_BY_COLUMN, WARNING_CODES, WARNING_PREFIX } from "./memoryConfig";
import { hasFilters, parseView, scopeParam, writeView, type MemoryViewState } from "./memoryUrl";
import { memoryMessages as t } from "./messages";
import { useContainerWidth } from "./useContainerWidth";
import { useLeaveGuard } from "./useLeaveGuard";
import { useMemoryActions } from "./useMemoryActions";
import { useMemoryContext } from "./useMemoryContext";
import { memoryKeys, useInvalidateMemory, useMemoryEntries, useMemoryKinds, useMemoryLimits, useMemoryScopes } from "./useMemoryApi";
import { useMemoryLive } from "./useMemoryLive";
import "./memory.css";

type Dlg =
  | { kind: "move"; entry: MemoryEntry | MemoryEntrySummary; dirty: boolean }
  | { kind: "history"; entry: MemoryEntry | MemoryEntrySummary; dirty: boolean }
  | { kind: "purge"; entry: MemoryEntry | MemoryEntrySummary }
  | { kind: "clear"; scope: MemoryScopeRef }
  | { kind: "import" };

export interface MemoryPageProps {
  /** 본문 폭을 직접 정한다(레이아웃이 없는 환경·테스트). 생략하면 컨테이너 폭을 관찰한다 */
  layoutWidth?: number;
}

const FALLBACK_WIDTH = 1220;
const readWidth = (raw: string | null, spec: { def: number; min: number; max: number }) => {
  const n = Number(raw);
  return Number.isFinite(n) && n >= spec.min && n <= spec.max ? n : spec.def;
};
const isEditable = (el: EventTarget | null): boolean => el instanceof HTMLElement && (el.closest("input, textarea, select, [contenteditable='true'], [data-ac-editable]") !== null);

export function MemoryPage({ layoutWidth }: MemoryPageProps) {
  usePageTitle(t.title);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const view = useMemo(() => parseView(params), [params]);
  const qc = useQueryClient();
  const storage = useStorage();
  const projects = useProjects();
  const ctx = useMemoryContext();
  const limits = useMemoryLimits();
  const actions = useMemoryActions();
  const invalidate = useInvalidateMemory();
  const runsOn = useRouteOn(ROUTE_ROLES.runs);

  const kindsQ = useMemoryKinds();
  const scopesQ = useMemoryScopes();
  const entries = useMemoryEntries(view, view.q);
  const kinds = useMemo(() => kindsQ.data?.kinds ?? [], [kindsQ.data]);
  const allScopes = useMemo(() => scopesQ.data ?? [], [scopesQ.data]);
  const info = useApiQuery(queryKeys.descriptors("server-info"), (rest) => rest.getServerInfo(), { retry: false, meta: { silentBackgroundError: true } });
  const warnings = (info.data?.warnings ?? []).filter((w) => w.code.startsWith(WARNING_PREFIX));

  // ---- 칸 배치 --------------------------------------------------------------------------------
  const bodyRef = useRef<HTMLDivElement>(null);
  const measured = useContainerWidth(bodyRef, FALLBACK_WIDTH);
  const width = layoutWidth ?? measured;
  const threeCols = width >= MEMORY_LIMITS.threeColumnMinWidth;
  const [treeWidth, setTreeWidth] = useState(() => readWidth(storage.get(MEMORY_STORAGE.treeWidth), MEMORY_LIMITS.tree));
  const [detailWidth, setDetailWidth] = useState(() => readWidth(storage.get(MEMORY_STORAGE.detailWidth), MEMORY_LIMITS.detail));
  const [openKinds, setOpenKinds] = useState<string[] | undefined>(() => {
    try {
      const raw = storage.get(MEMORY_STORAGE.treeOpen);
      const parsed: unknown = raw === null ? undefined : JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : undefined;
    } catch {
      return undefined;
    }
  });

  // ---- 이름·라벨 ------------------------------------------------------------------------------
  const kindOf = useCallback((kind: string) => kinds.find((k) => k.kind === kind), [kinds]);
  const unknownScopes = useMemo(() => new Set(allScopes.filter((s) => s.kind_known === false).map((s) => scopeKey(s.scope))), [allScopes]);
  const isUnknown = useCallback((scope: MemoryScopeRef) => kindOf(scope.kind) === undefined || unknownScopes.has(scopeKey(scope)), [kindOf, unknownScopes]);
  const labelFor = useCallback(
    (scope: MemoryScopeRef): ScopeLabel => scopeLabel(scope, kindOf(scope.kind), ctx.resolvers, !isUnknown(scope)),
    [kindOf, ctx.resolvers, isUnknown],
  );
  const labelText = useCallback((scope: MemoryScopeRef) => labelFor(scope).text, [labelFor]);

  const [showAllScopes, setShowAllScopes] = useState(false);
  const filtered = useMemo(() => visibleScopes(allScopes, kinds, ctx.project, ctx.graphIds), [allScopes, kinds, ctx.project, ctx.graphIds]);
  const treeScopes = showAllScopes ? allScopes : filtered.visible;
  const hiddenCount = showAllScopes ? 0 : filtered.hidden.length;

  // ---- 주소 상태 ------------------------------------------------------------------------------
  const [pendingChanges, setPendingChanges] = useState(0);
  const scroller = () => document.querySelector<HTMLElement>(".mem-frame .ac-mem-table-scroll");
  const toTop = useCallback(() => document.querySelector<HTMLElement>(".mem-frame .ac-mem-table-scroll")?.scrollTo({ top: 0 }), []);
  const update = useCallback(
    (patch: Partial<MemoryViewState>, replace = true) => {
      setParams((prev) => writeView(prev, { ...parseView(prev), ...patch }), { replace });
    },
    [setParams],
  );
  /** 필터·범위·정렬이 바뀌면 표를 맨 위로(선택한 항목은 유지) */
  const change = useCallback(
    (patch: Partial<MemoryViewState>) => {
      update(patch);
      setPendingChanges(0);
      queueMicrotask(toTop);
    },
    [update, toTop],
  );

  // ---- 저장 안 된 변경 보호 -------------------------------------------------------------------
  const detailRef = useRef<EntryDetailHandle>(null);
  const [detailDirty, setDetailDirty] = useState(false);
  const [newDirty, setNewDirty] = useState(false);
  const [creating, setCreating] = useState<{ scope: MemoryScopeRef | null; content: string } | null>(null);
  const dirty = detailDirty || (creating !== null && newDirty);
  const { guard, dialog: leaveDialog } = useLeaveGuard(
    dirty,
    creating === null ? () => detailRef.current?.save() ?? Promise.resolve(false) : undefined,
    () => {
      detailRef.current?.discard();
      setNewDirty(false);
    },
  );

  const focusEditorSoon = () => {
    let tries = 0;
    const timer = setInterval(() => {
      const el = document.querySelector<HTMLElement>(".mem-detail .cm-content");
      tries += 1;
      if (el !== null) {
        el.focus();
        clearInterval(timer);
      } else if (tries > 30) clearInterval(timer);
    }, 50);
  };
  const openEntry = (id: string | null, focusEditor = false) => {
    if (id === view.entry && creating === null) {
      if (focusEditor) focusEditorSoon();
      return;
    }
    guard(() => {
      setCreating(null);
      setNewDirty(false);
      update({ entry: id }, false);
      if (focusEditor) focusEditorSoon();
    });
  };
  const startCreate = (scope?: MemoryScopeRef | null, content = "") => {
    guard(() => {
      update({ entry: null });
      setNewDirty(false);
      setCreating({ scope: scope === undefined ? view.scope : scope, content });
    });
  };

  // ---- 실시간 ---------------------------------------------------------------------------------
  const [changedIds, setChangedIds] = useState<ReadonlySet<string>>(new Set());
  const [announce, setAnnounce] = useState("");
  const lastAnnounce = useRef(0);
  const treeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(treeTimer.current), []);
  const live = useMemoryLive({
    debounceMs: MEMORY_LIMITS.liveDebounceMs,
    onBatch: (batch) => {
      const ids = new Set(batch.map((b) => b.entry_id));
      setChangedIds(ids);
      setTimeout(() => setChangedIds(new Set()), MEMORY_LIMITS.highlightMs);
      // 나무 수·태그는 1초 디바운스로 숫자만 바뀐다
      clearTimeout(treeTimer.current);
      treeTimer.current = setTimeout(() => {
        void qc.invalidateQueries({ queryKey: memoryKeys.scopes() });
        void qc.invalidateQueries({ queryKey: ["memory", "tags"] });
      }, MEMORY_LIMITS.treeDebounceMs);
      if (view.entry !== null && ids.has(view.entry)) void qc.invalidateQueries({ queryKey: memoryKeys.entry(view.entry) });
      const atTop = (scroller()?.scrollTop ?? 0) <= 0;
      if (atTop && view.q.trim() === "") void qc.invalidateQueries({ queryKey: ["memory", "entries"] });
      else {
        setPendingChanges((n) => n + batch.length);
        const now = Date.now();
        if (now - lastAnnounce.current >= MEMORY_LIMITS.announceMs) {
          lastAnnounce.current = now;
          setAnnounce(t.toast.newChanges(pendingChangesRef.current + batch.length));
        }
      }
    },
    onReconnect: () => void invalidate(),
  });
  const pendingChangesRef = useRef(0);
  useEffect(() => {
    pendingChangesRef.current = pendingChanges;
  });
  const refreshNow = () => {
    setPendingChanges(0);
    setAnnounce("");
    toTop();
    void invalidate();
  };

  // ---- 대화상자·메뉴 --------------------------------------------------------------------------
  const [dialog, setDialog] = useState<Dlg | null>(null);
  const [rowMenu, setRowMenu] = useState<{ entry: MemoryEntrySummary; anchor: HTMLElement } | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [purging, setPurging] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const total = allScopes.reduce((n, s) => n + s.entries, 0);
  const items = entries.items;
  const noKinds = kindsQ.isSuccess && kinds.filter((k) => k.disabled !== true).length === 0;
  const workspaceEmpty = scopesQ.isSuccess && total === 0 && !hasFilters(view) && view.scope === null;
  const selectedSummary = items.find((e) => e.id === view.entry);
  const inFilter = view.entry === null || entries.pending || selectedSummary !== undefined || entries.hasMore;
  const contentTypes = useMemo(() => [...new Set(items.map((e) => e.content_type).filter((x): x is string => typeof x === "string" && x !== ""))], [items]);
  const scopeSummary = view.scope === null ? undefined : allScopes.find((s) => sameScope(s.scope, view.scope));
  const settingsPath = `${routePath(ROUTE_ROLES.settings)}#${SETTINGS_SECTION}`;

  const entryMenuItems = (entry: MemoryEntry | MemoryEntrySummary, onDone?: () => void): MenuItemDef[] => {
    const deleted = entry.deleted_at !== null && entry.deleted_at !== undefined;
    return [
      { id: "move", label: t.menu.move, disabled: deleted, onSelect: () => setDialog({ kind: "move", entry, dirty: false }) },
      { id: "history", label: t.menu.history, onSelect: () => setDialog({ kind: "history", entry, dirty: false }) },
      { id: "archive", label: entry.archived === true ? t.menu.unarchive : t.menu.archive, icon: "archive", disabled: deleted, onSelect: () => void actions.archive(entry, entry.archived !== true).then(() => onDone?.()) },
      { id: "delete", label: t.menu.delete, disabled: deleted, onSelect: () => void actions.remove(entry) },
      { id: "purge", label: t.menu.purge, danger: true, onSelect: () => setDialog({ kind: "purge", entry }) },
    ];
  };

  const confirmPurge = async (entry: MemoryEntry | MemoryEntrySummary) => {
    setPurging(true);
    const index = items.findIndex((e) => e.id === entry.id);
    const neighbor = items[index + 1] ?? items[index - 1];
    const ok = await actions.purge(entry);
    setPurging(false);
    if (!ok) return;
    setDialog(null);
    if (view.entry === entry.id) update({ entry: neighbor?.id ?? null }, false);
  };

  // ---- 키보드 ---------------------------------------------------------------------------------
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.defaultPrevented) return;
    if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !isEditable(e.target)) {
      e.preventDefault();
      searchRef.current?.focus();
    } else if (e.key === "Escape" && !(e.target instanceof HTMLElement && e.target.closest(".cm-editor, [role='dialog']"))) {
      if (creating !== null) guard(() => setCreating(null));
      else if (view.entry !== null) openEntry(null);
    }
  };

  // ---- 조각들 ---------------------------------------------------------------------------------
  const tree = (
    <MemoryScopeTree
      kinds={kinds}
      scopes={treeScopes}
      selected={view.scope}
      onSelect={(scope) => change({ scope })}
      resolvers={ctx.resolvers}
      {...(openKinds === undefined ? {} : { openKinds })}
      onOpenKindsChange={(next) => {
        setOpenKinds(next);
        storage.set(MEMORY_STORAGE.treeOpen, JSON.stringify(next));
      }}
      hiddenCount={hiddenCount}
      onShowHidden={() => setShowAllScopes(true)}
      onNewIn={(scope) => startCreate(scope)}
      onExportScope={(scope) => void actions.exportScope(scope)}
      onClearScope={(scope) => setDialog({ kind: "clear", scope })}
    />
  );
  const [scopeOpen, setScopeOpen] = useState(false);
  const scopeButton = threeCols ? null : (
    <Popover
      open={scopeOpen}
      onOpenChange={setScopeOpen}
      panelLabel={t.scope.picker}
      panelClassName="mem-pop mem-pop-tree"
      renderTrigger={(p) => (
        <button {...p} type="button" className="mem-tool mem-scope-btn" title={view.scope === null ? t.scope.pickerAll : labelText(view.scope)}>
          <span className="ac-ellipsis">{view.scope === null ? t.scope.pickerAll : t.scope.pickerButton(labelText(view.scope))}</span> <Icon name="chevron-down" size={12} />
        </button>
      )}
    >
      {({ close }) => (
        <MemoryScopeTree
          kinds={kinds}
          scopes={treeScopes}
          selected={view.scope}
          onSelect={(scope) => {
            change({ scope });
            close();
          }}
          resolvers={ctx.resolvers}
          hiddenCount={hiddenCount}
          onShowHidden={() => setShowAllScopes(true)}
        />
      )}
    </Popover>
  );

  const chips: ChipItem[] = [];
  const addChip = (id: string, label: string, remove: () => void, title?: string) =>
    chips.push({ id, label, title: title ?? t.chip.remove(label), icon: "close", active: true, onSelect: remove });
  if (ctx.project !== null && ctx.projectName !== null) addChip("current-prj", t.chip.project(ctx.projectName), () => projects.setCurrent(null));
  if (showAllScopes && ctx.project !== null) addChip("released", t.chip.projectReleased, () => setShowAllScopes(false));
  if (view.tag !== null) addChip("tag", t.chip.tag(view.tag), () => change({ tag: null }));
  if (view.authorKind !== null) addChip("authorKind", t.chip.authorKind(t.authorKind[view.authorKind] ?? view.authorKind), () => change({ authorKind: null }));
  if (view.authorRun !== null) {
    const runId = view.authorRun;
    addChip("authorRun", t.chip.authorRun(runId), () => change({ authorRun: null }), t.chip.authorRunTip(runId));
    if (runsOn) chips.push({ id: "openRun", label: t.chip.openRun, icon: "external-link", onSelect: () => void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(runId)}`) });
  }
  const clearAll = () => {
    setShowAllScopes(false);
    change({ q: "", tag: null, authorRun: null, authorKind: null, includeArchived: false, includeDeleted: false });
  };

  // ---- 표 자리 상태 ---------------------------------------------------------------------------
  const clearFiltersButton = <Button onClick={clearAll}>{t.state.clearFilters}</Button>;
  let tableEmpty: React.ReactNode;
  if (entries.pending) {
    tableEmpty = <div className="mem-skeleton" role="status" aria-busy="true" aria-label={t.loading}><Spinner /></div>;
  } else if (entries.error !== null && items.length === 0) {
    tableEmpty = <ErrorBlock title={t.state.errorList} message={describeError(entries.error, t.state.errorList).message} retryLabel={t.retry} onRetry={entries.refetch} />;
  } else if (workspaceEmpty) {
    tableEmpty = (
      <EmptyState
        icon={routeIconNode(ROUTE_ROLES.memory, 32)}
        title={t.state.emptyTitle}
        description={
          <>
            <p>{t.state.emptyBody}</p>
            <ul className="mem-benefits">{t.state.benefits.map((b) => <li key={b}>{b}</li>)}</ul>
            <p className="mem-muted">{t.state.hintResourceNoType}</p>
          </>
        }
        action={<Button onClick={() => setDialog({ kind: "import" })}>{t.actions.import}</Button>}
      />
    );
  } else if (hasFilters(view)) {
    tableEmpty = (
      <EmptyState title={view.q.trim() !== "" && view.tag === null && view.authorKind === null && view.authorRun === null ? t.state.filterNoneQ(view.q) : t.state.filterNone} action={clearFiltersButton} />
    );
  } else if (view.scope !== null) {
    tableEmpty = <EmptyState title={t.state.scopeEmptyTitle} />;
  }

  // ---- 상세 칸 --------------------------------------------------------------------------------
  const detailOpen = creating !== null || view.entry !== null;
  let detail: React.ReactNode = null;
  if (creating !== null) {
    detail = (
      <NewEntryForm
        key={`new-${creating.scope === null ? "" : scopeParam(creating.scope)}`}
        initialScope={creating.scope}
        initialContent={creating.content}
        kinds={kinds}
        scopes={allScopes}
        labelOf={labelText}
        maxBytes={limits.maxEntryBytes}
        onDirtyChange={setNewDirty}
        onCancel={() => guard(() => setCreating(null))}
        onOpenExisting={(id) => {
          setNewDirty(false);
          setCreating(null);
          update({ entry: id }, false);
        }}
        onCreated={(entry) => {
          setNewDirty(false);
          setCreating(null);
          void invalidate();
          update({ entry: entry.id }, false);
        }}
      />
    );
  } else if (view.entry !== null) {
    detail = (
      <EntryDetail
        key={view.entry}
        id={view.entry}
        {...(selectedSummary === undefined ? {} : { knownKey: selectedSummary.key })}
        handleRef={detailRef}
        kinds={kinds}
        ctx={ctx}
        limits={limits}
        inFilter={inFilter}
        closable={!threeCols}
        contentTypeSuggestions={contentTypes}
        onOpenRun={runsOn ? (runId) => void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(runId)}`) : undefined}
        onClose={() => openEntry(null)}
        onDirtyChange={setDetailDirty}
        onHistory={(entry, d) => setDialog({ kind: "history", entry, dirty: d })}
        onMove={(entry, d) => setDialog({ kind: "move", entry, dirty: d })}
        onArchive={actions.archive}
        onDelete={(entry) => void actions.remove(entry)}
        onPurge={(entry) => setDialog({ kind: "purge", entry })}
        onRestore={actions.restore}
        onSaveAsNew={({ content, entry }) => {
          detailRef.current?.discard();
          setCreating({ scope: entry.scope, content });
          update({ entry: null });
        }}
      />
    );
  } else if (threeCols) {
    detail = <ScopeSummaryPanel summary={scopeSummary} label={view.scope === null ? null : labelText(view.scope)} onNew={() => startCreate()} />;
  }

  const exportItems: MenuItemDef[] = [
    { id: "current", label: t.export.current, disabled: view.scope === null || total === 0, title: view.scope === null ? t.export.disabledNoScope : undefined, onSelect: () => void actions.exportScope(view.scope) },
    { id: "all", label: t.export.all, disabled: total === 0, title: total === 0 ? t.export.disabledEmpty : undefined, onSelect: () => void actions.exportScope(null) },
  ];

  const headerActions = (
    <>
      <Button variant="primary" icon={<Icon name="plus" />} onClick={() => startCreate()} disabled={noKinds}>{t.actions.new}</Button>
      <Popover
        open={exportOpen}
        onOpenChange={setExportOpen}
        panelRole="menu"
        panelLabel={t.export.menuLabel}
        align="end"
        renderTrigger={(p) => (
          <Button {...p} disabled={total === 0}>{t.actions.export} <Icon name="chevron-down" size={12} /></Button>
        )}
      >
        <Menu items={exportItems} onClose={() => setExportOpen(false)} />
        <p className="mem-help mem-pop-note">{t.export.note}</p>
      </Popover>
      <Button onClick={() => setDialog({ kind: "import" })}>{t.actions.import}</Button>
      <IconButton label={t.actions.settings} icon={<Icon name="settings" />} onClick={() => void navigate(settingsPath)} />
    </>
  );

  const storageWarning = warnings.find((w) => w.code === WARNING_CODES.storageMemory);
  const otherWarnings = warnings.filter((w) => w.code !== WARNING_CODES.storageMemory && w.code !== WARNING_CODES.searchFallback);
  const searchSlow = warnings.some((w) => w.code === WARNING_CODES.searchFallback);

  return (
    <div className="app-screen-frame mem-frame" data-screen="memory" data-cols={threeCols ? 3 : 2} role="region" aria-label={t.region} onKeyDown={onKeyDown}>
      <PageHeader title={t.title} actions={headerActions} />
      {storageWarning !== undefined ? (
        <Banner tone="warning" className="mem-banner" actions={<Button size="sm" disabled={total === 0} onClick={() => void actions.exportScope(null)}>{t.actions.export}</Button>}>
          {t.storageMemory}
        </Banner>
      ) : null}
      {otherWarnings.map((w) => <Banner key={w.code} tone="warning" className="mem-banner">{w.message}</Banner>)}
      {noKinds ? null : (
        <MemoryToolbar
          view={view}
          onChange={change}
          scopePicker={scopeButton}
          searchRef={searchRef}
          refreshing={entries.fetching && !entries.pending}
          onRefresh={refreshNow}
          disconnected={live.disconnected}
          searchSlow={searchSlow}
        />
      )}
      {chips.length > 0 && !noKinds ? (
        <div className="mem-chips">
          <ChipRow chips={chips} ariaLabel={t.toolbar.filters} />
          {chips.filter((c) => c.active).length >= 2 ? <button type="button" className="mem-linkbtn" onClick={clearAll}>{t.toolbar.clearAll}</button> : null}
        </div>
      ) : null}
      <div ref={bodyRef} className="mem-body">
        {noKinds ? (
          <EmptyState
            icon={routeIconNode(ROUTE_ROLES.memory, 32)}
            title={t.state.noKindsTitle}
            description={t.state.noKindsBody}
            action={<Button variant="primary" onClick={() => void navigate(settingsPath)}>{t.state.openSettings}</Button>}
          />
        ) : (
          <>
            {threeCols ? (
              <>
                <aside className="mem-tree" style={{ width: treeWidth }} aria-label={t.scope.treeLabel}>
                  {kindsQ.isError || scopesQ.isError ? (
                    <ErrorBlock title={t.state.errorTree} retryLabel={t.retry} onRetry={() => void invalidate()} />
                  ) : (
                    tree
                  )}
                </aside>
                <PaneSeparator
                  side="left"
                  size={treeWidth}
                  {...MEMORY_LIMITS.tree}
                  label={t.keyboard.treeSplit}
                  onChange={(next) => {
                    setTreeWidth(next);
                    storage.set(MEMORY_STORAGE.treeWidth, String(next));
                  }}
                />
              </>
            ) : null}
            <section className="mem-list" data-busy={entries.fetching && !entries.pending ? "" : undefined}>
              {pendingChanges > 0 ? (
                <button type="button" className="mem-newchanges" onClick={refreshNow}>
                  {t.live.newChanges(pendingChanges)} — {t.live.toTop}
                </button>
              ) : null}
              <span className="mem-sr" role="status" aria-live="polite">{announce}</span>
              <div className="mem-table-wrap">
                <MemoryEntryTable
                  entries={items}
                  total={entries.total}
                  hasMore={entries.hasMore}
                  loading={entries.fetchingMore}
                  onLoadMore={entries.fetchMore}
                  selectedId={view.entry}
                  onSelect={(e) => openEntry(e.id)}
                  onOpen={(e) => openEntry(e.id, true)}
                  onNew={() => startCreate()}
                  onDelete={(e) => void actions.remove(e)}
                  onPurge={(e) => setDialog({ kind: "purge", entry: e })}
                  onContextMenu={(entry, anchor) => setRowMenu({ entry, anchor })}
                  query={view.q}
                  showScope={view.scope === null}
                  scopeText={labelText}
                  isUnknownKind={isUnknown}
                  authorOptions={ctx.authorOptions}
                  changedIds={changedIds}
                  sortKeys={SORT_KEYS_BY_COLUMN}
                  sort={view.sort}
                  onSortChange={(sort) => change({ sort })}
                  emptyContent={tableEmpty}
                  {...(layoutWidth === undefined ? {} : { width: Math.max(0, width - (detailOpen ? detailWidth : 0) - (threeCols ? treeWidth : 0) - 12) })}
                />
              </div>
            </section>
            {detailOpen || threeCols ? (
              <>
                <PaneSeparator
                  side="right"
                  size={detailWidth}
                  {...MEMORY_LIMITS.detail}
                  label={t.keyboard.detailSplit}
                  onChange={(next) => {
                    setDetailWidth(next);
                    storage.set(MEMORY_STORAGE.detailWidth, String(next));
                  }}
                />
                <aside className="mem-detail-pane" style={{ width: detailWidth }}>{detail}</aside>
              </>
            ) : null}
          </>
        )}
      </div>
      {leaveDialog}
      {rowMenu !== null ? (
        <FloatingMenu anchor={rowMenu.anchor} label={t.menu.label(rowMenu.entry.key)} items={entryMenuItems(rowMenu.entry)} onClose={() => setRowMenu(null)} />
      ) : null}
      {dialog?.kind === "move" ? (
        <MoveDialog
          entry={dialog.entry}
          kinds={kinds}
          scopes={allScopes}
          labelOf={labelText}
          dirty={dialog.dirty}
          onClose={() => setDialog(null)}
          onMoved={() => {
            setDialog(null);
            void invalidate();
          }}
        />
      ) : null}
      {dialog?.kind === "history" ? (
        <HistoryDialog
          entry={dialog.entry}
          ctx={ctx}
          labelOf={labelText}
          dirty={dialog.dirty}
          maxVersions={limits.maxVersions}
          onClose={() => setDialog(null)}
          onRestored={() => {
            detailRef.current?.discard();
            setDialog(null);
            void invalidate();
          }}
        />
      ) : null}
      {dialog?.kind === "purge" ? (
        <PurgeDialog
          entry={dialog.entry}
          scopeLabel={labelText(dialog.entry.scope)}
          versions={limits.maxVersions === null ? dialog.entry.version : Math.min(dialog.entry.version, limits.maxVersions)}
          busy={purging}
          onCancel={() => setDialog(null)}
          onConfirm={() => void confirmPurge(dialog.entry)}
        />
      ) : null}
      {dialog?.kind === "clear" ? (
        <ClearScopeDialog
          scope={dialog.scope}
          summary={allScopes.find((s) => sameScope(s.scope, dialog.scope))}
          label={labelText(dialog.scope)}
          onClose={() => setDialog(null)}
          onDone={() => void invalidate()}
        />
      ) : null}
      {dialog?.kind === "import" ? (
        <ImportDialog
          onClose={() => setDialog(null)}
          onImported={() => void invalidate()}
          onViewImported={() => {
            setDialog(null);
            change({ authorKind: IMPORTED_AUTHOR_KIND });
          }}
        />
      ) : null}
    </div>
  );
}
