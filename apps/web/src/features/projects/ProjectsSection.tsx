import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { DeletePlan, Project, ProjectDeleteMode, ProjectUpdate } from "@agent-console/contracts/projects";
import { Banner, Button, EmptyState, useToast } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { queryKeys, useApiQuery } from "../../app/queries";
import { useStorage } from "../../app/StorageContext";
import { DeleteProjectDialog } from "./DeleteProjectDialog";
import { ProjectEditForm } from "./ProjectEditForm";
import { ProjectGuide } from "./ProjectGuide";
import { ScopeIssuesList } from "./ScopeIssues";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";

export const GUIDE_DISMISSED_KEY = "ac.projectGuideDismissed";

/**
 * 설정 > 프로젝트 섹션(컨테이너): 프로젝트 목록 + 선택한 프로젝트 고치기·삭제 + 첫 프로젝트 안내.
 * 프로젝트 기능이 꺼져 있으면 섹션 자체가 없으므로(설정 섹션 `requires`) 여기서는 그 경우를 다루지 않는다.
 */
export function ProjectsSection() {
  const p = useProjects();
  if (!p.enabled) return null;
  return <ProjectsSectionBody />;
}

function ProjectsSectionBody() {
  const p = useProjects();
  const toast = useToast();
  const storage = useStorage();
  const queryClient = useQueryClient();
  const client = p.client;
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(() => storage.get(GUIDE_DISMISSED_KEY) === "1");
  const selectedId = pickedId !== null && p.projects.some((x) => x.id === pickedId) ? pickedId : (p.current ?? p.projects[0]?.id ?? null);
  const selected = p.projects.find((x) => x.id === selectedId);

  // 선택한 프로젝트의 최신 본문과 해시(고칠 때 If-Match)
  const detail = useQuery({
    queryKey: ["list", "project", selectedId],
    queryFn: () => (client as NonNullable<typeof client>).getProjectVersioned(selectedId as string),
    enabled: client !== undefined && selectedId !== null,
  });
  // 저장 실패는 그 프로젝트를 보는 동안만 보인다(다른 프로젝트로 옮기면 사라진다)
  const [failure, setFailure] = useState<{ id: string | null; error: string; conflict: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const saveError = failure?.id === selectedId ? failure.error : null;
  const conflict = failure?.id === selectedId && failure.conflict;

  const conversations = useApiQuery(queryKeys.list("conversations"), (rest) => rest.listConversations(), { enabled: dismissed === false && selected !== undefined });
  const hasConversation = (conversations.data ?? []).some((c) => c.project_id === selected?.id);

  const [deleting, setDeleting] = useState<{ project: Project; plan: DeletePlan | null; error: string | null; busy: boolean } | null>(null);

  const save = (patch: ProjectUpdate) => {
    if (client === undefined || selectedId === null) return;
    setSaving(true);
    setFailure(null);
    client
      .updateProject(selectedId, patch, detail.data?.version_hash)
      .then(async () => {
        toast({ tone: "success", text: t.manage.saved });
        await Promise.all([p.refresh(), detail.refetch()]);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 412) setFailure({ id: selectedId, error: t.manage.conflict, conflict: true });
        else setFailure({ id: selectedId, error: describeError(e, t.manage.saveFailed).message, conflict: false });
      })
      .finally(() => setSaving(false));
  };

  const askDelete = (project: Project) => {
    if (client === undefined) return;
    setDeleting({ project, plan: null, error: null, busy: false });
    client
      .getDeletePlan(project.id)
      .then((plan) => setDeleting((cur) => (cur === null ? cur : { ...cur, plan })))
      .catch((e: unknown) => setDeleting((cur) => (cur === null ? cur : { ...cur, error: describeError(e, t.manage.deleteFailed).message })));
  };
  const confirmDelete = (mode: ProjectDeleteMode) => {
    if (client === undefined || deleting === null) return;
    const { project } = deleting;
    setDeleting({ ...deleting, busy: true, error: null });
    client
      .deleteProject(project.id, { mode })
      .then(async () => {
        if (p.current === project.id) p.setCurrent(null);
        setDeleting(null);
        toast({ tone: "success", text: t.manage.deleted(project.name) });
        await p.refresh();
        // 지운 프로젝트의 상세 쿼리는 버리고 다시 부르지 않는다(404 방지). 나머지 목록만 새로 고친다.
        queryClient.removeQueries({ queryKey: ["list", "project", project.id] });
        await queryClient.invalidateQueries({ queryKey: ["list"], predicate: (q) => !(q.queryKey[1] === "project" && q.queryKey[2] === project.id) });
      })
      .catch((e: unknown) => setDeleting((cur) => (cur === null ? cur : { ...cur, busy: false, error: describeError(e, t.manage.deleteFailed).message })));
  };

  const guideProject = selected ?? p.currentProject;
  const dismiss = () => {
    storage.set(GUIDE_DISMISSED_KEY, "1");
    setDismissed(true);
  };
  const sorted = useMemo(() => [...p.projects].sort((a, b) => a.name.localeCompare(b.name, "ko")), [p.projects]);

  return (
    <div className="prj-section">
      {dismissed ? null : (
        <ProjectGuide
          projects={p.projects}
          project={guideProject}
          hasConversation={hasConversation}
          onCreate={() => p.requestCreate((created) => setPickedId(created.id))}
          onConfigure={() => document.getElementById("prj-edit-region")?.querySelector<HTMLElement>("input, textarea")?.focus()}
          onDismiss={dismiss}
        />
      )}
      <ScopeIssuesList />
      {p.projects.length === 0 ? (
        <EmptyState title={t.manage.empty} description={t.manage.emptyBody} action={<Button variant="primary" onClick={() => p.requestCreate()}>{t.manage.create}</Button>} />
      ) : (
        <div className="prj-manage">
          <div className="prj-manage-list">
            <div className="prj-manage-head">
              <Button size="sm" variant="primary" onClick={() => p.requestCreate((created) => setPickedId(created.id))}>{t.manage.create}</Button>
            </div>
            <ul className="prj-list-plain" aria-label={t.manage.listLabel}>
              {sorted.map((x) => (
                <li key={x.id}>
                  <button type="button" className="prj-pick" aria-pressed={x.id === selectedId} onClick={() => setPickedId(x.id)} title={x.description || x.name}>
                    <span className="ac-ellipsis">{x.name}</span>
                    {x.id === p.current ? <span className="app-muted">{t.manage.isCurrent}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div id="prj-edit-region" className="prj-manage-body" role="region" aria-label={selected?.name ?? t.manage.select}>
            {detail.isError ? (
              <Banner tone="danger" actions={<Button size="sm" onClick={() => void detail.refetch()}>{t.manage.retry}</Button>}>{t.manage.loadFailed}</Banner>
            ) : null}
            {conflict ? <Button size="sm" onClick={() => { setFailure(null); void detail.refetch(); }}>{t.manage.reload}</Button> : null}
            {detail.data === undefined || selected === undefined ? null : (
              <ProjectEditForm
                key={`${selected.id}:${detail.data.version_hash ?? ""}`}
                project={detail.data.value}
                busy={saving}
                error={saveError}
                onSave={save}
                onDelete={() => askDelete(detail.data.value)}
                isCurrent={p.current === selected.id}
                onSwitch={() => p.setCurrent(selected.id)}
              />
            )}
          </div>
        </div>
      )}
      {deleting === null ? null : (
        <DeleteProjectDialog project={deleting.project} plan={deleting.plan} busy={deleting.busy} error={deleting.error} onConfirm={confirmDelete} onClose={() => setDeleting(null)} />
      )}
    </div>
  );
}
