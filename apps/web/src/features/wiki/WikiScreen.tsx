/**
 * 위키 화면(`/wiki/:wiki`, screen-wiki §5): 머리(이름·본문 검색·새 페이지·메뉴) + 2째 줄(폴더·페이지 수·끊긴 링크·규칙·최근 변경) + 탭 줄 + 탭 본문.
 * 탭 본문은 등록 표(`WikiTabPanels`)가 그린다 — 기본은 페이지 탭 하나이고 그래프·점검·규칙 탭은 같은 모양의 컴포넌트를 등록하면 탭 줄에 나온다.
 * 선택한 탭·페이지·모드는 주소가 진실이다. 위키 이름·규칙 이름·폴더 경로는 서버 데이터다.
 */
import "@agent-console/wiki-view/styles.css";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from "react-router";
import { Banner, Button, ChipRow, ConfirmDialog, PageHeader, Tabs, useToast, type TabItem } from "@agent-console/ui";
import { AuthorChip } from "@agent-console/wiki-view";
import { ToneChip } from "@agent-console/markdown-doc";
import type { WikiSummary } from "@agent-console/contracts/wiki";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useReportUnsaved } from "../../definition/unsaved";
import { useNow } from "../../app/useNow";
import { formatRelative } from "../../lib/format";
import { usePageTitle } from "../../shell/titles";
import { GuardedButton, MenuButton } from "../../app/menuParts";
import { ProjectChip } from "../projects";
import { NewPageDialog } from "./PageDialogs";
import { PageTab } from "./PageTab";
import { WikiSearch } from "./WikiSearch";
import { FailureBlock, ListSkeleton } from "./parts";
import { useDeleteWikiDialog, useExportDialog, useImportDialog, useNewWikiDialog } from "./wikiDialogs";
import { ownWriteKey, useInvalidateWiki, useWikiList, useWikiLive, useWikiSpace, usePageList, useWikiView, type OwnWrites } from "./useWikiApi";
import { useWikiContext } from "./useWikiContext";
import { DEFAULT_TAB, WIKI_PARAMS, WIKI_TAB_DEFS, buildWikiDisplay, severityTone } from "./wikiConfig";
import { wikiListPath, wikiPagePath, wikiPath } from "./wikiPaths";
import { useWikiShortcuts } from "./wikiShortcuts";
import type { NewPagePrefill, WikiTabPanels, WikiTabProps } from "./wikiTabs";
import { wikiMessages as m } from "./messages";
import "./wiki.css";

const P = WIKI_PARAMS;

/** 기본 탭 본문 등록 표. 그래프·점검·규칙 탭은 같은 모양의 컴포넌트를 `panels`로 더하면 탭 줄에 나온다(7R.20). */
export const DEFAULT_TAB_PANELS: WikiTabPanels = {
  page: PageTab,
};

export interface WikiScreenProps {
  /** 탭 본문 등록 표(기본 `DEFAULT_TAB_PANELS`). 앱 조립 층이 탭을 더하거나 바꾼다 */
  panels?: WikiTabPanels;
}

const wikiName = (w: { name?: string; id: string } | undefined, id: string): string => (w?.name !== undefined && w.name !== "" ? w.name : w?.id ?? id);

/** 점검 탭 배지: 위험·경고 톤인 심각도의 개수 합(심각도 이름은 서버 데이터라 톤 표로만 판단한다). */
export function lintBadge(counts: Readonly<Record<string, number>> | undefined): number {
  return Object.entries(counts ?? {}).reduce((n, [severity, c]) => (["danger", "warning"].includes(severityTone(severity)) ? n + c : n), 0);
}

export function WikiScreen({ panels = DEFAULT_TAB_PANELS }: WikiScreenProps) {
  const { wiki: wikiId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setSearch] = useSearchParams();
  const space = useWikiSpace();
  const ctx = useWikiContext();
  const toast = useToast();
  const now = useNow(true, 60_000);
  const invalidate = useInvalidateWiki();
  const viewQ = useWikiView(wikiId);
  const listQ = useWikiList();
  const pagesQ = usePageList(wikiId);
  const ownWrites = useRef<OwnWrites>(new Map());
  const [syncing, setSyncing] = useState(false);
  useWikiLive(ownWrites, (events) => {
    if (events.some((e) => e.wiki_id === wikiId)) {
      setSyncing(true);
      setTimeout(() => setSyncing(false), 1200);
    }
  });
  const display = useMemo(() => buildWikiDisplay(), []);
  const searchRef = useRef<HTMLInputElement>(null);
  const [newPage, setNewPage] = useState<{ prefill: NewPagePrefill | undefined } | null>(null);
  const [dirtyTabs, setDirtyTabs] = useState<ReadonlySet<string>>(new Set());
  const reportDirty = useCallback((key: string, dirty: boolean) => {
    setDirtyTabs((cur) => {
      if (cur.has(key) === dirty) return cur;
      const next = new Set(cur);
      if (dirty) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);
  const dirty = dirtyTabs.size > 0;
  useReportUnsaved(dirty);
  // 다른 화면으로 가는 이동만 막는다(같은 위키 안의 탭·페이지 이동은 주소 인자만 바뀌므로 막지 않는다)
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  const view = viewQ.data?.value;
  const versionHash = viewQ.data?.version_hash ?? view?.version_hash ?? "";
  const summary: WikiSummary | undefined = listQ.data?.find((w) => w.id === wikiId);
  const name = wikiName(view?.wiki ?? summary, wikiId);
  usePageTitle(view === undefined ? m.title : name);

  const importer = useImportDialog();
  const exporter = useExportDialog();
  const remover = useDeleteWikiDialog(() => void navigate(wikiListPath()));
  const creator = useNewWikiDialog((id) => void navigate(wikiPath(id)), ctx.capabilities.import_export ? () => importer.open(wikiId) : undefined);

  const tabs = WIKI_TAB_DEFS.filter((t) => panels[t.id] !== undefined);
  const fromUrl = params.get(P.tab);
  const active = tabs.find((t) => t.id === fromUrl)?.id ?? tabs.find((t) => t.id === DEFAULT_TAB)?.id ?? tabs[0]?.id;

  const setParams: WikiTabProps["setParams"] = (next, options) => setSearch(next, { replace: options?.replace === true });
  const goTab: WikiTabProps["goTab"] = (tab, query = {}) => {
    const next = new URLSearchParams();
    next.set(P.tab, tab);
    for (const [k, v] of Object.entries(query)) if (v !== null && v !== undefined && v !== "") next.set(k, v);
    setSearch(next);
  };
  const refresh = useCallback(async () => {
    await invalidate();
  }, [invalidate]);
  const writeBlock = ctx.readOnly ? ctx.readOnlyReason : undefined;
  const openNewPage = useCallback((prefill?: NewPagePrefill) => setNewPage({ prefill }), [setNewPage]);
  useWikiShortcuts({
    newPage: ctx.readOnly ? undefined : () => openNewPage(),
    search: () => searchRef.current?.focus(),
  });

  const rescan = async () => {
    try {
      const r = await space.client.scanWiki(wikiId);
      const n = (r.external ?? []).length + (r.imported ?? []).length + (r.deleted ?? []).length;
      toast({ tone: "info", text: n > 0 ? m.rescanDone(n) : m.rescanNone, durationMs: 4000 });
    } catch (e) {
      toast({ tone: "danger", text: e instanceof Error && e.message !== "" ? e.message : m.problem.generic });
    }
    await invalidate();
  };

  const backLink = <Button onClick={() => void navigate(wikiListPath())}>{m.backToList}</Button>;
  if (viewQ.isPending) {
    return (
      <div className="app-screen-frame wiki-screen">
        <PageHeader title={m.title} />
        <div className="wiki-screen-body"><ListSkeleton rows={8} /></div>
      </div>
    );
  }
  if (viewQ.isError || view === undefined) {
    return (
      <div className="app-screen-frame wiki-screen">
        <PageHeader title={m.title} />
        <div className="wiki-screen-body"><FailureBlock error={viewQ.error} title={m.loadFailed} onRetry={() => void viewQ.refetch()} backTo={backLink} /></div>
      </div>
    );
  }

  const directory = view.directory ?? summary?.directory ?? "";
  const rules = view.rules?.rules ?? summary?.rules ?? [];
  const errorCount = (view.issues ?? []).filter((i) => i.severity === "error").length;
  const broken = summary?.broken_links ?? 0;
  const lint = lintBadge(summary?.lint_counts);
  const others = (listQ.data ?? []).filter((w) => w.id !== wikiId);
  const copyDirectory = () => {
    void navigator.clipboard?.writeText(directory);
    toast({ tone: "success", text: m.copied });
  };
  const currentSummary: WikiSummary = summary ?? { id: wikiId, name };

  const tabProps: WikiTabProps = {
    wikiId,
    view,
    versionHash,
    summary,
    ctx,
    display,
    params,
    setParams,
    goTab,
    ownWrites,
    refresh,
    reportDirty,
    openNewPage,
    hasTab: (tab) => tabs.some((t) => t.id === tab),
  };
  const items: TabItem[] = tabs.map((t) => {
    const Panel = panels[t.id];
    const label = m.tabs[t.labelKey] ?? t.id;
    const badge = t.id === "lint" ? lint : 0;
    return {
      id: t.id,
      label: badge > 0 ? <>{label} <span className="wiki-badge" aria-label={m.lintBadge(badge)}>{badge}</span></> : label,
      title: label,
      content: Panel === undefined ? null : <Panel {...tabProps} />,
    };
  });

  return (
    <div className="app-screen-frame wiki-screen">
      <PageHeader
        title={name}
        status={
          <span className="wiki-crumb">
            <Link to={wikiListPath()} className="app-back">← {m.back}</Link>
            <MenuButton
              label={<><span aria-hidden="true">▾</span><span className="ac-sr-only">{m.header.switchLabel}</span></>}
              panelLabel={m.header.switchLabel}
              align="start"
              items={[
                ...others.map((w) => ({ id: `w:${w.id}`, label: wikiName(w, w.id), onSelect: () => void navigate(wikiPath(w.id)) })),
                { id: "new", label: m.list.new, disabled: writeBlock !== undefined, onSelect: creator.open },
                { id: "list", label: m.header.list, onSelect: () => void navigate(wikiListPath()) },
              ]}
            />
            {syncing || viewQ.isFetching ? <span className="wiki-spinner" role="status" aria-label={m.refreshing} /> : null}
          </span>
        }
        actions={
          <>
            <WikiSearch wikiId={wikiId} pages={pagesQ.data?.items ?? []} onOpen={(path) => void navigate(wikiPagePath(wikiId, path))} inputRef={searchRef} />
            <ProjectChip />
            <GuardedButton variant="primary" blockedReason={writeBlock} onClick={() => openNewPage()}>{m.header.newPage}</GuardedButton>
            <MenuButton
              label={<><span aria-hidden="true">⋯</span><span className="ac-sr-only">{m.header.more}</span></>}
              panelLabel={m.header.more}
              items={[
                ...(tabs.some((t) => t.id === "rules") ? [{ id: "edit", label: m.header.editInfo, onSelect: () => goTab("rules") }] : []),
                { id: "copy", label: m.copyDirectory, disabled: directory === "", onSelect: copyDirectory },
                ...(ctx.capabilities.import_export
                  ? [
                      { id: "export", label: m.list.export, onSelect: () => exporter.open(currentSummary) },
                      { id: "import", label: m.header.importZip, disabled: writeBlock !== undefined, onSelect: () => importer.open(wikiId) },
                    ]
                  : []),
                { id: "delete", label: m.list.delete, danger: true, disabled: writeBlock !== undefined, onSelect: () => remover.open(currentSummary) },
              ]}
            />
          </>
        }
      />
      <div className="wiki-subhead">
        {directory === "" ? null : (
          <>
            <span className="ac-mono-wrap ac-ellipsis wiki-mono" title={directory}>{directory}</span>
            <button type="button" className="app-link-btn" onClick={copyDirectory}>{m.copy}</button>
          </>
        )}
        {summary?.pages === undefined ? null : <span>{m.header.pages(summary.pages)}</span>}
        {broken > 0 ? <ToneChip label={m.header.broken(broken)} tone="warning" /> : null}
        {rules.length === 0 ? <span className="app-muted">{m.header.noRules}</span> : <ChipRow chips={rules.map((r) => ({ id: r.id, label: r.name !== undefined && r.name !== "" ? r.name : r.id, ...(r.missing === true ? { tone: "danger" } : {}) }))} ariaLabel={m.header.rules} />}
        {summary?.updated_at === undefined || summary.updated_at === null ? null : <span className="app-muted">{m.header.updated(formatRelative(summary.updated_at, now))}</span>}
        {summary?.updated_by === undefined || summary.updated_by === null ? null : <AuthorChip author={summary.updated_by} display={display} size="dense" />}
        <span className="wiki-spacer" />
        <button type="button" className="app-link-btn" onClick={() => void rescan()}>{m.rescan}</button>
      </div>
      {ctx.readOnly ? (
        <div className="wiki-banner-row">
          <div className="wiki-readonly-note" role="status" data-testid="wiki-readonly"><strong>{m.readonly.title}</strong> <span>{m.readonly.body}</span></div>
        </div>
      ) : null}
      {errorCount > 0 && active !== "rules" ? (
        <div className="wiki-banner-row">
          <Banner tone="warning" actions={tabs.some((t) => t.id === "rules") ? <Button size="sm" onClick={() => goTab("rules")}>{m.header.issuesOpen}</Button> : undefined}>{m.header.issues(errorCount)}</Banner>
        </div>
      ) : null}
      <div className="wiki-screen-body wiki-screen-body-tabs">
        {tabs.length === 0 || active === undefined ? <ErrorBlock title={m.loadFailed} /> : (
          <Tabs tabs={items} activeId={active} onChange={(next) => goTab(next)} ariaLabel={m.tabsLabel} lazy />
        )}
      </div>
      {newPage === null ? null : (
        <NewPageDialog
          wikiId={wikiId}
          wikiName={name}
          open
          onClose={() => setNewPage(null)}
          prefill={newPage.prefill}
          existingPaths={(pagesQ.data?.items ?? []).map((p) => p.path)}
          directory={directory !== "" ? directory : ctx.pagesRoot === undefined ? undefined : `${ctx.pagesRoot}/${wikiId}`}
          blockedReason={writeBlock}
          onWritten={(paths) => paths.forEach((p) => ownWrites.current.set(ownWriteKey(wikiId, p), Date.now()))}
          onCreated={(path) => {
            setNewPage(null);
            ownWrites.current.set(ownWriteKey(wikiId, path), Date.now());
            void invalidate();
            void navigate(wikiPagePath(wikiId, path, { [P.mode]: "edit" }));
          }}
          onOpenExisting={(path) => void navigate(wikiPagePath(wikiId, path))}
        />
      )}
      {creator.dialog}
      {importer.dialog}
      {exporter.dialog}
      {remover.dialog}
      <ConfirmDialog open={blocker.state === "blocked"} title={m.leave.title} confirmLabel={m.leave.leave} cancelLabel={m.leave.stay} danger onConfirm={() => blocker.state === "blocked" && blocker.proceed()} onCancel={() => blocker.state === "blocked" && blocker.reset()}>{m.leave.body}</ConfirmDialog>
    </div>
  );
}
