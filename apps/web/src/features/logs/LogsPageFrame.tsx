import { useEffect, type KeyboardEvent, type ReactNode } from "react";
import { Link, Navigate, Outlet, useNavigate } from "react-router";
import { Banner, PageHeader, useShortcuts } from "@agent-console/ui";
import { queryKeys, useApiQuery } from "../../app/queries";
import { useStorage } from "../../app/StorageContext";
import { usePageTitle } from "../../shell/titles";
import { LogProjectNote } from "../projects";
import { LogsLiveProvider } from "./LogsLive";
import { DEFAULT_LOG_TAB, FILTER_KEYS, LOGS_SCOPES, LOGS_STORAGE, LOG_TABS, WARNING_CODES, type LogTabId } from "./logsConfig";
import { logsMessages as t } from "./messages";

/** 로그 라우트의 공통 층: 수집 알림 구독(WS `logs`)을 하나 열고 하위 화면에 나눠 준다. */
export function LogsLayout() {
  return (
    <LogsLiveProvider>
      <Outlet />
    </LogsLiveProvider>
  );
}

/** `/logs` → 마지막에 본 탭(저장 실패·없으면 기본 탭)으로 `replace` 이동. */
export function LogsIndexRedirect() {
  const storage = useStorage();
  const saved = storage.get(LOGS_STORAGE.lastTab);
  const tab = LOG_TABS.find((x) => x.id === saved)?.id ?? DEFAULT_LOG_TAB;
  const segment = LOG_TABS.find((x) => x.id === tab)?.segment ?? tab;
  return <Navigate to={segment} replace />;
}

export interface LogsPageFrameProps {
  tab: LogTabId;
  /** 문서 제목 앞부분(예: `세션 a1b2c3d4`). 없으면 탭 이름 */
  title?: string;
  actions?: ReactNode;
  status?: ReactNode;
  children: ReactNode;
}

/** 로그 화면 공통 틀: 페이지 헤더 + 탭 줄(세션·검색·대시보드) + 본문. 탭 상태는 URL 경로가 정한다. */
export function LogsPageFrame({ tab, title, actions, status, children }: LogsPageFrameProps) {
  const navigate = useNavigate();
  const storage = useStorage();
  usePageTitle(`${title ?? t.tabs[tab] ?? tab} · ${t.title}`);
  useEffect(() => storage.set(LOGS_STORAGE.lastTab, tab), [storage, tab]);
  const info = useApiQuery(queryKeys.descriptors("server-info"), (rest) => rest.getServerInfo(), { retry: false, meta: { silentBackgroundError: true } });
  const redaction = (info.data?.warnings ?? []).some((w) => w.code === WARNING_CODES.redactionUnavailable);
  // 등록된 프로젝트가 없으면 로그 출처가 아무것도 읽지 않는다 — 빈 화면의 이유를 서버 문구(detail)로 보여 준다.
  const noProjects = (info.data?.warnings ?? []).find((w) => w.code === WARNING_CODES.noProjects);

  const go = (id: string) => {
    const seg = LOG_TABS.find((x) => x.id === id)?.segment;
    if (seg !== undefined) void navigate(`/logs/${seg}`);
  };
  useShortcuts(
    LOG_TABS.map((x, i) => ({ id: `logs.tab${i + 1}`, scope: LOGS_SCOPES.common, keys: `Alt+${i + 1}`, titleKey: "shortcuts.libPanelTab", run: () => go(x.id) })),
  );
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = LOG_TABS.findIndex((x) => x.id === tab);
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? LOG_TABS.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const target = LOG_TABS[(next + LOG_TABS.length) % LOG_TABS.length];
    if (target !== undefined) {
      go(target.id);
      requestAnimationFrame(() => document.getElementById(`logs-tab-${target.id}`)?.focus());
    }
  };
  return (
    <div className="app-screen-frame logs-frame" data-screen="logs" data-tab={tab}>
      <PageHeader title={t.title} {...(status === undefined ? {} : { status })} {...(actions === undefined ? {} : { actions })} />
      <div className="logs-tabs ac-tabs-list" role="tablist" aria-label={t.tabsLabel} onKeyDown={onKey}>
        {LOG_TABS.map((x) => (
          <Link key={x.id} id={`logs-tab-${x.id}`} to={`/logs/${x.segment}`} replace role="tab" aria-selected={x.id === tab} tabIndex={x.id === tab ? 0 : -1} className="ac-tab">
            {t.tabs[x.id] ?? x.id}
          </Link>
        ))}
      </div>
      {redaction && tab !== "dashboards" ? <Banner tone="warning" className="logs-redaction">{t.filters.redactionWarning}</Banner> : null}
      {noProjects !== undefined ? <Banner tone="warning" className="logs-no-projects">{noProjects.message || t.noProjects}</Banner> : null}
      <LogProjectNote filterParam={FILTER_KEYS.project} />
      <div className="logs-body">{children}</div>
    </div>
  );
}

