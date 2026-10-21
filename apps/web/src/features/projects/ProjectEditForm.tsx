import { useId, useState, type FormEvent } from "react";
import type { Project, ProjectUpdate } from "@agent-console/contracts/projects";
import { Banner, Button } from "@agent-console/ui";
import { projectMessages as t } from "./messages";

export interface ProjectEditFormProps {
  project: Project;
  busy?: boolean;
  error?: string | null;
  /** 바뀐 필드만 담아 부른다 */
  onSave: (patch: ProjectUpdate) => void;
  onDelete: () => void;
  /** 이 프로젝트가 현재 프로젝트인가 */
  isCurrent: boolean;
  onSwitch: () => void;
}

const splitList = (text: string): string[] => text.split(",").map((s) => s.trim()).filter((s) => s !== "");

/**
 * 프로젝트 하나 고치기(표현 전용): 이름·설명·작업 폴더·로그 연결(쉼표 목록). 열 때마다 새 초안으로 시작하도록 호출자가 `key`를 준다.
 * 프로젝트 층 설정(settings)·꼬리표는 이 폼이 건드리지 않는다(생략한 필드는 서버가 그대로 둔다).
 */
export function ProjectEditForm({ project, busy, error, onSave, onDelete, isCurrent, onSwitch }: ProjectEditFormProps) {
  const uid = useId();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const [directory, setDirectory] = useState(project.working_directory ?? "");
  const [logs, setLogs] = useState((project.log_projects ?? []).join(", "));

  const patch: ProjectUpdate = {};
  if (name.trim() !== project.name) patch.name = name.trim();
  if (description.trim() !== (project.description ?? "")) patch.description = description.trim();
  if (directory.trim() !== (project.working_directory ?? "")) patch.working_directory = directory.trim() === "" ? null : directory.trim();
  const nextLogs = splitList(logs);
  if (nextLogs.join("\u0000") !== (project.log_projects ?? []).join("\u0000")) patch.log_projects = nextLogs;
  const dirty = Object.keys(patch).length > 0;
  const invalid = name.trim() === "";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (dirty && !invalid && busy !== true) onSave(patch);
  };

  return (
    <form className="lib-form prj-edit" onSubmit={submit} aria-label={project.name}>
      {error ? <Banner tone="danger">{error}</Banner> : null}
      <div className="prj-edit-head">
        <code className="ac-mono app-muted">{project.id}</code>
        {isCurrent ? <span className="app-muted">{t.manage.isCurrent}</span> : <Button size="sm" onClick={onSwitch}>{t.manage.switchTo}</Button>}
      </div>
      <div className="lib-field">
        <label htmlFor={`${uid}-name`}>{t.manage.name}</label>
        <input id={`${uid}-name`} className="ac-input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} aria-invalid={invalid} />
      </div>
      <div className="lib-field">
        <label htmlFor={`${uid}-desc`}>{t.manage.description}</label>
        <textarea id={`${uid}-desc`} className="ac-input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <div className="lib-field">
        <label htmlFor={`${uid}-wd`}>{t.manage.workingDirectory}</label>
        <input id={`${uid}-wd`} className="ac-input ac-mono" value={directory} onChange={(e) => setDirectory(e.target.value)} aria-describedby={`${uid}-wd-note`} />
        <span id={`${uid}-wd-note`} className="app-muted lib-field-note">{t.manage.workingDirectoryHint}</span>
      </div>
      <div className="lib-field">
        <label htmlFor={`${uid}-logs`}>{t.manage.logProjects}</label>
        <input id={`${uid}-logs`} className="ac-input ac-mono" value={logs} onChange={(e) => setLogs(e.target.value)} aria-describedby={`${uid}-logs-note`} />
        <span id={`${uid}-logs-note`} className="app-muted lib-field-note">{t.manage.logProjectsHint}</span>
      </div>
      <div className="prj-edit-actions">
        <Button variant="primary" type="submit" loading={busy === true} disabled={!dirty || invalid}>{t.manage.save}</Button>
        <Button variant="danger" onClick={onDelete} disabled={busy === true}>{t.manage.delete}</Button>
      </div>
    </form>
  );
}
