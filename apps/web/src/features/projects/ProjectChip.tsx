import { useState } from "react";
import { Button, Icon, Popover, middleEllipsis } from "@agent-console/ui";
import type { ProjectView } from "@agent-console/contracts/projects";
import { createProjectsText, statusInfo } from "@agent-console/projects";
import { scopeMessages as m } from "./scopeMessages";
import { useProjects } from "./ProjectsContext";

const text = createProjectsText();

export interface ProjectChipViewProps {
  name: string;
  /** 전체 경로(칩에는 줄여 보이고 팝오버에는 전부 보인다) */
  folder: string;
  /** 문제 상태 문구(없으면 정상) */
  problem?: string | undefined;
  archived?: boolean | undefined;
  onOpenHome: () => void;
  onSwitch: () => void;
  onCopy: (path: string) => void;
}

/** 프로젝트 칩 표현(screen-projects §7.1): 이름 + 경로, 클릭하면 전체 경로·홈·바꾸기 팝오버. 데이터와 콜백은 props. */
export function ProjectChipView({ name, folder, problem, archived, onOpenHome, onSwitch, onCopy }: ProjectChipViewProps) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelLabel={m.chip.popover}
      align="end"
      className="prj-pchip-wrap"
      panelClassName="prj-pchip-panel"
      renderTrigger={(trigger) => (
        <button type="button" {...trigger} className="prj-pchip" data-problem={problem === undefined ? undefined : "true"} aria-label={m.chip.aria(name, folder)} title={problem ?? folder}>
          <Icon name="folder" size={14} />
          <span className="prj-pchip-name ac-ellipsis">{name}</span>
          <span className="prj-pchip-path ac-ellipsis" aria-hidden="true">{middleEllipsis(folder, 14, 22)}</span>
        </button>
      )}
    >
      {({ close }) => (
        <div className="prj-pchip-body">
          <strong className="ac-ellipsis">{name}</strong>
          <span className="app-muted">{m.chip.folderLabel}</span>
          <span className="prj-pchip-full">{folder}</span>
          <div>
            <Button size="sm" onClick={() => onCopy(folder)}>{m.chip.copy}</Button>
          </div>
          {archived === true ? <span className="app-muted">{m.chip.archived}</span> : null}
          {problem === undefined ? null : <span role="status">{problem}</span>}
          <div className="prj-pchip-actions">
            <Button size="sm" onClick={() => { close(); onOpenHome(); }}>{m.chip.home}</Button>
            <Button size="sm" onClick={() => { close(); onSwitch(); }}>{m.chip.switch}</Button>
          </div>
        </div>
      )}
    </Popover>
  );
}

function problemOf(view: ProjectView | undefined): string | undefined {
  if (view === undefined) return undefined;
  const info = statusInfo(view);
  return info.plain ? undefined : text(info.label);
}

/**
 * 현재 프로젝트 칩(컨테이너). 프로젝트 기능이 꺼져 있거나 현재 프로젝트가 없으면 아무것도 그리지 않는다.
 * 기능 화면의 `PageHeader` actions 맨 앞에 둔다.
 */
export function ProjectChip() {
  const p = useProjects();
  const view = p.currentView;
  if (!p.enabled || view === undefined) return null;
  const copy = (path: string) => void navigator.clipboard?.writeText(path);
  return (
    <ProjectChipView
      name={view.project.name}
      folder={view.project.folder ?? ""}
      problem={problemOf(view)}
      archived={view.project.archived}
      onOpenHome={() => p.openHome(view.project.id)}
      onSwitch={() => p.setSwitcherOpen(true)}
      onCopy={copy}
    />
  );
}
