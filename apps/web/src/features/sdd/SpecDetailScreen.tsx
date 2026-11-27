/**
 * 스펙 상세 화면(`/specs/:id`, screen-sdd §5): 머리(이름·프로젝트·내보내기·메뉴) + 2째 줄(문서 폴더·진행·문서 상태·자동 진행) + 탭 줄 + 탭 본문.
 * 탭 본문은 등록 표(`SddTabPanels`)가 그린다 — 탭을 더하려면 컴포넌트 하나를 등록한다. 선택한 탭·문서·작업은 주소가 진실이다.
 * 스펙 이름·문서 이름·상태 라벨은 서버 데이터다.
 */
import "@agent-console/sdd-view/styles.css";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Banner, Button, ConfirmDialog, PageHeader, Tabs, useToast, type TabItem } from "@agent-console/ui";
import { ToneChip } from "@agent-console/sdd-view";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useStorage } from "../../app/StorageContext";
import { useReportUnsaved } from "../../definition/unsaved";
import { usePageTitle } from "../../shell/titles";
import { ProjectChip } from "../projects";
import { DocumentsTab } from "./DocumentsTab";
import { FailureBlock, GuardedButton, ListSkeleton, MenuButton } from "./parts";
import { PlanTab } from "./PlanTab";
import { RulesTab } from "./RulesTab";
import { DEFAULT_TAB, SDD_PARAMS, SDD_STORAGE, SDD_TAB_DEFS } from "./sddConfig";
import { SpecExportDialog } from "./SpecExportDialog";
import { SpecRenameDialog } from "./SpecRenameDialog";
import { specsPath } from "./sddPaths";
import type { SddTabPanels, SddTabProps } from "./sddTabs";
import { TasksTab } from "./TasksTab";
import { TraceTab } from "./TraceTab";
import { useInvalidateSdd, useSddLive, useSddSpace, useSpecSyntax, useSpecView } from "./useSddApi";
import { useSddContext } from "./useSddContext";
import "./sdd.css";
import { useServerText, useT } from "@agent-console/i18n";
import { useMaybeT } from "../../i18n/useMaybeT";
import { SddToast } from "./SddToast";

const P = SDD_PARAMS;

/** 기본 탭 본문 등록 표. 계획·추적 같은 탭은 같은 모양의 컴포넌트를 `panels`로 더하면 탭 줄에 나온다. */
export const DEFAULT_TAB_PANELS: SddTabPanels = {
  documents: DocumentsTab,
  tasks: TasksTab,
  plan: PlanTab,
  trace: TraceTab,
  rules: RulesTab,
};

export interface SpecDetailScreenProps {
  /** 탭 본문 등록 표(기본 `DEFAULT_TAB_PANELS`). 앱 조립 층이 탭을 더하거나 바꾼다 */
  panels?: SddTabPanels;
}

export function SpecDetailScreen({ panels = DEFAULT_TAB_PANELS }: SpecDetailScreenProps) {
  const t = useT("sdd");
  const tm = useMaybeT("sdd");
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [params, setSearch] = useSearchParams();
  const space = useSddSpace();
  const ctx = useSddContext();
  const storage = useStorage();
  const toast = useToast();
  const qc = useQueryClient();
  const invalidate = useInvalidateSdd();
  const viewQ = useSpecView(id);
  const syntax = useSpecSyntax(id);
  const ownHashes = useRef(new Set<string>());
  useSddLive(ownHashes);
  const [dialog, setDialog] = useState<"export" | "delete" | "rename" | null>(null);
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
  // 다른 화면으로 가는 이동만 막는다(같은 스펙 안의 탭·문서 이동은 주소 인자만 바뀌므로 막지 않는다)
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  const serverText = useServerText();
  const rawView = viewQ.data?.value;
  // 기본 작업 문법·문서 상태의 이름은 서버 원문(패키지 데이터)이라 화면 언어로 옮긴다. 사용자가 쓴 이름은 묶음에 없어 그대로다.
  const view = useMemo(
    () =>
      rawView === undefined
        ? undefined
        : {
            ...rawView,
            ...(rawView.task_statuses === undefined ? {} : { task_statuses: rawView.task_statuses.map((s) => ({ ...s, label: serverText.text(s.label) })) }),
            ...(rawView.document_states === undefined ? {} : { document_states: rawView.document_states.map((s) => ({ ...s, label: serverText.text(s.label) })) }),
          },
    [rawView, serverText],
  );
  const versionHash = viewQ.data?.version_hash ?? view?.version_hash ?? "";
  usePageTitle(view?.spec.name ?? t("title"));

  const tabs = SDD_TAB_DEFS.filter((t) => panels[t.id] !== undefined);
  const fromUrl = params.get(P.tab);
  const stored = storage.get(SDD_STORAGE.tab(id));
  const active = tabs.find((t) => t.id === fromUrl)?.id ?? tabs.find((t) => t.id === stored)?.id ?? tabs.find((t) => t.id === DEFAULT_TAB)?.id ?? tabs[0]?.id;

  const setParams: SddTabProps["setParams"] = (next, options) => setSearch(next, { replace: options?.replace === true });
  const goTab: SddTabProps["goTab"] = (tab, query = {}) => {
    const next = new URLSearchParams();
    next.set(P.tab, tab);
    for (const [k, v] of Object.entries(query)) if (v !== null && v !== undefined && v !== "") next.set(k, v);
    storage.set(SDD_STORAGE.tab(id), tab);
    setSearch(next);
  };
  const refresh = async () => {
    await invalidate();
  };

  const tasks = view?.index?.tasks ?? [];
  const doneIds = useMemo(() => new Set((view?.task_statuses ?? []).filter((s) => s.done === true).map((s) => s.id)), [view?.task_statuses]);
  const done = tasks.filter((t) => doneIds.has(t.status)).length;
  const readyCount = tasks.filter((t) => t.ready === true && !doneIds.has(t.status)).length;
  const stateCounts = useMemo(() => {
    const out = new Map<string, { label: string; tone: string | null; n: number }>();
    for (const d of view?.spec.documents ?? []) {
      if (d.state === undefined || d.state === null) continue;
      const info = view?.document_states?.find((s) => s.id === d.state);
      const entry = out.get(d.state) ?? { label: info?.label ?? d.state, tone: info?.tone ?? null, n: 0 };
      entry.n += 1;
      out.set(d.state, entry);
    }
    return [...out.values()];
  }, [view]);
  const errorCount = (view?.issues ?? []).filter((i) => i.severity === "error").length;
  const backLink = <Button onClick={() => void navigate(specsPath())}>{t("backToList")}</Button>;

  if (viewQ.isPending) {
    return (
      <div className="app-screen-frame sdd-screen">
        <PageHeader title={t("title")} />
        <div className="sdd-screen-body"><ListSkeleton rows={8} /></div>
      </div>
    );
  }
  if (viewQ.isError || view === undefined) {
    return (
      <div className="app-screen-frame sdd-screen">
        <PageHeader title={t("title")} />
        <div className="sdd-screen-body"><FailureBlock error={viewQ.error} title={t("loadFailed")} onRetry={() => void viewQ.refetch()} backTo={backLink} /></div>
      </div>
    );
  }

  const specName = view.spec.name !== "" ? view.spec.name : view.spec.id;
  const directory = view.directory ?? "";
  const writeBlock = ctx.readOnly ? ctx.readOnlyReason : undefined;
  const copyPath = () => {
    void navigator.clipboard?.writeText(directory);
    toast({ tone: "success", text: <SddToast render={(t) => t("head.copied")} /> });
  };
  const rename = async (name: string) => {
    const saved = await space.client.putSpec(view.spec.id, { ...view.spec, name }, versionHash);
    if (saved.version_hash !== undefined) ownHashes.current.add(saved.version_hash);
    setDialog(null);
    await invalidate();
  };
  const remove = async () => {
    try {
      await space.client.deleteSpec(view.spec.id, versionHash);
      setDialog(null);
      qc.removeQueries({ queryKey: ["sdd", space.key, "spec", view.spec.id] });
      await invalidate();
      void navigate(specsPath());
    } catch (e) {
      setDialog(null);
      toast({ tone: "danger", text: <SddToast render={(t, d) => d(e, t("problem.generic")).message} /> });
    }
  };

  const tabProps: SddTabProps = { specId: view.spec.id, view, versionHash, ctx, params, setParams, goTab, ownHashes, refresh, reportDirty };
  const badge = (id2: string): string | null => (id2 === "tasks" && readyCount > 0 ? t("tabBadge.tasks", { count: readyCount }) : null);
  const items: TabItem[] = tabs.map((t) => {
    const Panel = panels[t.id];
    const label = tm(`tabs.${t.labelKey}`) ?? t.id;
    const b = t.id === "tasks" ? readyCount : 0;
    return {
      id: t.id,
      label: b > 0 ? <>{label} <span className="sdd-badge" aria-label={badge(t.id) ?? undefined}>{b}</span></> : label,
      title: label,
      content: Panel === undefined ? null : <Panel {...tabProps} />,
    };
  });

  return (
    <div className="app-screen-frame sdd-screen">
      <PageHeader
        title={specName}
        leading={
          <nav className="sdd-crumb" aria-label={t("head.crumbLabel")}>
            <Link to={specsPath()} className="app-back">← {t("back")}</Link>
            <span className="ac-breadcrumb-sep" aria-hidden="true">/</span>
          </nav>
        }
        actions={
          <>
            <ProjectChip />
            {ctx.capabilities.import_export ? <GuardedButton blockedReason={writeBlock} onClick={() => setDialog("export")}>{t("head.export")}</GuardedButton> : null}
            <MenuButton
              label="⋯"
              panelLabel={t("head.more")}
              items={[
                { id: "rename", label: t("head.rename"), disabled: writeBlock !== undefined, onSelect: () => setDialog("rename") },
                { id: "copy", label: t("head.copyPath"), disabled: directory === "", onSelect: copyPath },
                { id: "delete", label: t("head.delete"), danger: true, disabled: writeBlock !== undefined, onSelect: () => setDialog("delete") },
              ]}
            />
          </>
        }
      />
      <div className="sdd-subhead">
        {directory === "" ? null : <span className="ac-mono-wrap ac-ellipsis sdd-mono" title={directory}>{directory}</span>}
        {tasks.length > 0 ? (
          <span className="sdd-inline" role="status">
            <progress className="sdd-progress" max={tasks.length} value={done} aria-label={t("head.progress", { done, total: tasks.length })} />
            <span className="app-muted">{t("head.progress", { done, total: tasks.length })}</span>
          </span>
        ) : syntax.data?.empty === true ? <span className="app-muted">{t("head.noSyntax")}</span> : null}
        {stateCounts.map((s) => <ToneChip key={s.label} label={`${s.label} ${s.n}`} tone={s.tone} />)}
        {view.automation_state?.enabled === true ? <ToneChip label={t("head.automationOn")} tone="info" /> : null}
        {viewQ.isFetching ? <span className="ac-sr-only" role="status">{t("refreshing")}</span> : null}
      </div>
      {ctx.readOnly ? (
        <div className="sdd-banner-row">
          <div className="sdd-readonly-note" role="status" data-testid="sdd-readonly"><strong>{t("readonly.title")}</strong> <span>{t("readonly.body")}</span></div>
        </div>
      ) : null}
      {errorCount > 0 && active !== "rules" ? (
        <div className="sdd-banner-row">
          <Banner tone="warning" actions={tabs.some((t) => t.id === "rules") ? <Button size="sm" onClick={() => goTab("rules")}>{t("openRules")}</Button> : undefined}>{t("specIssues", { count: errorCount })}</Banner>
        </div>
      ) : null}
      <div className="sdd-screen-body">
        {tabs.length === 0 || active === undefined ? <ErrorBlock title={t("loadFailed")} /> : (
          <Tabs
            tabs={items}
            activeId={active}
            onChange={(next) => goTab(next)}
            ariaLabel={t("tabsLabel")}
            lazy
          />
        )}
      </div>
      {dialog === "export" ? (
        <SpecExportDialog open onClose={() => setDialog(null)} blockedReason={writeBlock} loadDirs={(path) => space.client.listImportFiles(path)} onSubmit={(body) => space.client.exportSpec(view.spec.id, body)} />
      ) : null}
      <ConfirmDialog open={blocker.state === "blocked"} title={t("leave.title")} confirmLabel={t("leave.leave")} cancelLabel={t("leave.stay")} danger onConfirm={() => blocker.state === "blocked" && blocker.proceed()} onCancel={() => blocker.state === "blocked" && blocker.reset()}>{t("leave.body")}</ConfirmDialog>
      <ConfirmDialog open={dialog === "delete"} title={t("delete.title", { name: specName })} confirmLabel={t("delete.confirm")} cancelLabel={t("cancel")} danger onConfirm={() => void remove()} onCancel={() => setDialog(null)}>
        {directory === "" ? t("delete.bodyRoot") : t("delete.body", { path: directory })}
      </ConfirmDialog>
      {dialog === "rename" ? <SpecRenameDialog open initialName={view.spec.name} onClose={() => setDialog(null)} onSubmit={rename} /> : null}
    </div>
  );
}
