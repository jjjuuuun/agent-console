import { useState } from "react";
import type { DeletePlan, Project, ProjectDeleteMode } from "@agent-console/contracts/projects";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { projectMessages as t } from "./messages";

export interface DeleteProjectDialogProps {
  project: Project;
  /** 삭제 계획(null = 불러오는 중) */
  plan: DeletePlan | null;
  busy?: boolean;
  error?: string | null;
  onConfirm: (mode: ProjectDeleteMode) => void;
  onClose: () => void;
}

/**
 * 프로젝트 삭제 확인(표현 전용): 소속 항목을 공용으로 옮길지 함께 삭제할지 확인 단계에서 고른다.
 * 모드 목록은 문구 표(`manage.deleteModes`)의 키이고 기본 선택은 서버 계획의 `default_mode`다.
 */
export function DeleteProjectDialog({ project, plan, busy, error, onConfirm, onClose }: DeleteProjectDialogProps) {
  const [picked, setPicked] = useState<ProjectDeleteMode | null>(null);
  const modes = Object.keys(t.manage.deleteModes) as ProjectDeleteMode[];
  const count = plan?.definitions?.length ?? 0;
  const mode = picked ?? plan?.default_mode ?? modes[0] ?? "move_to_shared";
  return (
    <Dialog
      open
      title={t.manage.deleteTitle(project.name)}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{t.manage.cancel}</Button>
          <Button variant="danger" loading={busy === true} disabled={plan === null} onClick={() => onConfirm(mode)}>{t.manage.deleteConfirm}</Button>
        </>
      }
    >
      <div className="lib-form">
        {error ? <Banner tone="danger">{error}</Banner> : null}
        <p className="ac-text">{plan === null ? "…" : t.manage.deleteBody(count)}</p>
        {count > 0 ? (
          <fieldset className="prj-related">
            <legend>{t.manage.deleteItems}</legend>
            <ul className="lib-issue-list">
              {(plan?.definitions ?? []).map((d) => (
                <li key={`${d.kind}/${d.id}`}>{d.name ?? d.id} <span className="app-muted ac-mono">{d.kind}</span></li>
              ))}
            </ul>
          </fieldset>
        ) : null}
        {count > 0 ? (
          <div role="radiogroup" aria-label={t.manage.deleteBody(count)} className="prj-modes">
            {modes.map((m) => (
              <label key={m} className="prj-check prj-mode-option">
                <input type="radio" name="prj-delete-mode" checked={mode === m} onChange={() => setPicked(m)} />
                <span className="prj-mode-text">
                  <strong>{t.manage.deleteModes[m]?.label ?? m}</strong>
                  <span className="app-muted lib-field-note">{t.manage.deleteModes[m]?.description ?? ""}</span>
                </span>
              </label>
            ))}
          </div>
        ) : null}
        {(plan?.warnings ?? []).length > 0 ? (
          <Banner tone="warning">
            <ul className="lib-issue-list">
              {(plan?.warnings ?? []).map((w, i) => (
                <li key={`${w.code}-${i}`}>{w.message}</li>
              ))}
            </ul>
          </Banner>
        ) : null}
      </div>
    </Dialog>
  );
}
