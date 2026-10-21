import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button, useShortcuts, useToast } from "@agent-console/ui";
import { HandoffMatrixView, LogEventTable, eventColumns, hasActiveFilter, isErrorEvent, type HandoffCell, type RowMenuAnchor } from "@agent-console/log-view";
import type { LogEvent } from "@agent-console/contracts";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useStorage } from "../../app/StorageContext";
import { ColumnsMenu, useColumnChoice } from "./ColumnsMenu";
import { EmptyNoLogs, EmptyNoMatch, FirstUseCard, NewEventsBanner, OtherSourcesHint } from "./LogsEmpty";
import { LogDetailPanel } from "./LogDetailPanel";
import { useDetailLink } from "./useDetailLink";
import { LogFilters, RangeControl, buildFilterFields } from "./LogFilters";
import { LogMenu, type LogMenuItem } from "./LogMenu";
import { LogsPageFrame } from "./LogsPageFrame";
import { useLogsIngested } from "./LogsLive";
import { SplitHandle } from "./SplitHandle";
import { useArchiveDownload } from "./archive";
import { CELL_IDS, DEFAULT_RANGE, EVENT_COLUMN_IDS, FILTER_KEYS, LOGS_LIMITS, LOGS_SCOPES, LOGS_STORAGE, SCREEN_PARAMS, SEARCH_EVENT_COLUMNS_DEFAULT, SEARCH_VIEWS, SUGGEST_FROM } from "./logsConfig";
import { errorBlockOf, fieldErrorsOf } from "./logsErrors";
import { classifyEmpty, enabledCount, eventFieldValues, originOf, parseRange, rangeToWindow, suggestionsFor, toRequestParams, withValues } from "./logsLib";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { useElementHeight } from "./useElementHeight";
import { useFilterOptions } from "./useFilterOptions";
import { useLogUrlState, useSelectedUid } from "./useLogFilterState";
import { useLogScan } from "./useLogScan";
import { logKeys, useAnyEvents, useLogEventPages, useLogHandoffs, useLogSources, useLogTaxonomyView } from "./useLogsApi";

const FIELDS = buildFilterFields();
const VIEWS = SEARCH_VIEWS;
/** 보기 id: 첫째가 이벤트 표(기본), 둘째가 위임 행렬 */
const EVENTS_VIEW = VIEWS[0] ?? "";
const MATRIX_VIEW = VIEWS[1] ?? "";
type View = string;

/** 검색(`/logs/search`): 세션 경계 없는 이벤트 표(키셋 페이지)와 handoff 행렬. 필터는 두 보기가 공유한다. */
export function SearchPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const storage = useStorage();
  const url = useLogUrlState(FIELDS);
  const [selectedUid, setSelectedUid] = useSelectedUid();
  const { tableRef: eventTableRef, panelRef: detailPanelRef, onActivate: activateEvent, reveal: revealEvent } = useDetailLink(selectedUid);
  const sources = useLogSources();
  const taxonomy = useLogTaxonomyView();
  const scan = useLogScan(sources.data);
  const download = useArchiveDownload();
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [anchor, setAnchor] = useState(() => Date.now());
  const [newBanner, setNewBanner] = useState(false);
  const [menu, setMenu] = useState<{ items: readonly LogMenuItem[]; anchor: RowMenuAnchor; note?: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const height = useElementHeight(wrapRef, 420);
  const [cols, setCols] = useColumnChoice(LOGS_STORAGE.colsSession + ".search", EVENT_COLUMN_IDS, SEARCH_EVENT_COLUMNS_DEFAULT);
  const columns = useMemo(() => eventColumns(cols), [cols]);
  const [timeMode, setTimeMode] = useState<"relative" | "absolute">(() => (storage.get(LOGS_STORAGE.timeMode) === "absolute" ? "absolute" : "relative"));
  const [detailW, setDetailW] = useState(() => Number(storage.get(LOGS_STORAGE.detailWidth)) || LOGS_LIMITS.detailWidthDefault);

  const viewParam = url.screen[SCREEN_PARAMS.view]?.[0];
  const view: View = VIEWS.includes(viewParam ?? "") ? (viewParam as View) : EVENTS_VIEW;
  const rangeValue = url.screen[SCREEN_PARAMS.range]?.[0];
  const window = rangeToWindow(parseRange(rangeValue, DEFAULT_RANGE.search), anchor);
  const params = useMemo(() => toRequestParams(url.filter, { [FILTER_KEYS.order]: order, [FILTER_KEYS.limit]: LOGS_LIMITS.eventsPage }, window), [url.filter, order, window.since, window.until]); // eslint-disable-line react-hooks/exhaustive-deps
  const handoffParams = useMemo(() => toRequestParams(url.filter, {}, window), [url.filter, window.since, window.until]); // eslint-disable-line react-hooks/exhaustive-deps
  const events = useLogEventPages(params, view === EVENTS_VIEW);
  const handoffs = useLogHandoffs(handoffParams, view === MATRIX_VIEW);
  const rows = useMemo<LogEvent[]>(() => (events.data?.pages ?? []).flatMap((p) => p.items ?? []), [events.data]);
  const total = events.data?.pages[0]?.total ?? null;
  const fieldErrors = useMemo(() => fieldErrorsOf(view === EVENTS_VIEW ? events.error : handoffs.error), [view, events.error, handoffs.error]);
  const isError = useCallback((e: Pick<LogEvent, "category" | "tags">) => isErrorEvent(e, taxonomy), [taxonomy]);
  const seen = useMemo(() => [...new Set(rows.map((r) => r.category))], [rows]);
  const options = useFilterOptions(taxonomy, seen);
  const origin = useMemo(() => originOf(rows), [rows]);
  const suggestions = useMemo(() => Object.fromEntries(Object.entries(SUGGEST_FROM).map(([n, f]) => [n, suggestionsFor(rows, (e) => eventFieldValues(e, f))])), [rows]);
  const listEmpty = view === EVENTS_VIEW && events.data !== undefined && rows.length === 0;
  const anyEvents = useAnyEvents(listEmpty && sources.data !== undefined && enabledCount(sources.data) > 0);
  const filtered = hasActiveFilter(url.filter);

  const refresh = () => {
    setAnchor(Date.now());
    setNewBanner(false);
    void qc.invalidateQueries({ queryKey: logKeys.root });
  };
  useLogsIngested(() => setNewBanner(true), LOGS_LIMITS.liveDebounceMs);
  const setView = (v: View) => url.setScreen({ [SCREEN_PARAMS.view]: v === EVENTS_VIEW ? null : v });
  useShortcuts([
    { id: "logs.x.search", scope: LOGS_SCOPES.search, keys: "/", titleKey: "shortcuts.logsFocusSearch", run: () => searchRef.current?.focus() },
    { id: "logs.x.filter", scope: LOGS_SCOPES.search, keys: "f", titleKey: "shortcuts.logsFocusFilter", run: () => document.querySelector<HTMLElement>(".ac-lv-addwrap button")?.click() },
    { id: "logs.x.view", scope: LOGS_SCOPES.search, keys: "h", titleKey: "shortcuts.logsHandoffToggle", run: () => setView(view === EVENTS_VIEW ? MATRIX_VIEW : EVENTS_VIEW) },
    { id: "logs.x.refresh", scope: LOGS_SCOPES.search, keys: "r", titleKey: "shortcuts.logsRefresh", run: refresh },
  ]);

  const copy = (text: string) => void navigator.clipboard?.writeText(text).then(() => toast({ tone: "success", text: t.copied, durationMs: 2000 }));
  const openRowMenu = (uid: string, a: RowMenuAnchor) => {
    const e = rows.find((r) => r.uid === uid);
    if (e === undefined) return;
    setMenu({
      anchor: a,
      items: [
        { id: "open", label: t.detail.openDetail, onSelect: () => setSelectedUid(uid) },
        { id: "call", label: t.detail.sameCall, onSelect: () => url.setFilter(withValues(url.filter, FILTER_KEYS.callId, e.call_id ? [e.call_id] : [])), disabled: !e.call_id },
        { id: "copy", label: t.detail.copyUid, onSelect: () => copy(uid) },
        { id: "session", label: t.search.openSession, onSelect: () => void navigate(`/logs/sessions/${encodeURIComponent(e.session ?? "")}#e=${encodeURIComponent(uid)}`), disabled: !e.session },
      ],
    });
  };
  const openArchiveMenu = (el: HTMLElement | null) => {
    const r = el?.getBoundingClientRect();
    setMenu({
      anchor: { x: r?.left ?? 0, y: r?.bottom ?? 0, element: el ?? undefined },
      items: [
        { id: "html", label: `${t.sessions.archive} — ${t.sessions.archiveHtml}`, onSelect: () => void download(handoffParams, "html") },
        { id: "json", label: `${t.sessions.archive} — ${t.sessions.archiveJson}`, onSelect: () => void download(handoffParams, "json") },
      ],
      note: t.sessions.archiveOffline,
    });
  };

  const cells: HandoffCell[] = (handoffs.data?.cells ?? []).map((c) => ({ from: c.from ?? c.source, to: c.to ?? c.target, via: c.via ?? c.kind, count: c.count }));
  const clearFilters = () => url.setFilter({});
  const defaultRange = rangeValue === undefined || rangeValue === DEFAULT_RANGE.search;

  let body;
  if (view === MATRIX_VIEW) {
    body = handoffs.isError && handoffs.data === undefined && Object.keys(fieldErrors).length === 0 ? (
      <ErrorBlock title={t.search.handoffFailed} message={errorBlockOf(handoffs.error, t.loadFailed).message} retryLabel={t.retry} onRetry={() => void handoffs.refetch()} />
    ) : (
      <HandoffMatrixView
        cells={cells}
        loading={handoffs.isPending}
        limit={40}
        onCellClick={(c) => url.update(withValues(withValues(withValues(url.filter, FILTER_KEYS.from, [c.from]), FILTER_KEYS.to, [c.to]), FILTER_KEYS.via, c.via === undefined ? [] : [c.via]), { [SCREEN_PARAMS.view]: null })}
      />
    );
  } else if (events.isError && events.data === undefined && Object.keys(fieldErrors).length === 0) {
    const e = errorBlockOf(events.error, t.loadFailed);
    body = <ErrorBlock title={t.loadFailed} message={e.message} {...(e.detail === undefined ? {} : { details: e.detail })} detailsLabel={t.detailsLabel} retryLabel={t.retry} onRetry={() => void events.refetch()} />;
  } else if (listEmpty && sources.data !== undefined && !filtered && classifyEmpty(sources.data, undefined) === "A") {
    body = <FirstUseCard sources={sources.data} />;
  } else if (listEmpty && sources.data !== undefined) {
    const kind = filtered || !defaultRange ? "C" : classifyEmpty(sources.data, anyEvents);
    body = kind === "B" ? <EmptyNoLogs sources={sources.data} scanning={scan.scanning} onScan={() => void scan.run()} /> : <EmptyNoMatch onClearFilters={filtered ? clearFilters : undefined} onAllRange={defaultRange ? () => url.setScreen({ [SCREEN_PARAMS.range]: "all" }) : undefined} />;
  } else {
    body = (
      <LogEventTable
        ref={eventTableRef}
        onActivate={activateEvent}
        rows={rows}
        columns={columns}
        selectedUid={selectedUid}
        onSelect={setSelectedUid}
        onRowMenu={openRowMenu}
        taxonomy={taxonomy}
        isError={isError}
        slotFor={slotFor}
        timeMode={timeMode}
        originTime={timeMode === "relative" ? origin : null}
        loading={events.isPending}
        hasMore={events.hasNextPage}
        loadingMore={events.isFetchingNextPage}
        onNearEnd={() => void events.fetchNextPage()}
        height={Math.max(160, height - 40)}
        ariaLabel={t.detail.ariaTable}
        renderCell={(id, row) =>
          id === CELL_IDS.session && row.session ? (
            <Link className="logs-linkbtn logs-mono" tabIndex={-1} to={`/logs/sessions/${encodeURIComponent(row.session)}#e=${encodeURIComponent(row.uid)}`} title={row.session} onClick={(ev) => ev.stopPropagation()}>
              {row.session.slice(0, 8)}
            </Link>
          ) : undefined
        }
      />
    );
  }

  const count = events.data === undefined ? "" : total !== null ? t.detail.resultCount(total) : events.hasNextPage ? t.detail.resultCountMore(rows.length) : t.detail.resultCountExact(rows.length);
  const selectedRow = selectedUid === null ? undefined : rows.find((r) => r.uid === selectedUid);

  return (
    <LogsPageFrame
      tab="search"
      status={<span className="app-muted" role="status">{scan.scanning ? t.scanning : (view === EVENTS_VIEW ? events.isFetching : handoffs.isFetching) && !events.isPending ? t.refreshing : ""}</span>}
      actions={
        <>
          <Button size="sm" onClick={refresh}>{t.refresh} ⟳</Button>
          {enabledCount(sources.data) > 0 ? <Button size="sm" loading={scan.scanning} onClick={() => void scan.run()}>{t.scan}</Button> : null}
        </>
      }
    >
      {rows.length > 0 ? <OtherSourcesHint sources={sources.data} /> : null}
      {newBanner ? <NewEventsBanner text={t.search.newBanner} action={t.search.loadNew} onAction={refresh} /> : null}
      <div className="logs-toolbar">
        <LogFilters
          value={url.filter}
          onChange={url.setFilter}
          options={options}
          suggestions={suggestions}
          fieldErrors={fieldErrors}
          inputRef={searchRef}
          trailing={<RangeControl value={rangeValue} fallbackId={DEFAULT_RANGE.search} onChange={(v) => url.setScreen({ [SCREEN_PARAMS.range]: v })} />}
        />
        {url.unknown.length > 0 ? <span className="app-muted" role="status">{t.filters.unknownError}: {url.unknown.join(", ")}</span> : null}
      </div>
      <div className="logs-subhead">
        <div role="tablist" aria-label={t.search.viewTabs} className="logs-subtabs ac-tabs-list" onKeyDown={(e) => {
          if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
            e.preventDefault();
            setView(view === EVENTS_VIEW ? MATRIX_VIEW : EVENTS_VIEW);
          }
        }}>
          {VIEWS.map((v) => (
            <button key={v} type="button" role="tab" id={`logs-view-${v}`} aria-selected={view === v} tabIndex={view === v ? 0 : -1} className="ac-tab" onClick={() => setView(v)}>
              {t.search.views[v] ?? v}
            </button>
          ))}
        </div>
        <span className="app-muted" aria-live="polite">{view === EVENTS_VIEW ? count : ""}</span>
        <span className="logs-spacer" />
        {view === EVENTS_VIEW ? (
          <>
            <Button size="sm" aria-pressed={order === "desc"} onClick={() => setOrder(order === "desc" ? "asc" : "desc")}>{order === "desc" ? t.search.orderDesc : t.search.orderAsc}</Button>
            <Button size="sm" aria-pressed={timeMode === "absolute"} aria-label={t.filters.timeMode} onClick={() => { const next = timeMode === "relative" ? "absolute" : "relative"; setTimeMode(next); storage.set(LOGS_STORAGE.timeMode, next); }}>⏱ {timeMode === "relative" ? t.filters.timeRelative : t.filters.timeAbsolute}</Button>
            <ColumnsMenu all={EVENT_COLUMN_IDS} selected={cols} labelOf={(id) => eventColumns([id])[0]?.header?.toString() ?? id} onChange={setCols} />
          </>
        ) : null}
        <Button size="sm" aria-haspopup="menu" onClick={(e) => openArchiveMenu(e.currentTarget)}>{t.search.archive} ▾</Button>
      </div>
      <div className="logs-search-main" data-detail={selectedUid !== null ? "open" : "closed"}>
        <div ref={wrapRef} className="logs-tablewrap" data-dim={(view === EVENTS_VIEW ? events.isError : handoffs.isError) && Object.keys(fieldErrors).length > 0 ? "true" : undefined}>
          {body}
          {view === EVENTS_VIEW && events.isFetchNextPageError ? (
            <p role="alert" className="logs-nextfail">{t.search.nextFailed} <Button size="sm" onClick={() => void events.fetchNextPage()}>{t.search.nextRetry}</Button></p>
          ) : null}
        </div>
        {view === EVENTS_VIEW && selectedUid !== null ? (
          <>
            <SplitHandle size={detailW} min={LOGS_LIMITS.detailWidthMin} max={LOGS_LIMITS.detailWidthMax} onChange={(n) => { setDetailW(n); storage.set(LOGS_STORAGE.detailWidth, String(n)); }} label={t.detail.splitLabel} />
            <div className="logs-detail-col" style={{ width: detailW }}>
              <LogDetailPanel
                ref={detailPanelRef}
                uid={selectedUid}
                preview={selectedRow}
                taxonomy={taxonomy}
                isError={isError}
                originTime={origin}
                laneLabelFor={() => undefined}
                filteredOut={selectedRow === undefined}
                width={detailW}
                onClose={() => setSelectedUid(null)}
                onOpenEvent={(uid, ses) => {
                  if (ses !== undefined) void navigate(`/logs/sessions/${encodeURIComponent(ses)}#e=${encodeURIComponent(uid)}`);
                  else {
                    setSelectedUid(uid);
                    revealEvent(uid);
                  }
                }}
              />
            </div>
          </>
        ) : null}
      </div>
      {menu === null ? null : <LogMenu label={t.sessions.rowMenu} anchor={menu.anchor} items={menu.items} {...(menu.note === undefined ? {} : { footnote: menu.note })} onClose={() => setMenu(null)} />}
    </LogsPageFrame>
  );
}

