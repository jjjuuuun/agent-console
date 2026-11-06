import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, ConfirmDialog, EmptyState, Icon, IconButton, useToast, type MenuItemDef } from "@agent-console/ui";
import { createProjectsText, projectAbilities, statusInfo } from "@agent-console/projects";
import { ApiError } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { useDelayed } from "../../app/useDelayed";
import { useNow } from "../../app/useNow";
import { lookupMessage, messages as appMessages } from "../../app/messages";
import { DEFAULT_ROUTES } from "../../shell/routeConfig";
import { useBackendReadiness } from "../backendReadiness";
import { ROUTE_ROLES, routePath, useRoutesOn } from "../library";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { ManifestResetDialog } from "./ManifestResetDialog";
import { MenuPopover } from "./MenuPopover";
import { ProjectConfigCard } from "./ProjectConfigCard";
import { ProjectProblemBanner } from "./ProjectProblemBanner";
import { configUnreadable, manifestPath, problemBanners, type BannerAction, type BannerSpec } from "./projectHomeLib";
import { useProjects } from "./ProjectsContext";
import { RecentActivityCard } from "./RecentActivityCard";
import { SETTINGS_PROJECTS_HASH } from "./sectionId";
import { NEW_PARAM } from "./newParam";
import { useCopyDialog } from "./useCopyDialog";
import { KIND_DELETERS, useProjectActivity, useProjectConfig, type ConfigRow } from "./useProjectHomeData";

const text = createProjectsText();
const STATUS_ICON: Readonly<Record<string, string>> = {
  folder_missing: "folder-off",
  not_a_directory: "folder-off",
  no_access: "folder-lock",
  folder_unset: "folder-help",
  folder_conflict: "folder-alert",
  manifest_invalid: "folder-alert",
};
const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

/** 앱 로그인 상태 한 줄(앱 단위, 읽기 전용): 로그인을 제공하는 백엔드의 정적 점검 결과를 톤·요약으로 그린다. 로그인 개념이 없으면 줄이 없다. */
function LoginLine() {
  const { rest } = useApi();
  const backends = useQuery({ queryKey: ["descriptors", "backends"], queryFn: () => rest.listBackends(), staleTime: 60_000, retry: false, meta: { silentBackgroundError: true } });
  const { readiness, isPending } = useBackendReadiness();
  const login = (backends.data ?? []).find((b) => b.capabilities?.login === true);
  const settingsPath = routePath(ROUTE_ROLES.settings);
  if (login === undefined) return null;
  const r = readiness[login.id];
  const key = isPending || r === undefined ? "checking" : r.tone === "ok" ? "signed_in" : r.tone === "unknown" ? "unavailable" : "signed_out";
  return (
    <Link className="prj-sum-item" data-state={key} to={`${settingsPath}#backends`} title={r?.summary}>
      <span className="prj-sum-mark" aria-hidden="true">{key === "signed_in" ? "✓" : key === "signed_out" ? "⚠" : "·"}</span>
      {m.home.login[key]}
    </Link>
  );
}

/**
 * 프로젝트 홈 `/projects/:id`(screen-projects §4). 머리·"이 프로젝트의 구성"·"최근 활동" 카드 셋.
 * 상태별 배너와 막힌 버튼(`aria-disabled` + 이유)은 `projectAbilities` 표 하나를 읽는다.
 * 가져오기(복사 계획 대화상자)는 33o의 몫이라 슬롯만 둔다.
 */
export function ProjectHomeScreen() {
  const { id = "" } = useParams();
  const p = useProjects();
  const { rest, space } = useApi();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const now = useNow(true, 30_000);
  const slow = useDelayed(p.loading || !p.loaded);
  const routeOn = useRoutesOn();
  const view = p.views.find((v) => v.project.id === id);
  const [resetOpen, setResetOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const copyDialog = useCopyDialog();
  const [highlight, setHighlight] = useState<string | undefined>(undefined);
  const [deleting, setDeleting] = useState<ConfigRow | null>(null);
  useEffect(() => {
    if (highlight === undefined) return;
    const t = setTimeout(() => setHighlight(undefined), 1500);
    return () => clearTimeout(t);
  }, [highlight]);

  // 이 화면을 열면 현재 프로젝트가 이 프로젝트가 된다
  useEffect(() => {
    if (view !== undefined && view.project.archived !== true && p.current !== id) p.setCurrent(id);
  }, [view, id, p]);

  const unreadable = view === undefined ? true : configUnreadable(view);
  const config = useProjectConfig(view, view !== undefined && !unreadable && view.project.archived !== true);
  const recordsUnreadable = view?.records_state === "unavailable";
  const activity = useProjectActivity(id, view !== undefined && !recordsUnreadable && view.status !== "folder_unset");
  const dirFallback = text("projects.dir_fallback");
  const banners = useMemo(() => (view === undefined ? [] : problemBanners(view, dirFallback)), [view, dirFallback]);

  if (p.loadFailed) {
    return (
      <div className="app-screen prj-home" data-screen="project-home">
        <ErrorBlock title={m.home.loadFailed} retryLabel={m.home.retry} onRetry={() => void p.refresh()} />
      </div>
    );
  }
  if (view === undefined) {
    if (!p.loaded) return <div className="app-screen prj-home" data-screen="project-home">{slow ? <p className="app-muted" role="status">{m.home.loading}</p> : null}</div>;
    const first = p.views.find((v) => v.project.archived !== true);
    return (
      <div className="app-screen prj-home" data-screen="project-home">
        <EmptyState
          title={m.home.notFound}
          description={m.home.notFoundBody}
          action={first === undefined ? undefined : <Button variant="primary" onClick={() => p.openHome(first.project.id)}>{m.home.toFirst}</Button>}
        />
      </div>
    );
  }

  const archived = view.project.archived === true;
  const info = statusInfo(view);
  const abilities = projectAbilities(view, { recordsWritable: view.records_writable !== false });
  const folder = view.project.folder ?? "";
  const withPrj = (path: string) => `${path}?prj=${encodeURIComponent(id)}`;
  const reason = (a: keyof typeof abilities) => (abilities[a].allowed || abilities[a].reason === null ? undefined : text(abilities[a].reason));

  const configRowMenu = (row: ConfigRow): MenuItemDef[] => {
    const saveBlock = reason("save_to_library");
    const editBlock = reason("edit");
    return [
      {
        id: "save-to-library",
        label: text("copy.save_to_library"),
        ...(saveBlock === undefined ? {} : { disabled: true, title: saveBlock }),
        onSelect: () => copyDialog.open({ direction: "save", project: id, start: "plan", items: [{ kind: row.kind, id: row.id }] }),
      },
      ...(Object.hasOwn(KIND_DELETERS, row.kind)
        ? [{ id: "delete", label: m.home.configDelete, danger: true, ...(editBlock === undefined ? {} : { disabled: true, title: editBlock }), onSelect: () => setDeleting(row) }]
        : []),
    ];
  };
  const removeConfigRow = async () => {
    const row = deleting;
    setDeleting(null);
    if (row === null) return;
    try {
      await (KIND_DELETERS[row.kind] as NonNullable<(typeof KIND_DELETERS)[string]>)(space(id), row.id);
      await queryClient.invalidateQueries({ queryKey: ["list"] });
      toast({ tone: "success", text: m.home.configDeleted(row.name) });
    } catch (e) {
      toast({ tone: "danger", text: describeError(e, m.home.configDeleteFailed).message });
    }
  };

  const chatPath = routeOn(ROUTE_ROLES.conversations) ? `${withPrj(routePath(ROUTE_ROLES.conversations))}&${NEW_PARAM}=1` : undefined;
  const runsPath = routeOn(ROUTE_ROLES.runs) ? withPrj(routePath(ROUTE_ROLES.runs)) : undefined;
  // [실행…]은 실행 시작 대화상자를 연다(실행 기록 화면이 `?new=1`을 받아 연다)
  const startRunPath = runsPath === undefined ? undefined : `${runsPath}&${NEW_PARAM}=1`;
  const shortcuts = DEFAULT_ROUTES.filter((r) => r.projectShortcut === true && routeOn(r.serves ?? r.id));

  const copy = async (value: string, done: string) => {
    toast(await copyText(value) ? { tone: "success", text: done, durationMs: 2000 } : { tone: "warning", text: m.menu.copyFailed });
  };

  const recheck = async () => {
    setBusy("recheck");
    try {
      const next = await rest.getProject(id);
      await p.refresh();
      const was = view;
      if (was.status !== "ready" && next.status === "ready") {
        setNote(null);
        toast({ tone: "success", text: m.problem.found });
      } else if (was.config_writable === false && next.config_writable !== false) {
        setNote(null);
        toast({ tone: "success", text: m.problem.writableAgain });
      } else setNote(m.problem.stillOpen(hhmm(new Date())));
    } finally {
      setBusy(null);
    }
  };

  const onBannerAction = (action: BannerAction, banner: BannerSpec) => {
    switch (action) {
      case "recheck":
        void recheck();
        return;
      case "repath":
      case "setFolder":
        p.requestRepath(id);
        return;
      case "unregister":
        p.requestUnregister(id);
        return;
      case "copyManifestPath": {
        const path = manifestPath(view);
        if (path !== null) void copy(path, m.problem.copied);
        return;
      }
      case "recreateManifest":
        setResetOpen(true);
        return;
      case "copyRecordsPath": {
        const path = view.records_issue?.details?.["path"];
        if (typeof path === "string") void copy(path, m.problem.copied);
        return;
      }
      case "copyBackupPath": {
        const path = view.records_issue?.details?.["backup_path"];
        if (typeof path === "string") void copy(path, m.problem.copied);
        return;
      }
      case "appendGitignore":
        setBusy(banner.id);
        rest.appendProjectGitignore(id).then(
          async () => {
            await p.refresh();
            toast({ tone: "success", text: m.problem.gitignoreAppended });
          },
          () => toast({ tone: "danger", text: m.problem.gitignoreFailed }),
        ).finally(() => setBusy(null));
        return;
      case "reregister":
        setBusy(banner.id);
        rest.updateProject(id, { archived: false }).then(() => p.refresh()).finally(() => setBusy(null));
    }
  };

  const submitReset = async (v: { name: string; description: string | undefined }) => {
    try {
      const result = await rest.resetProjectManifest(id, { name: v.name, ...(v.description === undefined ? {} : { description: v.description }) });
      await p.refresh();
      toast({ tone: "success", text: m.problem.manifestRecreated(result.backup_path), durationMs: 10_000, action: { label: m.home.copyPath, onClick: () => void copy(result.backup_path, m.problem.copied) } });
    } catch (e) {
      // 이미 정상이면 서버가 409: 새로 고치고 안내만 한다
      if (e instanceof ApiError && e.status === 409) {
        await p.refresh();
        toast({ tone: "info", text: m.problem.manifestRecreateNotNeeded });
        return;
      }
      throw e;
    }
  };

  const headerMenu: MenuItemDef[] = [
    ...(folder === "" ? [] : [
      { id: "copy-path", label: m.menu.copyPath, onSelect: () => void copy(folder, m.menu.pathCopied) },
      { id: "copy-cd", label: m.menu.copyCd, title: m.menu.copyCdHelp, onSelect: () => void copy(`cd "${folder}"`, m.menu.cdCopied) },
    ]),
    { id: "settings", label: m.home.settingsEntry, onSelect: () => void navigate(`${routePath(ROUTE_ROLES.settings)}${SETTINGS_PROJECTS_HASH}`) },
    ...(archived ? [] : [
      { id: "repath", label: m.menu.repath, onSelect: () => p.requestRepath(id) },
      { id: "unregister", label: m.menu.unregister, danger: true, onSelect: () => p.requestUnregister(id) },
    ]),
  ];

  const startBlock = archived ? text("projects.blocked.archived") : reason("start_chat");
  const runBlock = archived ? text("projects.blocked.archived") : reason("start_run");
  const gate = (href: string | undefined, blocked: string | undefined) => (e: React.MouseEvent) => {
    if (blocked !== undefined || href === undefined) e.preventDefault();
  };

  const header = (
    <section className="prj-card prj-head-card" aria-labelledby="prj-home-title" data-testid="project-head-card" data-status={view.status}>
      <div className="prj-head-top">
        <h1 id="prj-home-title" className="prj-home-title">
          <span className="prj-home-icon" data-tone={info.tone} aria-hidden="true"><Icon name={archived ? "folder" : (STATUS_ICON[view.status] ?? (view.status === "ready" ? "folder" : "folder-alert"))} size={20} /></span>
          <span className="ac-ellipsis" title={view.project.name}>{view.project.name}</span>
        </h1>
        {archived ? <span className="prj-chip-status" data-tone="neutral">{text("projects.status.archived")}</span> : null}
        {!archived && !info.plain && view.status !== "ready" ? <span className="prj-chip-status" data-tone={info.tone}>{text(info.label)}</span> : null}
        {!archived && view.status === "ready" && view.config_writable === false ? (
          <span className="prj-chip-status" data-tone="warning"><Icon name="folder-lock" size={12} /> {text("projects.status.readonly")}</span>
        ) : null}
        <div className="prj-head-actions">
          {chatPath === undefined ? null : (
            <Link
              to={chatPath}
              className="ac-btn"
              data-variant="primary"
              data-size="md"
              aria-disabled={startBlock !== undefined ? "true" : undefined}
              title={startBlock}
              onClick={gate(chatPath, startBlock)}
            >
              {m.home.startChat}
            </Link>
          )}
          {startRunPath === undefined ? null : (
            <Link
              to={startRunPath}
              className="ac-btn"
              data-variant="secondary"
              data-size="md"
              aria-disabled={runBlock !== undefined ? "true" : undefined}
              title={runBlock}
              onClick={gate(startRunPath, runBlock)}
            >
              {m.home.startRun}
            </Link>
          )}
          <MenuPopover label={m.home.more} triggerLabel={m.home.more} triggerClassName="prj-more-btn" items={headerMenu}>⋯</MenuPopover>
        </div>
      </div>
      {startBlock !== undefined || runBlock !== undefined ? <p className="prj-blocked-reason app-muted" data-testid="project-blocked-reason">{startBlock ?? runBlock}</p> : null}
      {folder === "" ? (
        <p className="prj-path" data-unset="true">{m.home.folderUnset}</p>
      ) : (
        <p className="prj-path">
          <span className="ac-mono-wrap prj-path-text" data-testid="project-path">{folder}</span>
          <IconButton size="sm" label={m.home.copyPath} icon={<Icon name="copy" size={14} />} onClick={() => void copy(folder, m.menu.pathCopied)} />
        </p>
      )}
      <p className="prj-id-note app-muted">{m.home.pathNote(view.project.id)}</p>
      <div className="prj-summary" aria-label={m.home.summaryLabel}>
        <LoginLine />
        {shortcuts.map((r) => (
          <Link key={r.id} className="prj-sum-item" to={withPrj(r.path)}>{lookupMessage(r.titleKey)}</Link>
        ))}
      </div>
    </section>
  );

  return (
    <div className="app-screen prj-home" data-screen="project-home" data-project={id}>
      {header}
      <ProjectProblemBanner banners={banners} onAction={onBannerAction} busy={busy} note={note} />
      {archived ? null : (
        <div className="prj-cards">
          <ProjectConfigCard
            rows={config.rows}
            loading={config.loading}
            failed={config.failed}
            onRetry={config.retry}
            unreadable={unreadable}
            blockedReason={reason("copy_in")}
            creatable={config.creatable}
            onNew={(c) => void navigate(c.href)}
            onImport={() => copyDialog.open({ direction: "import", project: id, start: "pick", onApplied: (o) => o.first !== null && setHighlight(`${o.first.kind}:${o.first.id}`) })}
            rowMenu={configRowMenu}
            highlightKey={highlight}
            onOpen={(href) => void navigate(href)}
            nowMs={now}
          />
          <RecentActivityCard
            rows={activity.rows}
            loading={activity.loading}
            failed={activity.failed}
            unreadable={recordsUnreadable}
            chatHref={activity.chatsOn ? (cid) => withPrj(`${routePath(ROUTE_ROLES.conversations)}/${encodeURIComponent(cid)}`) : undefined}
            runHref={activity.runsOn ? (rid) => withPrj(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(rid)}`) : undefined}
            chatsAllHref={activity.chatsOn ? withPrj(routePath(ROUTE_ROLES.conversations)) : undefined}
            runsAllHref={activity.runsOn ? withPrj(routePath(ROUTE_ROLES.runs)) : undefined}
            nowMs={now}
          />
        </div>
      )}
      {copyDialog.dialog}
      <ConfirmDialog
        open={deleting !== null}
        title={deleting === null ? "" : m.home.configDeleteTitle(deleting.name)}
        confirmLabel={m.home.configDelete}
        cancelLabel={appMessages.common.cancel}
        danger
        onConfirm={() => void removeConfigRow()}
        onCancel={() => setDeleting(null)}
      >
        {m.home.configDeleteBody}
      </ConfirmDialog>
      {resetOpen ? (
        <ManifestResetDialog
          name={view.project.name}
          description={view.project.description ?? ""}
          configDir={view.config_dir ?? dirFallback}
          blockedReason={view.config_writable === false ? text("projects.blocked.edit") : undefined}
          onSubmit={submitReset}
          onClose={() => setResetOpen(false)}
        />
      ) : null}
    </div>
  );
}
