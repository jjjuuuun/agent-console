import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router";
import { Banner, Button, Disclosure, EmptyState, PageHeader, useShortcuts } from "@agent-console/ui";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { lookupMessage, messages as appMessages } from "../../app/messages";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { queryKeys, useApiQuery, useWorkspaceSettings } from "../../app/queries";
import { useNow } from "../../app/useNow";
import { formatRelative } from "../../lib/format";
import { AccountWideNote } from "../projects";
import { RollupPanel, buildLinesByView } from "./RollupPanel";
import { SourcesPanel } from "./SourcesPanel";
import { UsageSetupGuide, type SetupGuideState } from "./UsageSetupGuide";
import { WindowCard } from "./WindowCard";
import { usageMessages as t } from "./messages";
import { OFFICIAL_TRUST, USAGE_POLL_MS, USAGE_REPORT_KEY, USAGE_SOURCES_KEY, USAGE_ROLLUP_PERIODS, USAGE_ROLLUP_VIEWS, USAGE_SETUP_HASH, DEFAULT_ROLLUP_PERIOD, DEFAULT_ROLLUP_VIEW } from "./usageConfig";
import { buildWindowGroups, plainText, filterRollupByDays, sourceIndex, windowDisplayName, windowNameIndex, type RollupDimension } from "./usageLib";
import "./usage.css";

const NO_SOURCES: readonly string[] = [];
const usageKey = USAGE_REPORT_KEY;
const sourcesKey = USAGE_SOURCES_KEY;

/** 사용량 화면(컨테이너): `/usage`·`/usage/sources`·공통 설정(`usage`)을 읽어 카드·집계·출처 패널에 나눠 준다. */
export function UsageScreen() {
  const qc = useQueryClient();
  const report = useApiQuery(usageKey, (rest) => rest.getUsage(), { refetchInterval: USAGE_POLL_MS });
  const sources = useApiQuery(sourcesKey, (rest) => rest.listUsageSources(), { refetchInterval: USAGE_POLL_MS });
  // 플랫폼 실행분 토큰 집계는 사용량-실행 연동이 켜져 있을 때만 있다. 꺼졌으면 집계 자리에 안내 한 줄만 남고,
  // 집계 이름 표시에만 쓰던 목록(에이전트·팀 구성)도 부르지 않는다.
  const rollupPart = useLinkPart(LINK_PART_IDS.usageTokenRollup);
  const settings = useWorkspaceSettings();
  const agents = useApiQuery(queryKeys.list("agents"), (rest) => rest.listAgents(), { enabled: rollupPart.visible });
  const graphs = useApiQuery(queryKeys.list("graphs"), (rest) => rest.listGraphs(), { enabled: rollupPart.visible });
  const [view, setView] = useState<RollupDimension>(DEFAULT_ROLLUP_VIEW);
  const [period, setPeriod] = useState(DEFAULT_ROLLUP_PERIOD);
  const nowMs = useNow(true, 1000);
  // 연결 안내 펼침: 사용자가 정한 값이 우선, 없으면 "값이 전혀 없을 때만 펼침". 값이 생기면 자동으로 접는다.
  const wantSetup = useLocation().hash === USAGE_SETUP_HASH;
  const [guideOpen, setGuideOpen] = useState<Readonly<Record<string, boolean>>>({});

  const usageSettings = settings.data?.value.usage;
  const labels = usageSettings?.window_labels ?? {};
  const rawOrder = usageSettings?.primary_source_order;
  const order = useMemo(() => rawOrder ?? NO_SOURCES, [rawOrder]);
  const staleAfter = usageSettings?.stale_after_seconds ?? null;
  const index = useMemo(() => sourceIndex(sources.data ?? []), [sources.data]);
  const windowInfo = useMemo(() => windowNameIndex(sources.data ?? []), [sources.data]);
  const sourceInfo = (id: string) => {
    const d = index.get(id)?.descriptor;
    return { title: d?.title ?? id, trust: d?.trust ?? "" };
  };

  const groups = useMemo(
    () => buildWindowGroups(report.data?.windows ?? [], order, (id) => index.get(id)?.descriptor.trust === OFFICIAL_TRUST),
    [report.data?.windows, order, index],
  );
  const latestBySource = useMemo(() => {
    const map = new Map<string, number>();
    for (const w of report.data?.windows ?? []) map.set(w.source, Math.max(map.get(w.source) ?? 0, w.observed_at));
    return map;
  }, [report.data?.windows]);
  const observedSources = useMemo(() => new Set(latestBySource.keys()), [latestBySource]);

  const setupSources = useMemo(
    () => (sources.data ?? []).filter((s) => s.enabled !== false && s.descriptor.needs_setup === true && (s.descriptor.setup_snippets?.length ?? 0) > 0),
    [sources.data],
  );
  const connectedIds = useMemo(
    () => new Set(setupSources.filter((s) => observedSources.has(s.descriptor.id) || s.last_received_at != null).map((s) => s.descriptor.id)),
    [setupSources, observedSources],
  );
  const wasConnected = useRef<ReadonlySet<string>>(new Set());
  useEffect(() => {
    const fresh = [...connectedIds].filter((id) => !wasConnected.current.has(id));
    wasConnected.current = connectedIds;
    if (fresh.length > 0) setGuideOpen((prev) => ({ ...prev, ...Object.fromEntries(fresh.map((id) => [id, false])) }));
  }, [connectedIds]);

  const periodDays = USAGE_ROLLUP_PERIODS.find((p) => p.id === period)?.days ?? null;
  const dayKey = new Date(nowMs).toDateString();
  const linesByView = useMemo(
    // 날짜가 바뀔 때만 다시 계산한다(dayKey).
    () => buildLinesByView(filterRollupByDays(report.data?.rollups ?? [], periodDays, new Date()), USAGE_ROLLUP_VIEWS),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report.data?.rollups, periodDays, dayKey],
  );

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["usage"] });
  };
  useShortcuts([{ id: "usage.refresh", scope: "usage", keys: "r", titleKey: "shortcuts.usageRefresh", run: refresh }]);

  const nameOf = (dim: RollupDimension, value: string | null): string => {
    if (value === null) return t.rollup.unnamed;
    if (dim === "agent_id") return agents.data?.find((a) => a.id === value)?.name ?? value;
    if (dim === "graph_id") return graphs.data?.find((g) => g.id === value)?.name ?? value;
    return value;
  };

  const fetching = report.isFetching || sources.isFetching;
  const updated = report.dataUpdatedAt > 0 ? Math.floor(report.dataUpdatedAt / 1000) : undefined;
  const header = (
    <PageHeader
      title={t.title}
      status={<><AccountWideNote /><span className="app-muted" aria-live="polite">{fetching ? t.refreshing : updated === undefined ? "" : t.lastUpdated(formatRelative(updated, nowMs))}</span></>}
      actions={<Button size="sm" loading={fetching && !report.isPending} onClick={refresh}>{t.refresh}</Button>}
    />
  );

  let cards;
  if (report.isPending) {
    cards = (
      <div className="usage-cards" role="status" aria-busy="true" aria-label={t.loading}>
        {[0, 1, 2].map((i) => <div key={i} className="usage-card app-skeleton-row" style={{ height: 140 }} />)}
      </div>
    );
  } else if (report.isError && report.data === undefined) {
    const e = describeError(report.error, t.loadFailed);
    cards = <ErrorBlock title={t.loadFailed} message={e.message} details={errorDetails(e)} detailsLabel={appMessages.common.details} retryLabel={appMessages.common.retry} onRetry={refresh} />;
  } else if (groups.length === 0) {
    // 값이 전혀 없을 때: 켜진 일반 출처마다 한 줄(설명). 시험용(test_only)은 출처 목록의 "개발용" 접힘에만 있다.
    const rows = (sources.data ?? []).filter((x) => x.enabled !== false && x.descriptor.test_only !== true);
    cards = (
      <EmptyState
        title={t.cards.empty}
        description={t.cards.emptyBody}
        action={
          <ul className="usage-empty-rows">
            {rows.map((x) => (
              <li key={x.descriptor.id}>
                <strong>{x.descriptor.title}</strong>
                {x.descriptor.description ? <span className="app-muted usage-empty-summary" title={plainText(x.descriptor.description)}>{plainText(x.descriptor.description)}</span> : null}
              </li>
            ))}
          </ul>
        }
      />
    );
  } else {
    cards = (
      <div className="usage-cards" role="list" aria-label={t.cards.region} data-dim={report.isError ? "true" : undefined}>
        {groups.map((g) => (
          <div role="listitem" key={g.window}>
            <WindowCard name={windowDisplayName(g.window, labels, windowInfo[g.window], sourceInfo(g.primary.source).title)} group={g} sourceInfo={sourceInfo} nowMs={nowMs} staleAfterSeconds={staleAfter} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="app-screen-frame" data-screen="usage">
      {header}
      <div className="app-screen-body usage-body">
        {report.isError && report.data !== undefined ? <Banner tone="warning">{t.staleData}</Banner> : null}
        {cards}
        {setupSources.length > 0 ? (
          <div className="usage-guides" id="setup">
            {setupSources.map((x) => {
              const id = x.descriptor.id;
              const connected = connectedIds.has(id);
              const state: SetupGuideState = connected ? "connected" : groups.length === 0 ? "empty" : "missing";
              return (
                <UsageSetupGuide
                  key={id}
                  snippets={x.descriptor.setup_snippets ?? []}
                  help={x.descriptor.setup_help}
                  note={t.hint}
                  state={state}
                  lastReceivedAt={x.last_received_at ?? latestBySource.get(id)}
                  nowMs={nowMs}
                  open={guideOpen[id] ?? (wantSetup || (!connected && groups.length === 0))}
                  onOpenChange={(o) => setGuideOpen((prev) => ({ ...prev, [id]: o }))}
                  onRecheck={refresh}
                  rechecking={fetching}
                />
              );
            })}
          </div>
        ) : null}
        {!rollupPart.visible ? (
          <p className="app-muted usage-rollup-off">{lookupMessage("linkPart.note.usageRollupOff")}</p>
        ) : (
        <>
        <p className="app-muted usage-rollup-note">{t.nestedNote}</p>
        <RollupPanel
          linesByView={linesByView}
          views={USAGE_ROLLUP_VIEWS}
          view={view}
          onViewChange={setView}
          periods={USAGE_ROLLUP_PERIODS.map((p) => p.id)}
          period={period}
          onPeriodChange={setPeriod}
          nameOf={nameOf}
          loading={report.isPending}
        />
        </>
        )}
        <section aria-labelledby="usage-sources-title" className="usage-sources-section">
          <h2 id="usage-sources-title" className="app-block-title">{t.sources.title}</h2>
          {sources.isError && sources.data === undefined ? (
            <ErrorBlock title={t.sources.loadFailed} retryLabel={appMessages.common.retry} onRetry={refresh} />
          ) : (
            <Disclosure summary={t.sources.summary(sources.data?.length ?? 0, (sources.data ?? []).filter((x) => x.enabled !== false).length)}>
              <SourcesPanel sources={sources.data ?? []} nowMs={nowMs} settingsHref="/settings#usage" hasObservation={(id) => observedSources.has(id)} latestObservedAt={(id) => latestBySource.get(id)} />
            </Disclosure>
          )}
        </section>
      </div>
    </div>
  );
}
