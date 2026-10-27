import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Banner, Button, IconButton, useShortcuts, useToast } from "@agent-console/ui";
import {
  CategoryChips,
  LogEventTable,
  PlaybackBar,
  focusLogControl,
  eventColumns,
  indexOfSeq,
  isErrorEvent,
  isHiddenEvent,
  nextSpeed,
  orderCategories,
  seqAtIndex,
  sortEvents,
  usePlayback,
  type PlaybackClock,
  type RowMenuAnchor,
} from "@agent-console/log-view";
import type { LogEvent } from "@agent-console/contracts";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useApiQuery } from "../../app/queries";
import { useStorage } from "../../app/StorageContext";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { ColumnsMenu, useColumnChoice } from "./ColumnsMenu";
import { LogDetailPanel } from "./LogDetailPanel";
import { LogFilters, buildFilterFields } from "./LogFilters";
import { LogMenu, type LogMenuItem } from "./LogMenu";
import { useDetailLink } from "./useDetailLink";
import { LogsPageFrame } from "./LogsPageFrame";
import { useLogsIngested } from "./LogsLive";
import { FlowSegments, SessionFlow, type FlowView } from "./SessionFlow";
import { SplitHandle } from "./SplitHandle";
import { archiveFilterFor, useArchiveDownload } from "./archive";
import { CELL_IDS, EVENT_COLUMN_IDS, FILTER_KEYS, LOGS_LIMITS, LOGS_SCOPES, LOGS_STORAGE, SCREEN_PARAMS, SEARCH_FIELD, SESSION_EVENT_COLUMNS_DEFAULT, SUGGEST_FROM } from "./logsConfig";
import { errorBlockOf } from "./logsErrors";
import { categoryItems, filterSessionEvents, laneLabels, laneOf, originOf, paramsKey, suggestionsFor, eventFieldValues, toLaneEvents, shouldAutoFoldFlow, clampOr, valuesOf, withValues } from "./logsLib";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { useElementHeight } from "./useElementHeight";
import { useFilterOptions } from "./useFilterOptions";
import { useLogUrlState, useSelectedUid } from "./useLogFilterState";
import { logKeys, useLogTaxonomyView, useLogTimeline, useLogTrace } from "./useLogsApi";

const FIELDS = buildFilterFields();
const NO_PARAMS = {} as const;
const NO_STRINGS: readonly string[] = [];
const REAL_CLOCK: PlaybackClock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => window.setTimeout(fn, ms),
  clearTimeout: (h) => window.clearTimeout(h as number),
};

function readNumber(raw: string | null, fallback: number): number {
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

/** 세션 상세(`/logs/sessions/:session`): 재생 막대 + 흐름 패널(레인·위임 흐름) + 범주 칩 + 이벤트 표 + 상세 패널. */
export function SessionDetailPage() {
  const { session = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const storage = useStorage();
  const url = useLogUrlState(FIELDS);
  const [selectedUid, setSelectedUid] = useSelectedUid();
  const taxonomy = useLogTaxonomyView();
  const isError = useCallback((e: Pick<LogEvent, "category" | "tags">) => isErrorEvent(e, taxonomy), [taxonomy]);
  const isHidden = useCallback((e: Pick<LogEvent, "category">) => isHiddenEvent(e, taxonomy), [taxonomy]);
  const download = useArchiveDownload();
  const traceVisible = useLinkPart(LINK_PART_IDS.logsTraceFlow).visible;

  // ---- 데이터
  const tl = useLogTimeline(session, NO_PARAMS);
  const hiddenIds = useMemo(() => taxonomy.order.filter((id) => !taxonomy.get(id).visible), [taxonomy]);
  const [includeHidden, setIncludeHidden] = useState(false);
  const hiddenParams = useMemo(() => ({ [FILTER_KEYS.session]: session, [FILTER_KEYS.category]: hiddenIds, [FILTER_KEYS.limit]: "200", [FILTER_KEYS.order]: "asc" }), [session, hiddenIds]);
  const hiddenQ = useApiQuery(logKeys.events(paramsKey(hiddenParams)), (rest) => rest.listLogEvents(hiddenParams), { enabled: includeHidden && hiddenIds.length > 0 });
  const timeline = tl.data;
  const all = useMemo(() => {
    const merged = new Map<string, LogEvent>();
    for (const e of timeline?.events ?? []) merged.set(e.uid, e);
    if (includeHidden) for (const e of hiddenQ.data?.items ?? []) if (!merged.has(e.uid)) merged.set(e.uid, e);
    return sortEvents([...merged.values()]);
  }, [timeline?.events, includeHidden, hiddenQ.data]);
  const lanes = useMemo(() => timeline?.lanes ?? [], [timeline?.lanes]);
  const labels = useMemo(() => laneLabels(lanes), [lanes]);
  const laneLabelFor = useCallback((id: string) => labels.get(id), [labels]);
  const origin = useMemo(() => originOf(all), [all]);

  // ---- 재생 위치(로컬 상태가 진실, URL `through`는 초기값이자 정지했을 때의 기록)
  const throughRaw = url.screen[SCREEN_PARAMS.through]?.[0];
  const [pos, setPos] = useState<number | null>(null);
  const fromUrl = indexOfSeq(all, throughRaw === undefined ? null : Number(throughRaw));
  const index = Math.min(pos ?? fromUrl, all.length - 1);
  const playback = usePlayback({
    events: all,
    clock: REAL_CLOCK,
    index,
    onIndexChange: setPos,
    initialSpeed: readNumber(storage.get(LOGS_STORAGE.speed), 1),
    initialSkipGaps: storage.get(LOGS_STORAGE.skipGaps) !== "0",
  });
  const atEnd = index >= all.length - 1;
  const live = atEnd && !playback.playing;
  const [liveBanner, setLiveBanner] = useState(false);
  useEffect(() => {
    if (playback.playing) return;
    const want = index < 0 ? undefined : seqAtIndex(all, index);
    const have = throughRaw === undefined ? undefined : Number(throughRaw);
    if (index >= 0 && want !== have) url.setScreen({ [SCREEN_PARAMS.through]: want === undefined ? null : String(want) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, playback.playing, all]);
  useEffect(() => storage.set(LOGS_STORAGE.openedSession, "1"), [storage]);

  useLogsIngested(
    () => {
      if (live) {
        void qc.invalidateQueries({ queryKey: ["logs", "timeline", session] });
        setPos(null);
      } else setLiveBanner(true);
    },
    LOGS_LIMITS.liveDebounceMs,
  );

  // ---- 표시 필터
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [grouped, setGrouped] = useState(true);
  const [follow, setFollow] = useState(true);
  const [timeMode, setTimeMode] = useState<"relative" | "absolute">(() => (storage.get(LOGS_STORAGE.timeMode) === "absolute" ? "absolute" : "relative"));
  const laneFilter = url.screen[SCREEN_PARAMS.lane] ?? NO_STRINGS;
  const visible = useMemo(() => all.slice(0, index + 1), [all, index]);
  const rows = useMemo(
    () =>
      filterSessionEvents(
        visible,
        { filter: url.filter, names: { search: SEARCH_FIELD, category: FILTER_KEYS.category, since: FILTER_KEYS.since, until: FILTER_KEYS.until, source: FILTER_KEYS.source, suggestFrom: SUGGEST_FROM }, errorsOnly, lanes: laneFilter, includeHidden },
        isError,
        isHidden,
      ),
    [visible, url.filter, errorsOnly, laneFilter, includeHidden, isError, isHidden],
  );
  const chipItems = useMemo(() => orderCategories(categoryItems(all, visible), taxonomy), [all, visible, taxonomy]);
  const seenCategories = useMemo(() => chipItems.map((c) => c.id), [chipItems]);
  const options = useFilterOptions(taxonomy, seenCategories);
  const errorCount = useMemo(() => all.filter(isError).length, [all, isError]);
  const errorIndexes = useMemo(() => all.flatMap((e, i) => (isError(e) ? [i] : [])).slice(0, LOGS_LIMITS.maxErrorTicks * 5), [all, isError]);
  const suggestions = useMemo(
    () => Object.fromEntries(Object.entries(SUGGEST_FROM).map(([name, field]) => [name, suggestionsFor(all, (e) => eventFieldValues(e, field))])),
    [all],
  );
  const laneEvents = useMemo(() => toLaneEvents(all.filter((e) => includeHidden || !isHidden(e)), isError), [all, includeHidden, isError, isHidden]);
  const cursorTime = atEnd ? null : (all[index]?.time ?? null);

  // ---- 선택
  const byUid = useMemo(() => new Map(all.map((e, i) => [e.uid, { e, i }] as const)), [all]);
  const selected = selectedUid === null ? undefined : byUid.get(selectedUid);
  useEffect(() => {
    if (selectedUid !== null && selected !== undefined && selected.i > index) setSelectedUid(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, selectedUid, selected?.i]);

  // ---- 흐름 패널
  const [flowSaved, setFlowSaved] = useState(() => storage.get(LOGS_STORAGE.flowCollapsed) === "1");
  // 표 공간이 모자라 자동으로 접은 상태(저장하지 않는다). 사용자가 직접 펴면 다시 자동으로 접지 않는다.
  const [flowAuto, setFlowAuto] = useState(false);
  const [flowUserOpened, setFlowUserOpened] = useState(false);
  const flowCollapsed = flowSaved || flowAuto;
  const [flowView, setFlowView] = useState<FlowView>("lane");
  const effectiveFlowView: FlowView = traceVisible ? flowView : "lane";
  const trace = useLogTrace(session, traceVisible && !flowCollapsed && effectiveFlowView === "trace");
  const toggleFlow = () => {
    if (flowCollapsed) {
      setFlowUserOpened(true);
      setFlowAuto(false);
      setFlowSaved(false);
      storage.set(LOGS_STORAGE.flowCollapsed, "0");
    } else {
      setFlowSaved(true);
      storage.set(LOGS_STORAGE.flowCollapsed, "1");
    }
  };
  const [flowH, setFlowH] = useState(() => clampOr(readNumber(storage.get(LOGS_STORAGE.flowHeight), LOGS_LIMITS.flowHeightDefault), LOGS_LIMITS.flowHeightMin, LOGS_LIMITS.flowHeightMax, LOGS_LIMITS.flowHeightDefault));
  const setFlowHeight = (n: number) => {
    setFlowH(n);
    storage.set(LOGS_STORAGE.flowHeight, String(n));
  };

  // ---- 상세 패널 폭
  const [detailW, setDetailW] = useState(() => readNumber(storage.get(LOGS_STORAGE.detailWidth), LOGS_LIMITS.detailWidthDefault));
  const setWidth = (n: number) => {
    setDetailW(n);
    storage.set(LOGS_STORAGE.detailWidth, String(n));
  };

  // ---- 열 구성 / 메뉴
  const [cols, setCols] = useColumnChoice(LOGS_STORAGE.colsSession, EVENT_COLUMN_IDS, SESSION_EVENT_COLUMNS_DEFAULT);
  const columns = useMemo(() => eventColumns(cols), [cols]);
  const [menu, setMenu] = useState<{ items: readonly LogMenuItem[]; anchor: RowMenuAnchor; note?: string } | null>(null);
  const tableWrapRef = useRef<HTMLDivElement>(null);
  const tableH = useElementHeight(tableWrapRef, 360);
  if (shouldAutoFoldFlow({ tableHeight: tableH, minRows: LOGS_LIMITS.tableMinRows, rowHeight: LOGS_LIMITS.tableRowHeight, collapsed: flowCollapsed, userOpened: flowUserOpened })) setFlowAuto(true);
  const { tableRef: eventTableRef, panelRef: detailPanelRef, onActivate: activateEvent, reveal: revealEvent } = useDetailLink(selectedUid);
  const searchRef = useRef<HTMLInputElement>(null);

  const copy = (text: string) => void navigator.clipboard?.writeText(text).then(() => toast({ tone: "success", text: t.copied, durationMs: 2000 }));
  const setLane = (id: string) => url.setScreen({ [SCREEN_PARAMS.lane]: laneFilter.includes(id) ? laneFilter.filter((x) => x !== id) : [...laneFilter, id] });
  const openRowMenu = (uid: string, anchor: RowMenuAnchor) => {
    const hit = byUid.get(uid);
    if (hit === undefined) return;
    const e = hit.e;
    const items: LogMenuItem[] = [
      { id: "open", label: t.detail.openDetail, onSelect: () => setSelectedUid(uid) },
      { id: "through", label: t.detail.throughHere, onSelect: () => playback.seek(hit.i) },
      { id: "lane", label: t.detail.onlyThisLane, onSelect: () => url.setScreen({ [SCREEN_PARAMS.lane]: laneOf(e) || null }), disabled: laneOf(e) === "" },
      { id: "call", label: t.detail.sameCall, onSelect: () => url.setFilter(withValues(url.filter, FILTER_KEYS.callId, e.call_id ? [e.call_id] : [])), disabled: !e.call_id },
      { id: "copy", label: t.detail.copyUid, onSelect: () => copy(uid) },
      { id: "search", label: t.detail.openInSearch, onSelect: () => void navigate(`/logs/search?${FILTER_KEYS.session}=${encodeURIComponent(session)}#e=${encodeURIComponent(uid)}`) },
    ];
    setMenu({ items, anchor });
  };
  const openArchiveMenu = (el: HTMLElement | null) => {
    const r = el?.getBoundingClientRect();
    setMenu({
      anchor: { x: r?.left ?? 0, y: r?.bottom ?? 0, element: el ?? undefined },
      items: [
        { id: "html", label: `${t.sessions.archive} — ${t.sessions.archiveHtml}`, onSelect: () => void download(archiveFilterFor(session), "html") },
        { id: "json", label: `${t.sessions.archive} — ${t.sessions.archiveJson}`, onSelect: () => void download(archiveFilterFor(session), "json") },
      ],
      note: t.sessions.archiveOffline,
    });
  };

  const speeds = [0.5, 1, 2, 5, 10, 30];
  const changeSpeed = (s: number) => {
    playback.setSpeed(s);
    storage.set(LOGS_STORAGE.speed, String(s));
  };
  const changeSkip = (v: boolean) => {
    playback.setSkipGaps(v);
    storage.set(LOGS_STORAGE.skipGaps, v ? "1" : "0");
  };
  useShortcuts([
    { id: "logs.s.play", scope: LOGS_SCOPES.session, keys: "k", titleKey: "shortcuts.logsPlayToggle", run: playback.toggle },
    { id: "logs.s.prev", scope: LOGS_SCOPES.session, keys: ",", titleKey: "shortcuts.logsStepBack", run: () => playback.step(-1) },
    { id: "logs.s.next", scope: LOGS_SCOPES.session, keys: ".", titleKey: "shortcuts.logsStepForward", run: () => playback.step(1) },
    { id: "logs.s.slower", scope: LOGS_SCOPES.session, keys: "[", titleKey: "shortcuts.logsSpeedDown", run: () => changeSpeed(nextSpeed(speeds, playback.speed, -1)) },
    { id: "logs.s.faster", scope: LOGS_SCOPES.session, keys: "]", titleKey: "shortcuts.logsSpeedUp", run: () => changeSpeed(nextSpeed(speeds, playback.speed, 1)) },
    { id: "logs.s.errors", scope: LOGS_SCOPES.session, keys: "e", titleKey: "shortcuts.logsErrorsOnly", run: () => setErrorsOnly((v) => !v) },
    { id: "logs.s.flow", scope: LOGS_SCOPES.session, keys: "t", titleKey: "shortcuts.logsToggleFlow", run: toggleFlow },
    { id: "logs.s.view", scope: LOGS_SCOPES.session, keys: "v", titleKey: "shortcuts.logsFlowView", run: () => traceVisible && setFlowView((v) => (v === "lane" ? "trace" : "lane")) },
    { id: "logs.s.detail", scope: LOGS_SCOPES.session, keys: "d", titleKey: "shortcuts.logsToggleDetail", run: () => selectedUid !== null && setSelectedUid(null) },
    { id: "logs.s.search", scope: LOGS_SCOPES.session, keys: "/", titleKey: "shortcuts.logsFocusSearch", run: () => searchRef.current?.focus() },
    { id: "logs.s.chips", scope: LOGS_SCOPES.session, keys: "f", titleKey: "shortcuts.logsCategoryFocus", run: () => focusLogControl("categoryChips") },
  ]);

  const summary = timeline?.session;
  const notFound = tl.isError && (tl.error as { status?: number } | null)?.status === 404;
  const body = (() => {
    if (notFound)
      return (
        <div className="logs-empty" role="alert">
          <h2 className="app-block-title">{t.detail.notFoundTitle}</h2>
          <p>{t.detail.notFoundBody}</p>
          <Link className="logs-linkbtn" to="/logs/sessions">{t.detail.backToList}</Link>
        </div>
      );
    if (tl.isError && timeline === undefined) {
      const e = errorBlockOf(tl.error, t.loadFailed);
      return <ErrorBlock title={t.loadFailed} message={e.message} {...(e.detail === undefined ? {} : { details: e.detail })} detailsLabel={t.detailsLabel} retryLabel={t.retry} onRetry={() => void tl.refetch()} />;
    }
    return null;
  })();
  if (body !== null) {
    return (
      <LogsPageFrame tab="sessions" title={t.docTitle.session(session.slice(0, 8))}>
        {body}
      </LogsPageFrame>
    );
  }

  const hasHiddenCategories = hiddenIds.length > 0;
  const emptyRows = rows.length === 0;
  const detailOpen = selectedUid !== null;
  const durationMs = summary?.first_time != null && summary?.last_time != null ? Math.max(0, (summary.last_time - summary.first_time) * 1000) : null;
  const clearFilters = () => {
    setErrorsOnly(false);
    url.setFilter({});
    url.setScreen({ [SCREEN_PARAMS.lane]: null });
  };

  return (
    <LogsPageFrame
      tab="sessions"
      title={t.docTitle.session(session.slice(0, 8))}
      status={<span className="app-muted" role="status">{tl.isFetching && !tl.isPending ? t.refreshing : ""}</span>}
      actions={<Button size="sm" onClick={() => void tl.refetch()}>{t.refresh} ⟳</Button>}
    >
      <div
        className="logs-session"
        data-detail={detailOpen ? "open" : "closed"}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !e.defaultPrevented && laneFilter.length > 0) url.setScreen({ [SCREEN_PARAMS.lane]: null });
        }}
      >
        <div className="logs-session-main">
          <header className="logs-session-head">
            <div className="logs-session-line">
              <Link className="logs-linkbtn" to="/logs/sessions" aria-label={t.detail.backToList}>← {t.detail.back}</Link>
              <span className="app-muted">/</span>
              <code className="logs-mono" title={session}>{session.length > 8 ? `${session.slice(0, 8)}…` : session}</code>
              <IconButton label={t.detail.copySession} icon={<span aria-hidden="true">⧉</span>} size="sm" onClick={() => copy(session)} />
              {summary === undefined ? (
                <span className="app-skeleton-row logs-skel-inline" aria-hidden="true" />
              ) : (
                <span className="logs-summary app-wrap">
                  {summary.project ? `${t.detail.project} ${summary.project.label || summary.project.id}` : null}
                  {summary.models && summary.models.length > 0 ? ` · ${summary.models.join(", ")}` : null}
                  {` · ${t.detail.events} ${(summary.events ?? all.length).toLocaleString("ko-KR")}`}
                  {` · ${t.detail.errors} ${errorCount}`}
                  {summary.tokens?.total != null ? ` · ${t.detail.tokens} ${summary.tokens.total.toLocaleString("ko-KR")}` : null}
                </span>
              )}
              <span className="logs-spacer" />
              <Button size="sm" aria-haspopup="menu" onClick={(e) => openArchiveMenu(e.currentTarget)}>{t.sessions.archive} ▾</Button>
            </div>
            {summary === undefined ? null : (
              <div className="logs-session-line app-muted">
                <span>{t.detail.start} {summary.first_time != null ? new Date(summary.first_time * 1000).toLocaleString("ko-KR") : "–"}</span>
                {durationMs !== null ? <span> · {t.detail.length} {Math.round(durationMs / 1000)}초</span> : null}
                {summary.thread_count != null ? <span> · {t.detail.agents} {summary.thread_count}</span> : null}
              </div>
            )}
          </header>

          {all.length > LOGS_LIMITS.bigSessionWarn ? <Banner tone="info" className="logs-banner">{t.detail.big}</Banner> : null}
          {timeline?.truncated ? <Banner tone="info" className="logs-banner">{t.detail.loadMoreNote(all.length)}</Banner> : null}
          {liveBanner && !live ? (
            <Banner
              tone="info"
              className="logs-banner"
              actions={
                <Button
                  size="sm"
                  onClick={() => {
                    setLiveBanner(false);
                    setPos(null);
                    url.setScreen({ [SCREEN_PARAMS.through]: null });
                    void tl.refetch();
                  }}
                >
                  {t.detail.liveAction}
                </Button>
              }
            >
              {t.detail.liveBanner}
            </Banner>
          ) : null}

          <PlaybackBar
            events={all}
            index={index}
            onIndexChange={playback.seek}
            playing={playback.playing}
            onPlayingChange={(p) => (p ? playback.play() : playback.pause())}
            speed={playback.speed}
            onSpeedChange={changeSpeed}
            skipGaps={playback.skipGaps}
            onSkipGapsChange={changeSkip}
            errorIndexes={errorIndexes}
            originTime={origin}
            describe={(i) => all[i]?.title ?? ""}
            ended={playback.ended}
            maxTicks={LOGS_LIMITS.maxErrorTicks}
          />

          <section className="logs-flow" data-collapsed={flowCollapsed ? "true" : undefined} aria-label={t.detail.flowPanel}>
            <div className="logs-flow-head">
              <Button size="sm" aria-expanded={!flowCollapsed} onClick={toggleFlow}>{flowCollapsed ? t.detail.flowToggleShow : t.detail.flowToggleHide}</Button>
              {traceVisible && !flowCollapsed ? <FlowSegments view={effectiveFlowView} onChange={setFlowView} /> : null}
            </div>
            {flowCollapsed ? null : (
              <>
              <div className="logs-flow-body" style={{ maxHeight: flowH }}>
                <SessionFlow
                  view={effectiveFlowView}
                  lanes={lanes}
                  laneLabelFor={(id) => labels.get(id) ?? id}
                  events={laneEvents}
                  cursorTime={cursorTime}
                  trace={{ data: trace.data, loading: trace.isPending, error: trace.error, refetch: () => void trace.refetch() }}
                  taxonomy={taxonomy}
                  selectedUid={selectedUid}
                  onSelectEvent={(uid) => setSelectedUid(uid)}
                  onSelectLane={setLane}
                  playing={playback.playing}
                  atEnd={atEnd}
                  lastTime={all.length > 0 ? (all[all.length - 1]?.time ?? null) : null}
                />
              </div>
              <SplitHandle orientation="horizontal" size={flowH} min={LOGS_LIMITS.flowHeightMin} max={LOGS_LIMITS.flowHeightMax} onChange={setFlowHeight} label={t.detail.flowSplitLabel} />
              </>
            )}
          </section>

          <div className="logs-filterrow">
            <LogFilters
              value={url.filter}
              onChange={url.setFilter}
              options={options}
              suggestions={suggestions}
              inputRef={searchRef}
              compact
              savedExtra={() => ({ errorsOnly, lanes: laneFilter })}
              onApplySavedExtra={(extra) => {
                setErrorsOnly(extra?.["errorsOnly"] === true);
                const l = extra?.["lanes"];
                url.setScreen({ [SCREEN_PARAMS.lane]: Array.isArray(l) ? (l as string[]) : null });
              }}
            />
            <CategoryChips
              items={chipItems}
              taxonomy={taxonomy}
              slotFor={slotFor}
              selected={valuesOf(url.filter, FILTER_KEYS.category)}
              onChange={(next) => url.setFilter(withValues(url.filter, FILTER_KEYS.category, next))}
            />
            <div className="logs-toggles">
              <label className="app-check"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />{t.detail.errorsOnly} ({errorCount})</label>
              <label className="app-check"><input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} />{t.detail.groupResponses}</label>
              {hasHiddenCategories ? <label className="app-check"><input type="checkbox" checked={includeHidden} onChange={(e) => setIncludeHidden(e.target.checked)} />{t.detail.includeHidden}</label> : null}
              {laneFilter.map((id) => (
                <span key={id} className="logs-chip">
                  {t.detail.laneChip(labels.get(id) ?? id)}
                  <button type="button" className="logs-chipx" aria-label={t.detail.removeLane(labels.get(id) ?? id)} onClick={() => setLane(id)}>×</button>
                </span>
              ))}
              <Button size="sm" onClick={() => { const next = timeMode === "relative" ? "absolute" : "relative"; setTimeMode(next); storage.set(LOGS_STORAGE.timeMode, next); }} aria-label={t.filters.timeMode} aria-pressed={timeMode === "absolute"}>⏱ {timeMode === "relative" ? t.filters.timeRelative : t.filters.timeAbsolute}</Button>
              <ColumnsMenu all={EVENT_COLUMN_IDS} selected={cols} labelOf={(id) => columns.find((c) => c.id === id)?.header?.toString() ?? eventColumns([id])[0]?.header?.toString() ?? id} onChange={setCols} />
            </div>
          </div>

          <div ref={tableWrapRef} className="logs-tablewrap" data-dim={tl.isError ? "true" : undefined}>
            {tl.isPending ? (
              <div className="app-loading" role="status" aria-busy="true">{all.length > LOGS_LIMITS.bigSessionProgress ? t.detail.loadingProgress(all.length) : t.loading}</div>
            ) : all.length === 0 ? (
              <p className="logs-empty">{hasHiddenCategories && !includeHidden ? `${t.detail.onlyHidden}` : t.detail.noEvents}{hasHiddenCategories && !includeHidden ? <Button size="sm" onClick={() => setIncludeHidden(true)}>{t.detail.includeHidden}</Button> : null}</p>
            ) : emptyRows ? (
              <div className="logs-empty">
                <p>{t.detail.noMatch(visible.length)}</p>
                <Button size="sm" onClick={clearFilters}>{t.clearFilters}</Button>
              </div>
            ) : (
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
                originTime={origin}
                groupByMessage={grouped}
                followLast={playback.playing || live ? follow : undefined}
                onFollowChange={setFollow}
                currentUid={all[index]?.uid ?? null}
                laneLabelFor={laneLabelFor}
                height={Math.max(160, tableH - 8)}
                ariaLabel={t.detail.ariaTable}
                renderCell={(id, row) =>
                  id === CELL_IDS.lane && laneOf(row) !== "" ? (
                    <button type="button" className="logs-linkbtn ac-ellipsis" tabIndex={-1} title={`${labels.get(laneOf(row)) ?? laneOf(row)} — ${t.detail.onlyThisLane}`} onClick={(ev) => { ev.stopPropagation(); setLane(laneOf(row)); }}>
                      {labels.get(laneOf(row)) ?? laneOf(row)}
                    </button>
                  ) : undefined
                }
              />
            )}
          </div>
        </div>

        {detailOpen && selectedUid !== null ? (
          <>
            <SplitHandle size={detailW} min={LOGS_LIMITS.detailWidthMin} max={LOGS_LIMITS.detailWidthMax} onChange={setWidth} label={t.detail.splitLabel} />
            <div className="logs-detail-col" style={{ width: detailW }}>
              <LogDetailPanel
                ref={detailPanelRef}
                uid={selectedUid}
                preview={selected?.e}
                taxonomy={taxonomy}
                isError={isError}
                originTime={origin}
                laneLabelFor={laneLabelFor}
                filteredOut={selected !== undefined && !rows.includes(selected.e)}
                width={detailW}
                onClose={() => setSelectedUid(null)}
                onOpenEvent={(uid, ses) => {
                  if (ses !== undefined && ses !== session) void navigate(`/logs/sessions/${encodeURIComponent(ses)}#e=${encodeURIComponent(uid)}`);
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
