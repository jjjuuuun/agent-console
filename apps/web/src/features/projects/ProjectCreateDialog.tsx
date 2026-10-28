import { useId, useState } from "react";
import type { ProjectCreate } from "@agent-console/contracts/projects";
import { NewDefinitionDialog } from "../library";
import { projectMessages as t } from "./messages";

export interface ProjectCreateDialogProps {
  open: boolean;
  /** 이미 있는 프로젝트 id(중복 즉시 표시) */
  existingIds: ReadonlySet<string>;
  busy?: boolean;
  error?: string | null;
  onSubmit: (body: ProjectCreate) => void;
  onClose: () => void;
}

/** 새 프로젝트 만들기(표현 전용): 이름·id·설명 + 작업 폴더(선택). 열 때마다 새로 시작하도록 호출자가 `open`일 때만 렌더한다. */
export function ProjectCreateDialog({ open, existingIds, busy, error, onSubmit, onClose }: ProjectCreateDialogProps) {
  const [directory, setDirectory] = useState("");
  const uid = useId();
  return (
    <NewDefinitionDialog
      open={open}
      title={t.create.title}
      submitLabel={t.create.submit}
      existingIds={existingIds}
      fallbackId="project"
      {...(busy === undefined ? {} : { busy })}
      {...(error === undefined ? {} : { error })}
      onClose={onClose}
      onSubmit={(v) => {
        const wd = directory.trim();
        // 계약 0.11.0: 폴더 필수(비우면 서버가 422로 거절한다). 폴더 고르기 화면은 5.7R.33n.
        onSubmit({ id: v.id, name: v.name, folder: wd, ...(v.description === "" ? {} : { description: v.description }) });
      }}
      extra={
        <div className="lib-field">
          <label htmlFor={`${uid}-wd`}>{t.create.workingDirectory}</label>
          <input id={`${uid}-wd`} className="ac-input ac-mono" value={directory} onChange={(e) => setDirectory(e.target.value)} aria-describedby={`${uid}-wd-note`} />
          <span id={`${uid}-wd-note`} className="app-muted lib-field-note">{t.create.workingDirectoryHint}</span>
        </div>
      }
    />
  );
}
