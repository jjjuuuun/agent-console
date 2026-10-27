import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Switch } from "@agent-console/ui";
import { isErrorEvent } from "@agent-console/log-view";
import type { LogEvent } from "@agent-console/contracts";
import { useStorage } from "../../app/StorageContext";
import { ARCH_RUN_HEIGHT, ARCH_RUN_SCOPE, ARCH_STORAGE, ArchitectureChips, ArchitectureDialog, ArchitecturePanel, archMessages, observedValue, useArchitectureController } from "../architecture";
import { RunArchitectureEvents, NO_RUN_EVENT_FILTERS, type RunEventFilters } from "./RunArchitectureEvents";
import { settingsLogsHref } from "./LogsEmpty";
import { useLogsIngested, LogsLiveProvider } from "./LogsLive";
import { LOGS_LIMITS } from "./logsConfig";
import { clampOr } from "./logsLib";
import { LINK_ROLES, pathForRole } from "./routeLinks";
import { SplitHandle } from "./SplitHandle";
import { useLogEventPages, useLogSchema, useLogTaxonomyView } from "./useLogsApi";

export interface RunArchitectureTabProps {
  runId: string;
  /** 실행이 진행 중인지(진행 중이면 새 이벤트마다 1초 디바운스로 다시 질의한다) */
  running: boolean;
  /** 자식 실행이 있는가([자식 실행 포함] 스위치는 있을 때만 보인다) */
  hasChildren: boolean;
  /** 실행 이벤트가 올 때마다 바뀌는 값(예: 마지막 seq). 로그 수집 알림과 함께 다시 질의하는 신호다. */
  refreshKey?: number | string | undefined;
}

/** 실행 상세 검사 패널의 [구조도] 탭. 수집 알림 구독을 직접 연다(실행 상세는 로그 화면 밖이다). */
export function RunArchitectureTab(props: RunArchitectureTabProps) {
  return (
    <LogsLiveProvider>
      <RunArchitecture {...props} />
    </LogsLiveProvider>
  );
}

function RunArchitecture({ runId, running, hasChildren, refreshKey }: RunArchitectureTabProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const storage = useStorage();
  const taxonomy = useLogTaxonomyView();
  const [tree, setTree] = useState(false);
  const includeChildren = tree && hasChildren;
  const [filters, setFilters] = useState<RunEventFilters>(NO_RUN_EVENT_FILTERS);
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [canvasH, setCanvasH] = useState(() => clampOr(Number.parseFloat(storage.get(ARCH_STORAGE.runHeight) ?? ""), ARCH_RUN_HEIGHT.min, ARCH_RUN_HEIGHT.max, ARCH_RUN_HEIGHT.default));
  const changeHeight = (n: number) => {
    setCanvasH(n);
    storage.set(ARCH_STORAGE.runHeight, String(n));
  };
  const expandRef = useRef<HTMLButtonElement>(null);
  const focusTable = useRef<(() => void) | null>(null);
  const registerFocus = useCallback((f: (() => void) | null) => {
    focusTable.current = f;
  }, []);

  const scope = useMemo(() => ({ [ARCH_RUN_SCOPE.param]: `${includeChildren ? ARCH_RUN_SCOPE.tree : ARCH_RUN_SCOPE.run}:${runId}` }), [includeChildren, runId]);
  const schema = useLogSchema();
  const filterTitle = useCallback((name: string) => schema.data?.filters?.find((f) => f.id === name)?.title || name, [schema.data]);
  const arch = useArchitectureController({ scope, enabled: true, highlightUid: selectedUid, filterTitle });
  const isError = useCallback((e: Pick<LogEvent, "category" | "tags">) => isErrorEvent(e, taxonomy), [taxonomy]);

  // 구조도 선택이 없을 때는 범위 전체 이벤트, 있으면 서버가 걸러 준 이벤트(칸 횟수와 행 수가 같다).
  const baseParams = useMemo(() => ({ ...scope, limit: LOGS_LIMITS.runLogsPage, order: "asc" }), [scope]);
  const filtered = arch.rowsParams !== null;
  const base = useLogEventPages(baseParams, !filtered);
  const baseEvents = useMemo(() => (base.data?.pages ?? []).flatMap((pg) => pg.items ?? []), [base.data]);
  const events = filtered ? arch.rows.events : baseEvents;

  // ---- 실시간: 수집 알림과 실행 이벤트마다 1초 디바운스로 다시 질의
  const refresh = useCallback(
    (count: number) => {
      arch.ingested(count);
      void qc.invalidateQueries({ queryKey: ["logs", "events"] });
    },
    [arch, qc],
  );
  useLogsIngested((info) => refresh(info.count), LOGS_LIMITS.archDebounceMs, running);
  const refreshRef = useRef(refresh);
  useEffect(() => {
    refreshRef.current = refresh;
  });
  const firstKey = useRef(refreshKey);
  useEffect(() => {
    if (!running || refreshKey === firstKey.current) return;
    const timer = setTimeout(() => refreshRef.current(0), LOGS_LIMITS.archDebounceMs);
    return () => clearTimeout(timer);
  }, [refreshKey, running]);

  const count = observedValue(arch.target?.count);
  const note = count === undefined ? undefined : archMessages.table.only(arch.targetTitle, count);
  const scopeName = includeChildren ? archMessages.runTab.scopeTree : archMessages.runTab.scopeRun;
  const profileTitle = arch.profiles?.profiles?.find((x) => x.id === arch.view?.profile)?.title ?? arch.view?.profile ?? "";

  const includeSwitch = hasChildren ? (
    <Switch checked={includeChildren} onChange={setTree} label={archMessages.runTab.includeChildren} onText={archMessages.runTab.on} offText={archMessages.runTab.off} />
  ) : null;
  const toolbarExtra = (
    <>
      {includeSwitch}
      <Button ref={expandRef} size="sm" aria-haspopup="dialog" onClick={() => setExpanded(true)}>{archMessages.dialog.expand} ⤢</Button>
    </>
  );
  const panelProps = {
    rootLabel: archMessages.runTab.rootLabel,
    live: running,
    // 확대·맞춤 단추는 두지 않는다(화면 맞춤 그림이 기본이고, 자세히 보려면 [크게 보기]).
    toolbar: { zoom: false, fit: false },
    hideEmptyHead: true,
    defaultFit: "contain" as const,
    storageKeys: { fit: ARCH_STORAGE.runFit, view: ARCH_STORAGE.runView },
    hasFilters: filters !== NO_RUN_EVENT_FILTERS && (filters.q !== "" || filters.errorsOnly || filters.categories.length > 0),
    onClearFilters: () => setFilters(NO_RUN_EVENT_FILTERS),
    onOpenSettings: () => void navigate(`${pathForRole(LINK_ROLES.settings)}#architecture`),
    onOpenSources: () => void navigate(settingsLogsHref()),
    onSkip: () => focusTable.current?.(),
  };
  const pane = (searchId: string) => (
    <RunArchitectureEvents
      searchId={searchId}
      events={events}
      filters={filters}
      onFilters={setFilters}
      taxonomy={taxonomy}
      isError={isError}
      loading={filtered ? arch.rows.loading && arch.rows.events.length === 0 : base.isPending}
      hasMore={filtered ? false : base.hasNextPage}
      loadingMore={filtered ? false : base.isFetchingNextPage}
      onNearEnd={() => void base.fetchNextPage()}
      running={running}
      selectedUid={selectedUid}
      onSelect={setSelectedUid}
      registerFocus={registerFocus}
      note={note}
    />
  );

  return (
    <div className="arch-run">
      <p className="arch-table-note arch-run-explain">{archMessages.runTab.explain}</p>
      <div className="arch-run-diagram">
        {expanded ? null : <ArchitecturePanel controller={arch} toolbarExtra={toolbarExtra} diagramHeight={canvasH + ARCH_RUN_HEIGHT.chrome} {...panelProps} />}
      </div>
      <SplitHandle orientation="horizontal" size={canvasH} min={ARCH_RUN_HEIGHT.min} max={ARCH_RUN_HEIGHT.max} onChange={changeHeight} label={archMessages.runTab.splitLabel} />
      <div className="arch-run-chips"><ArchitectureChips chips={arch.chips} /></div>
      <div className="arch-run-table">{expanded ? null : pane("arch-run-q")}</div>
      <ArchitectureDialog
        open={expanded}
        title={archMessages.dialog.title(profileTitle, scopeName)}
        onClose={() => {
          setExpanded(false);
          requestAnimationFrame(() => expandRef.current?.focus());
        }}
        controller={arch}
        panelProps={{ ...panelProps, toolbar: true, defaultFit: "width", defaultView: "diagram", storageKeys: { fit: ARCH_STORAGE.runDialogFit, view: ARCH_STORAGE.runDialogView }, toolbarExtra: includeSwitch }}
        table={expanded ? pane("arch-run-dialog-q") : undefined}
      />
    </div>
  );
}
