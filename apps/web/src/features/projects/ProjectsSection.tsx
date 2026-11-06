import { useMemo, useState } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import type { AssignProjectRequest, AssignProjectResult, ProjectCounts, ProjectView, RecordsMoveRequest, RecordsMoveResult } from "@agent-console/contracts/projects";
import { createProjectsText, statusInfo } from "@agent-console/projects";
import { Button, EmptyState, useToast } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { lookupMessage } from "../../app/messages";
import { queryKeys } from "../../app/queries";
import { useApi } from "../../app/ApiContext";
import { useStorage } from "../../app/StorageContext";
import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { AssignProjectDialog, type AssignTarget } from "./AssignProjectDialog";
import { RecordsMoveDialog, type RecordsMoveOutcome } from "./RecordsMoveDialog";
import { AppRecordsBlock, ArchivedProjects, LegacyConfigBlock, LegacyRecordsBlock, ProjectsTable, SectionError, type ArchivedRow, type CleanupRow, type LegacyRow, type ProjectRow, type RecordsRow } from "./SettingsBlocks";
import { assignSummary, countFor, mergeMoveResults } from "./settingsLib";
import { scopeMessages } from "./scopeMessages";
import { projectHomePath, useProjects } from "./ProjectsContext";
import { regionProjects } from "./projectRegionLib";
import { useCopyDialog } from "./useCopyDialog";

const t = scopeMessages.settings;
const text = createProjectsText();
const dismissedKey = (feature: string) => `ac.legacy.dismissed.${feature}`;

/** 앱 기록이 있는 기능 하나: 개수 조회·넣기·폴더로 옮기기 호출과 제목을 얻는 라우트 역할(제목은 라우트 데이터). */
interface RecordFeature {
  key: string;
  role: string;
  counts: (rest: RestClient) => Promise<ProjectCounts>;
  assign: (rest: RestClient, request: AssignProjectRequest) => Promise<AssignProjectResult>;
  move: (rest: RestClient, request: RecordsMoveRequest) => Promise<RecordsMoveResult>;
}
/** 순서가 중요하다: 채팅(대화가 자기 실행을 먼저 가져간다) → 실행. */
const RECORD_FEATURES: readonly RecordFeature[] = [
  { key: "conversations", role: "conversations", counts: (r) => r.getConversationProjectCounts(), assign: (r, q) => r.assignConversationsToProject(q), move: (r, q) => r.moveConversationsToProject(q) },
  { key: "runs", role: "runs", counts: (r) => r.getRunProjectCounts(), assign: (r, q) => r.assignRunsToProject(q), move: (r, q) => r.moveRunsToProject(q) },
];

function featureLabel(f: RecordFeature): string {
  const route = routeServing(DEFAULT_ROUTES, f.role);
  return route === undefined ? f.key : lookupMessage(route.titleKey);
}

function dateText(epochSeconds: number | null | undefined): string | null {
  if (epochSeconds == null) return null;
  const d = new Date(epochSeconds * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function overlaps(a: string, b: string): boolean {
  const n = (x: string) => x.replace(/[\\/]+$/, "").replace(/\\/g, "/").toLowerCase();
  const [x, y] = [n(a), n(b)];
  return x === y || x.startsWith(`${y}/`) || y.startsWith(`${x}/`);
}

/**
 * 설정 > 프로젝트 섹션(컨테이너, screen-projects §8): 관리 작업만 둔다 — 등록 목록(경로 다시 지정·등록 해제), 등록 해제된 프로젝트,
 * 프로젝트 없는 이전 기록 넣기, 옛 프로젝트 전용 구성 옮기기, 앱에 남은 기록 옮기기. 모두 즉시 적용되며 설정 저장 흐름 밖이다.
 * 프로젝트 기능이 꺼져 있으면 섹션 자체가 없으므로(설정 섹션 `requires`) 그 경우는 아무것도 그리지 않는다.
 */
export function ProjectsSection() {
  const p = useProjects();
  if (!p.enabled) return null;
  return <ProjectsSectionBody />;
}

type Dialog =
  | { kind: "assign"; feature: RecordFeature }
  | { kind: "move"; view: ProjectView };

function ProjectsSectionBody() {
  const p = useProjects();
  const { rest } = useApi();
  const toast = useToast();
  const storage = useStorage();
  const queryClient = useQueryClient();
  const copy = useCopyDialog();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<RecordsMoveOutcome | null>(null);
  const [reregistering, setReregistering] = useState<string | null>(null);
  const [showHidden, setShowHidden] = useState(false);
  // 접어 둔 기능(저장값이 없거나 저장이 막혀도 이번 화면에서는 접힌다)
  const [kept, setKept] = useState<ReadonlySet<string>>(new Set());

  const active = useMemo(() => p.views.filter((v) => v.project.archived !== true).sort((a, b) => a.project.name.localeCompare(b.project.name, "ko")), [p.views]);
  const archived = useMemo(() => p.views.filter((v) => v.project.archived === true), [p.views]);
  const activeIds = useMemo(() => new Set(regionProjects(p.projects).map((x) => x.id)), [p.projects]);

  const counts = useQueries({
    queries: RECORD_FEATURES.map((f) => ({
      queryKey: queryKeys.list("project-record-counts", { feature: f.key }),
      queryFn: () => f.counts(rest),
      retry: false,
      meta: { silentBackgroundError: true },
    })),
  });
  const countOf = (f: RecordFeature, id: string | null) => countFor(counts[RECORD_FEATURES.indexOf(f)]?.data, id);

  // 옛 프로젝트 전용 구성 수: 프로젝트마다 옛 방식 정의의 복사 계획(항목 수)을 읽는다
  const legacy = useQueries({
    queries: active.map((v) => ({
      queryKey: queryKeys.list("project-legacy", { id: v.project.id, hash: v.version_hash ?? "" }),
      queryFn: () => rest.planLegacyCopy(v.project.id),
      retry: false,
      meta: { silentBackgroundError: true },
    })),
  });

  const refreshAll = async () => {
    await p.refresh();
    await queryClient.invalidateQueries({ queryKey: ["list"] });
  };

  // ---- 표 ----
  const rows: ProjectRow[] = active.map((v) => {
    const info = statusInfo(v);
    return { id: v.project.id, name: v.project.name, folder: v.project.folder ?? "", href: projectHomePath(v.project.id), statusLabel: text(info.label), statusTone: info.tone, plain: info.plain };
  });
  const archivedRows: ArchivedRow[] = archived.map((v) => {
    const chats = countOf(RECORD_FEATURES[0] as RecordFeature, v.project.id);
    const runs = countOf(RECORD_FEATURES[1] as RecordFeature, v.project.id);
    const folder = v.project.folder ?? "";
    const clash = folder !== "" && active.some((a) => a.project.folder != null && overlaps(a.project.folder, folder));
    return {
      id: v.project.id,
      name: v.project.name,
      folder,
      archivedAt: dateText(v.project.archived_at),
      stored: chats + runs > 0 ? t.appStored(chats, runs) : null,
      blocked: clash ? t.reregisterBlocked : undefined,
    };
  });

  // ---- 프로젝트 없는 이전 기록 ----
  const dismissed = (f: RecordFeature) => kept.has(f.key) || storage.get(dismissedKey(f.key)) === "1";
  const withNone = RECORD_FEATURES.filter((f) => countOf(f, null) > 0);
  const legacyRows: LegacyRow[] = withNone.filter((f) => showHidden || !dismissed(f)).map((f) => ({ key: f.key, feature: featureLabel(f), count: countOf(f, null) }));
  const hiddenCount = showHidden ? 0 : withNone.filter(dismissed).length;

  // ---- 옛 프로젝트 전용 구성 ----
  const cleanupRows: CleanupRow[] = active
    .map((v, i) => ({ view: v, n: (legacy[i]?.data?.items ?? []).filter((it) => it.reason === "requested").length }))
    .filter((x) => x.n > 0)
    .map((x) => ({
      id: x.view.project.id,
      name: x.view.project.name,
      href: projectHomePath(x.view.project.id),
      count: x.n,
      blocked: x.view.config_writable === false ? text("projects.blocked.records_readonly") : undefined,
    }));

  // ---- 앱에 남은 기록 ----
  const recordRows: RecordsRow[] = [
    ...active.map((v): RecordsRow => ({
      id: v.project.id,
      name: v.project.name,
      href: projectHomePath(v.project.id),
      chats: countOf(RECORD_FEATURES[0] as RecordFeature, v.project.id),
      runs: countOf(RECORD_FEATURES[1] as RecordFeature, v.project.id),
      blocked: v.records_writable === false ? t.recordsMoveBlocked : undefined,
    })),
    // 같은 동작 버튼이 한 화면에 두 번 나오지 않게: 위 "이전 기록" 블록이 이미 그 개수를 보이면 "프로젝트 없음" 행은 뺀다
    ...(legacyRows.length > 0 || hiddenCount > 0 ? [] : [{ id: null, name: t.recordsNoProject, href: null, chats: countOf(RECORD_FEATURES[0] as RecordFeature, null), runs: countOf(RECORD_FEATURES[1] as RecordFeature, null) } as RecordsRow]),
  ];

  // ---- 동작 ----
  const closeDialog = () => {
    setDialog(null);
    setBusy(false);
    setDialogError(null);
    setOutcome(null);
  };

  const reregister = (id: string) => {
    setReregistering(id);
    rest
      .updateProject(id, { archived: false })
      .then(() => p.refresh())
      .catch((e: unknown) => toast({ tone: "danger", text: describeError(e, t.reregisterBlocked).message }))
      .finally(() => setReregistering(null));
  };

  const submitAssign = (feature: RecordFeature, projectId: string, direct: boolean) => {
    const name = p.names.get(projectId) ?? projectId;
    const requested = countOf(feature, null);
    setBusy(true);
    setDialogError(null);
    const run = direct
      ? feature.move(rest, { project_id: projectId, select: "null", remove_source: true }).then((r) => ({ ok: r.moved ?? 0, skipped: (r.skipped ?? 0) + (r.failed?.length ?? 0), total: requested }))
      : feature.assign(rest, { to: projectId, from_null: true }).then((r) => assignSummary(r, requested));
    run
      .then(async (s) => {
        toast({ tone: "success", text: s.skipped > 0 ? t.assignPartial(s.total, s.ok, s.skipped) : t.assignDone(featureLabel(feature), s.ok, name) });
        closeDialog();
        await refreshAll();
      })
      .catch((e: unknown) => {
        setBusy(false);
        setDialogError(describeError(e, t.assignFailed).message);
      });
  };

  const submitMove = async (view: ProjectView, removeSource: boolean) => {
    setBusy(true);
    setDialogError(null);
    const results: RecordsMoveResult[] = [];
    try {
      for (const f of RECORD_FEATURES) {
        if (countOf(f, view.project.id) === 0) continue;
        results.push(await f.move(rest, { project_id: view.project.id, select: "project", remove_source: removeSource }));
      }
    } catch (e: unknown) {
      setBusy(false);
      setDialogError(describeError(e, t.moveFailed).message);
      return;
    }
    const merged = mergeMoveResults(results);
    await refreshAll();
    setBusy(false);
    if (merged.failed.length > 0) {
      setOutcome(merged);
      return;
    }
    const chats = results[0]?.moved ?? 0;
    toast({ tone: "success", text: `${t.moveDone(chats, merged.moved - chats)}${merged.skipped > 0 ? ` ${t.moveSkipped(merged.skipped)}` : ""}` });
    closeDialog();
  };

  const assignTargets: AssignTarget[] = active.map((v) => {
    const info = statusInfo(v);
    return { id: v.project.id, name: v.project.name, folder: v.project.folder ?? "", problem: info.profile === "ready" || info.profile === "ready_readonly" ? undefined : text(info.label) };
  });

  const moveItems = async (id: string) => {
    try {
      const plan = await rest.planLegacyCopy(id);
      const items = (plan.items ?? []).filter((it) => it.reason === "requested").map((it) => ({ kind: it.kind, id: it.id }));
      copy.open({ direction: "move", project: id, start: "plan", items, onApplied: () => void queryClient.invalidateQueries({ queryKey: ["list", "project-legacy"] }) });
    } catch (e: unknown) {
      toast({ tone: "danger", text: describeError(e, t.loadFailed).message });
    }
  };

  const orphanCount = 0; // 프로젝트 없는/해제된 프로젝트의 옛 구성은 서버가 알려 주는 API가 아직 없다(검증 대기)

  return (
    <div className="prj-section" data-testid="settings-projects">
      <div className="prj-section-head">
        <div><Button size="sm" variant="primary" onClick={() => p.requestAddFolder()}>{`+ ${t.add}`}</Button></div>
      </div>
      {p.loadFailed ? <SectionError onRetry={() => void p.refresh()} /> : null}
      {!p.loaded && !p.loadFailed ? (
        <div className="app-skeleton" role="status" aria-busy="true" aria-label={scopeMessages.gate.loading}>
          {Array.from({ length: 3 }, (_, i) => <div key={i} className="app-skeleton-row" />)}
        </div>
      ) : p.loadFailed ? null : rows.length === 0 ? (
        <EmptyState title={t.empty} action={<Button variant="primary" onClick={() => p.requestAddFolder()}>{t.add}</Button>} />
      ) : (
        <ProjectsTable rows={rows} onRepath={(id) => p.requestRepath(id)} onUnregister={(id) => p.requestUnregister(id)} />
      )}
      <ArchivedProjects rows={archivedRows} busyId={reregistering} onReregister={reregister} onView={(id) => p.openHome(id)} />
      <LegacyRecordsBlock
        rows={legacyRows}
        hiddenCount={hiddenCount}
        onAssign={(key) => {
          const feature = RECORD_FEATURES.find((f) => f.key === key);
          if (feature !== undefined) setDialog({ kind: "assign", feature });
        }}
        onKeep={(key) => {
          storage.set(dismissedKey(key), "1");
          setKept((prev) => new Set(prev).add(key));
        }}
        onShowHidden={() => setShowHidden(true)}
      />
      <LegacyConfigBlock rows={cleanupRows} orphans={orphanCount} onMove={(id) => void moveItems(id)} />
      <AppRecordsBlock
        rows={recordRows}
        onMove={(id) => {
          const view = active.find((v) => v.project.id === id);
          if (view !== undefined) setDialog({ kind: "move", view });
        }}
        onAssignNone={() => {
          const feature = withNone[0];
          if (feature !== undefined) setDialog({ kind: "assign", feature });
        }}
      />
      {dialog?.kind === "assign" ? (
        <AssignProjectDialog
          feature={featureLabel(dialog.feature)}
          count={countOf(dialog.feature, null)}
          targets={assignTargets.filter((x) => activeIds.has(x.id))}
          directDefault={true}
          busy={busy}
          error={dialogError}
          onSubmit={(id, direct) => submitAssign(dialog.feature, id, direct)}
          onClose={closeDialog}
        />
      ) : null}
      {dialog?.kind === "move" ? (
        <RecordsMoveDialog
          projectName={dialog.view.project.name}
          folder={dialog.view.project.folder ?? ""}
          chats={countOf(RECORD_FEATURES[0] as RecordFeature, dialog.view.project.id)}
          runs={countOf(RECORD_FEATURES[1] as RecordFeature, dialog.view.project.id)}
          busy={busy}
          outcome={outcome}
          error={dialogError}
          onSubmit={(remove) => void submitMove(dialog.view, remove)}
          onClose={closeDialog}
        />
      ) : null}
      {copy.dialog}
    </div>
  );
}
