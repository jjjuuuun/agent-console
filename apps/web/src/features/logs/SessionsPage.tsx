import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button, useShortcuts, useToast } from "@agent-console/ui";
import { SessionList, focusLogControl, hasActiveFilter, sessionColumns } from "@agent-console/log-view";
import { LinkPart, LINK_PART_IDS } from "../../modules";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useStorage } from "../../app/StorageContext";
import { Link } from "react-router";
import { LINK_ROLES, pathForRole } from "./routeLinks";
import { ColumnsMenu, useColumnChoice } from "./ColumnsMenu";
import { EmptyNoLogs, EmptyNoMatch, FirstUseCard, NewEventsBanner, OtherSourcesHint } from "./LogsEmpty";
import { LogFilters, buildFilterFields } from "./LogFilters";
import { LogMenu } from "./LogMenu";
import { LogsPageFrame } from "./LogsPageFrame";
import { RangeControl } from "./LogFilters";
import { useLogsIngested } from "./LogsLive";
import { DEFAULT_RANGE, LOGS_LIMITS, LOGS_SCOPES, LOGS_STORAGE, SCREEN_PARAMS, SESSION_COLUMNS_DEFAULT, SESSION_COLUMN_IDS } from "./logsConfig";
import { errorBlockOf, fieldErrorsOf } from "./logsErrors";
import { classifyEmpty, enabledCount, parseRange, rangeToWindow, toRequestParams } from "./logsLib";
import { logsMessages as t } from "./messages";
import { useArchiveDownload } from "./archive";
import { useElementHeight } from "./useElementHeight";
import { useFilterOptions } from "./useFilterOptions";
import { useLogUrlState } from "./useLogFilterState";
import { useLogScan } from "./useLogScan";
import { logKeys, useAnyEvents, useLogSessions, useLogSources, useLogTaxonomyView } from "./useLogsApi";
import type { RowMenuAnchor } from "@agent-console/log-view";

const FIELDS = buildFilterFields();
const NO_SEEN: readonly string[] = [];

/** 세션 목록(`/logs/sessions`): 필터·기간·정렬(시작 시각)·열 구성·보관본·수집. 데이터는 `GET /logs/sessions`. */
export function SessionsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const storage = useStorage();
  const url = useLogUrlState(FIELDS);
  const sources = useLogSources();
  const taxonomy = useLogTaxonomyView();
  const options = useFilterOptions(taxonomy, NO_SEEN);
  const scan = useLogScan(sources.data);
  const download = useArchiveDownload();
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [anchor, setAnchor] = useState(() => Date.now());
  const [newCount, setNewCount] = useState(0);
  const [menu, setMenu] = useState<{ id: string; anchor: RowMenuAnchor } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const activeSession = useRef<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const height = useElementHeight(wrapRef, 480);
  const [cols, setCols] = useColumnChoice(LOGS_STORAGE.colsSessions, SESSION_COLUMN_IDS, SESSION_COLUMNS_DEFAULT);
  const columns = useMemo(() => sessionColumns(cols), [cols]);

  const rangeValue = url.screen[SCREEN_PARAMS.range]?.[0];
  const range = parseRange(rangeValue, DEFAULT_RANGE.sessions);
  const window = rangeToWindow(range, anchor);
  const params = useMemo(() => toRequestParams(url.filter, { order, limit: LOGS_LIMITS.sessionsPage }, window), [url.filter, order, window.since, window.until]); // eslint-disable-line react-hooks/exhaustive-deps
  const q = useLogSessions(params);
  const list = q.data ?? [];
  const fieldErrors = useMemo(() => fieldErrorsOf(q.error), [q.error]);
  const hasServerFilterError = Object.keys(fieldErrors).length > 0;
  const total0 = useAnyEvents(q.data !== undefined && list.length === 0 && sources.data !== undefined && enabledCount(sources.data) > 0);

  const refresh = () => {
    setAnchor(Date.now());
    setNewCount(0);
    void qc.invalidateQueries({ queryKey: logKeys.root });
  };
  // 수집 알림: 시작 시각 내림차순이면 자동 재조회, 아니면 배너(스크롤·선택 유지)
  useLogsIngested(
    ({ count }) => {
      if (order === "desc") void qc.invalidateQueries({ queryKey: ["logs", "sessions"] });
      else setNewCount((n) => n + count);
    },
    LOGS_LIMITS.liveDebounceMs,
  );

  const copyId = (id: string) => {
    void navigator.clipboard?.writeText(id).then(() => toast({ tone: "success", text: t.copied, durationMs: 2000 }));
  };
  useShortcuts([
    { id: "logs.search", scope: LOGS_SCOPES.common, keys: "/", titleKey: "shortcuts.logsFocusSearch", run: () => searchRef.current?.focus() },
    { id: "logs.filter", scope: LOGS_SCOPES.common, keys: "f", titleKey: "shortcuts.logsFocusFilter", run: () => focusLogControl("filterBar") },
    { id: "logs.refresh", scope: LOGS_SCOPES.common, keys: "r", titleKey: "shortcuts.logsRefresh", run: refresh },
    { id: "logs.scan", scope: LOGS_SCOPES.common, keys: "Shift+R", titleKey: "shortcuts.logsScan", run: () => void scan.run() },
    {
      id: "logs.copyId",
      scope: LOGS_SCOPES.common,
      keys: "c",
      titleKey: "shortcuts.libCopyId",
      run: () => {
        const id = activeSession.current;
        if (id) copyId(id);
      },
    },
  ]);

  const open = (id: string) => {
    storage.set(LOGS_STORAGE.openedSession, "1");
    void navigate(`/logs/sessions/${encodeURIComponent(id)}`);
  };
  const filtered = hasActiveFilter(url.filter);
  const defaultRange = rangeValue === undefined || rangeValue === DEFAULT_RANGE.sessions;
  const clearFilters = () => url.setFilter({});
  const showAllRange = () => url.setScreen({ [SCREEN_PARAMS.range]: "all" });
  const anyEnabled = enabledCount(sources.data) > 0;

  let body;
  if (q.isError && q.data === undefined && !hasServerFilterError) {
    const e = errorBlockOf(q.error, t.loadFailed);
    body = <ErrorBlock title={t.loadFailed} message={e.message} {...(e.detail === undefined ? {} : { details: e.detail })} detailsLabel={t.detailsLabel} retryLabel={t.retry} onRetry={() => void q.refetch()} />;
  } else if (sources.data !== undefined && q.data !== undefined && list.length === 0 && !filtered && classifyEmpty(sources.data, undefined) === "A") {
    body = <FirstUseCard sources={sources.data} />;
  } else if (q.data !== undefined && list.length === 0 && sources.data !== undefined) {
    const kind = filtered || !defaultRange ? "C" : classifyEmpty(sources.data, total0);
    body = kind === "B" ? <EmptyNoLogs sources={sources.data} scanning={scan.scanning} onScan={() => void scan.run()} /> : <EmptyNoMatch onClearFilters={filtered ? clearFilters : undefined} onAllRange={defaultRange ? showAllRange : undefined} />;
  } else {
    body = (
      <>
        <SessionList
          onActiveChange={(id) => {
            activeSession.current = id;
          }}
          sessions={list}
          columns={columns}
          order={order}
          onOrderChange={setOrder}
          onOpen={open}
          onRowMenu={(id, a) => setMenu({ id, anchor: a })}
          loading={q.isPending}
          limitReached={list.length >= LOGS_LIMITS.sessionsPage}
          limit={LOGS_LIMITS.sessionsPage}
          height={Math.max(160, height - 64)}
          sourceLabelFor={(id) => sources.data?.find((s) => s.descriptor.id === id)?.descriptor.title}
          renderTokenExtra={() => (
            <LinkPart id={LINK_PART_IDS.logsUsageLink}>
              <Link className="logs-linkbtn" to={pathForRole(LINK_ROLES.usage)} title={t.sessions.toUsage} aria-label={t.sessions.toUsage} onClick={(e) => e.stopPropagation()}> ↗</Link>
            </LinkPart>
          )}
        />
      </>
    );
  }

  const menuItems = (id: string) => [
    { id: "open", label: t.sessions.openSession, onSelect: () => open(id) },
    { id: "copy", label: t.sessions.copyId, onSelect: () => copyId(id) },
    { id: "search", label: t.sessions.onlyThisSession, onSelect: () => void navigate(`/logs/search?session=${encodeURIComponent(id)}`) },
    { id: "html", label: `${t.sessions.archive} — ${t.sessions.archiveHtml}`, separator: true, onSelect: () => void download({ session: id }, "html") },
    { id: "json", label: `${t.sessions.archive} — ${t.sessions.archiveJson}`, onSelect: () => void download({ session: id }, "json") },
  ];

  return (
    <LogsPageFrame
      tab="sessions"
      status={<span className="app-muted" role="status">{scan.scanning ? t.scanning : q.isFetching && !q.isPending ? t.refreshing : ""}</span>}
      actions={
        <>
          <Button size="sm" onClick={refresh}>{t.refresh} ⟳</Button>
          {anyEnabled ? <Button size="sm" loading={scan.scanning} onClick={() => void scan.run()}>{t.scan}</Button> : null}
        </>
      }
    >
      {list.length > 0 ? <OtherSourcesHint sources={sources.data} /> : null}
      {newCount > 0 ? <NewEventsBanner text={t.sessions.newEvents(newCount)} action={t.sessions.reloadBanner} onAction={refresh} /> : null}
      <div className="logs-toolbar">
        <LogFilters
          value={url.filter}
          onChange={url.setFilter}
          options={options}
          fieldErrors={fieldErrors}
          inputRef={searchRef}
          trailing={<RangeControl value={rangeValue} fallbackId={DEFAULT_RANGE.sessions} onChange={(v) => url.setScreen({ [SCREEN_PARAMS.range]: v })} />}
        />
        {url.unknown.length > 0 ? <span className="app-muted" role="status">{t.filters.unknownError}: {url.unknown.join(", ")}</span> : null}
      </div>
      <div className="logs-subhead">
        <span className="app-muted" aria-live="polite">{q.data === undefined ? "" : t.sessions.count(list.length)}</span>
        <ColumnsMenu all={SESSION_COLUMN_IDS} selected={cols} labelOf={(id) => sessionColumns([id])[0]?.header?.toString() ?? id} onChange={setCols} />
      </div>
      <div ref={wrapRef} className="logs-tablewrap" data-dim={q.isError && q.data !== undefined ? "true" : undefined}>
        {body}
      </div>
      {menu === null ? null : <LogMenu label={t.sessions.rowMenu} anchor={menu.anchor} items={menuItems(menu.id)} footnote={t.sessions.archiveOffline} onClose={() => setMenu(null)} />}
    </LogsPageFrame>
  );
}

