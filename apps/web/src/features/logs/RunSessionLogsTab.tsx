import { useLogTimeMode } from "./useLogTimeMode";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Banner, Button, useShortcuts } from "@agent-console/ui";
import { CategoryChips, LogEventTable, eventColumns, isErrorEvent, orderCategories, type LogFilterValue } from "@agent-console/log-view";
import type { LogEvent } from "@agent-console/contracts";
import { ErrorBlock } from "../../app/ErrorBlock";
import { LogDetailPanel } from "./LogDetailPanel";
import { useDetailLink } from "./useDetailLink";
import { LogsLiveProvider, useLogsIngested } from "./LogsLive";
import { settingsLogsHref } from "./LogsEmpty";
import { CELL_IDS, FILTER_KEYS, LOGS_LIMITS, RUN_TAB_COLUMNS, SEARCH_FIELD } from "./logsConfig";
import { errorBlockOf } from "./logsErrors";
import { categoryItems, originOf, toRequestParams, valuesOf, withValues } from "./logsLib";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";
import { useElementHeight } from "./useElementHeight";
import { useLogScan } from "./useLogScan";
import { useLogSources, useLogTaxonomyView, useRunLogPages } from "./useLogsApi";

export interface RunSessionLogsTabProps {
  runId: string;
  /** 실행이 진행 중인지(진행 중이면 새 이벤트를 1초 디바운스로 다시 읽고 "끝 따라가기"를 보인다) */
  running: boolean;
  /** 그래프에서 선택한 노드(`node_path`에 포함된 행을 강조한다) */
  selectedNodeId: string | null;
  /** 행을 선택하면 그 행의 노드를 그래프에서 선택하도록 알린다 */
  onSelectNode?: ((nodeId: string) => void) | undefined;
}

/** 이 화면 밖(실행 상세)에서도 쓰는 탭이라 수집 알림 구독을 직접 연다. */
export function RunSessionLogsTab(props: RunSessionLogsTabProps) {
  return (
    <LogsLiveProvider>
      <RunSessionLogs {...props} />
    </LogsLiveProvider>
  );
}

const NO_FILTER: LogFilterValue = {};

function RunSessionLogs({ runId, running, selectedNodeId, onSelectNode }: RunSessionLogsTabProps) {
  const qc = useQueryClient();
  const taxonomy = useLogTaxonomyView();
  const sources = useLogSources();
  const scan = useLogScan(sources.data);
  const [filter, setFilter] = useState<LogFilterValue>(NO_FILTER);
  const [q, setQ] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [follow, setFollow] = useState(true);
  const [selectedUidRaw, setSelectedUid] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const height = useElementHeight(wrapRef, 240, 120);
  const isError = useCallback((e: Pick<LogEvent, "category" | "tags">) => isErrorEvent(e, taxonomy), [taxonomy]);
  const composing = useRef(false);
  const params = useMemo(() => toRequestParams(filter, { [FILTER_KEYS.limit]: LOGS_LIMITS.runLogsPage }), [filter]);
  const pages = useRunLogPages(runId, params, true);
  useLogsIngested(() => void qc.invalidateQueries({ queryKey: ["logs", "run", runId] }), LOGS_LIMITS.runTabDebounceMs, running);

  const items = useMemo(() => (pages.data?.pages ?? []).flatMap((p) => p.items ?? []), [pages.data]);
  const total = pages.data?.pages[0]?.total ?? items.length;
  const sessions = useMemo(() => [...new Set(items.map((e) => e.session).filter((s): s is string => typeof s === "string" && s !== ""))], [items]);
  const rows = useMemo(() => (errorsOnly ? items.filter(isError) : items), [items, errorsOnly, isError]);
  const chips = useMemo(() => orderCategories(categoryItems(items, items), taxonomy), [items, taxonomy]);
  const origin = useMemo(() => originOf(items), [items]);
  const time = useLogTimeMode();
  const columns = useMemo(() => eventColumns(RUN_TAB_COLUMNS, undefined, time.widths), [time.widths]);
  const selected = selectedUidRaw === null ? undefined : items.find((e) => e.uid === selectedUidRaw);
  // 목록에서 사라진 행의 선택은 없는 것으로 본다
  const selectedUid = selected === undefined ? null : selectedUidRaw;
  const { tableRef: eventTableRef, panelRef: detailPanelRef, onActivate: activateEvent } = useDetailLink(selectedUid);
  const highlighted = useMemo(() => (selectedNodeId === null ? undefined : items.find((e) => (e.node_path ?? []).includes(selectedNodeId))), [items, selectedNodeId]);
  const hasFilter = Object.keys(filter).length > 0;

  const closeDetail = () => {
    setSelectedUid(null);
    requestAnimationFrame(() => eventTableRef.current?.focus());
  };
  const setCategories = (next: string[]) => setFilter(withValues(filter, FILTER_KEYS.category, next));
  const commitQ = (value: string) => setFilter(withValues(filter, SEARCH_FIELD, value === "" ? [] : [value]));
  useShortcuts([
    { id: "runs.logs.search", scope: "run-detail", keys: "/", titleKey: "shortcuts.logsFocusSearch", run: () => document.getElementById("logs-runtab-q")?.focus() },
    { id: "runs.logs.errors", scope: "run-detail", keys: "e", titleKey: "shortcuts.logsErrorsOnly", run: () => setErrorsOnly((v) => !v) },
  ]);

  const noSessions = pages.data !== undefined && items.length === 0 && !hasFilter;
  let body;
  if (pages.isError && pages.data === undefined) {
    const e = errorBlockOf(pages.error, t.runTab.loadFailed);
    body = <ErrorBlock title={t.runTab.loadFailed} message={e.message} {...(e.detail === undefined ? {} : { details: e.detail })} retryLabel={t.retry} onRetry={() => void pages.refetch()} />;
  } else if (noSessions) {
    body = (
      <div className="logs-empty" data-testid="logs-runtab-empty">
        <h3 className="app-block-title">{t.runTab.emptyTitle}</h3>
        <p>{t.runTab.emptyBody}</p>
        <div className="logs-empty-actions">
          <Button size="sm" loading={scan.scanning} onClick={() => void scan.run()}>{t.scan}</Button>
          <Link className="logs-linkbtn" to={settingsLogsHref()}>{t.empty.openSettings}</Link>
        </div>
      </div>
    );
  } else if (pages.data !== undefined && rows.length === 0) {
    body = (
      <div className="logs-empty">
        <p>{t.runTab.emptyFilter}</p>
        <Button size="sm" onClick={() => { setFilter(NO_FILTER); setQ(""); setErrorsOnly(false); }}>{t.clearFilters}</Button>
      </div>
    );
  } else {
    body = (
      <LogEventTable
        ref={eventTableRef}
        onActivate={activateEvent}
        rows={rows}
        columns={columns}
        density="compact"
        selectedUid={selectedUid}
        onSelect={(uid) => {
          setSelectedUid(uid);
          const e = items.find((x) => x.uid === uid);
          const node = e?.node_path?.[e.node_path.length - 1];
          if (node !== undefined) onSelectNode?.(node);
        }}
        taxonomy={taxonomy}
        isError={isError}
        slotFor={slotFor}
        timeMode={time.mode}
        onTimeModeChange={time.setMode}
        originTime={origin}
        loading={pages.isPending}
        hasMore={pages.hasNextPage}
        loadingMore={pages.isFetchingNextPage}
        onNearEnd={() => void pages.fetchNextPage()}
        highlight={(e) => selectedNodeId !== null && (e.node_path ?? []).includes(selectedNodeId)}
        followLast={running ? follow : undefined}
        onFollowChange={setFollow}
        height={Math.max(120, height - 8)}
        ariaLabel={t.runTab.tableLabel}
        renderCell={(id, row) =>
          id === CELL_IDS.time && sessions.length > 1 && row.session ? (
            <span className="ac-lv-num" title={row.session}>
              <span className="logs-sessiondot" aria-hidden="true" style={{ background: `var(--ac-cat-${slotFor(row.session) + 1})` }} />
              {row.session.slice(0, 4)}
            </span>
          ) : undefined
        }
      />
    );
  }

  const openInLogs =
    sessions.length === 1 ? (
      <Link className="logs-linkbtn" to={`/logs/sessions/${encodeURIComponent(sessions[0] ?? "")}`}>{t.runTab.openInLogs}</Link>
    ) : sessions.length > 1 ? (
      <Link className="logs-linkbtn" to={`/logs/search?${FILTER_KEYS.runId}=${encodeURIComponent(runId)}`}>{t.runTab.openInLogs}</Link>
    ) : null;

  return (
    <div className="logs-runtab">
      <Banner tone="info" className="logs-runtab-explain">{t.runTab.explain}</Banner>
      {!noSessions ? (
        <>
          <div className="logs-runtab-sessions">
            <span>{t.runTab.sessions(sessions.length)}</span>
            {sessions.slice(0, 3).map((s) => (
              <Link key={s} className="logs-linkbtn logs-mono" to={`/logs/sessions/${encodeURIComponent(s)}`} title={s}>{s.slice(0, 8)} ↗</Link>
            ))}
            {sessions.length > 3 ? <span className="app-muted">{t.runTab.sessionsMore(sessions.length - 3)}</span> : null}
            <span className="app-muted">{t.runTab.events(total)}</span>
            <span className="logs-spacer" />
            {openInLogs}
          </div>
          <div className="logs-runtab-filters">
            <input
              id="logs-runtab-q"
              type="search"
              className="logs-input"
              aria-label={t.filters.labels[SEARCH_FIELD] ?? SEARCH_FIELD}
              placeholder={t.filters.labels[SEARCH_FIELD] ?? ""}
              maxLength={LOGS_LIMITS.searchMaxLength}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onCompositionStart={() => (composing.current = true)}
              onCompositionEnd={(e) => {
                composing.current = false;
                setQ(e.currentTarget.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !composing.current) commitQ(q);
              }}
              onBlur={() => !composing.current && q !== (valuesOf(filter, SEARCH_FIELD)[0] ?? "") && commitQ(q)}
            />
            <CategoryChips items={chips} taxonomy={taxonomy} slotFor={slotFor} selected={valuesOf(filter, FILTER_KEYS.category)} onChange={setCategories} maxInline={6} />
            <label className="app-check"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />{t.runTab.errorsOnly}</label>
            {running ? <label className="app-check"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />{t.runTab.follow}</label> : null}
            {highlighted !== undefined ? <Button size="sm" onClick={() => setSelectedUid(highlighted.uid)}>{t.runTab.toNode}</Button> : null}
          </div>
        </>
      ) : null}
      <div ref={wrapRef} className="logs-tablewrap logs-runtab-table" data-dim={pages.isError && pages.data !== undefined ? "true" : undefined}>
        {body}
      </div>
      {selectedUid !== null ? (
        <section className="logs-runtab-drawer" aria-label={t.runTab.drawerTitle}>
          <div className="logs-runtab-drawer-head">
            <strong>{t.runTab.drawerTitle}</strong>
            {selected?.session ? <Link className="logs-linkbtn" to={`/logs/sessions/${encodeURIComponent(selected.session)}#e=${encodeURIComponent(selectedUid)}`}>{t.runTab.seeInLogs}</Link> : null}
          </div>
          <LogDetailPanel
            ref={detailPanelRef}
            uid={selectedUid}
            preview={selected}
            taxonomy={taxonomy}
            isError={isError}
            originTime={origin}
            laneLabelFor={() => undefined}
            tabs={["overview", "detail", "raw"]}
            drawer={false}
            onClose={closeDetail}
            onOpenEvent={() => undefined}
          />
        </section>
      ) : null}
    </div>
  );
}
