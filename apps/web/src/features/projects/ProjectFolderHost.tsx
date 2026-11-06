import { useCallback, useMemo } from "react";
import { useToast } from "@agent-console/ui";
import type { ProjectView } from "@agent-console/contracts/projects";
import { createProjectsText, statusInfo } from "@agent-console/projects";
import { useApi } from "../../app/ApiContext";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { ProjectFolderDialog, type FolderSubmit, type RepathTarget } from "./ProjectFolderDialog";
import { useFolderApi } from "./useFolderApi";

/** 열려 있는 폴더 대화상자 요청. */
export type FolderRequest =
  | { mode: "add"; onAdded?: ((view: ProjectView) => void) | undefined }
  | { mode: "repath"; view: ProjectView };

export interface ProjectFolderHostProps {
  request: FolderRequest;
  projects: readonly ProjectView[];
  /** 서버 값이 바뀐 뒤 목록을 다시 읽는다 */
  refresh: () => Promise<void>;
  /** 새·다시 등록된 프로젝트를 현재로 정하고 홈으로 간다 */
  openHome: (id: string) => void;
  onClose: () => void;
}

const text = createProjectsText();

/** 보기 값 -> 경로 다시 지정 대상(상태 칩 글자 포함). */
export function repathTarget(view: ProjectView): RepathTarget {
  const info = statusInfo(view);
  return {
    id: view.project.id,
    name: view.project.name,
    folder: view.project.folder,
    statusLabel: info.plain ? undefined : text(info.label),
    configDir: view.config_dir ?? undefined,
  };
}

/**
 * 폴더 대화상자 컨테이너: 서버 호출(등록·다시 등록·경로 변경)·토스트·홈 이동을 대화상자(표현)에 잇는다.
 * 대화상자는 요청이 있을 때만 마운트되어 열 때마다 새로 시작한다.
 */
export function ProjectFolderHost({ request, projects, refresh, openHome, onClose }: ProjectFolderHostProps) {
  const { rest } = useApi();
  const toast = useToast();
  const nameOf = useCallback((id: string) => projects.find((p) => p.project.id === id)?.project.name, [projects]);
  const api = useFolderApi(nameOf, request.mode === "repath" ? { excludeProjectId: request.view.project.id } : {});
  const target = useMemo(() => (request.mode === "repath" ? repathTarget(request.view) : undefined), [request]);

  const onSubmit = async (v: FolderSubmit) => {
    if (v.kind === "repath" && request.mode === "repath") {
      const { value } = await rest.updateProject(request.view.project.id, { folder: v.folder }, request.view.version_hash ?? undefined);
      await refresh();
      toast({ tone: "success", text: m.dialog.repathDone });
      onClose();
      openHome(value.project.id);
      return;
    }
    if (v.kind === "reregister") {
      const { value } = await rest.updateProject(v.projectId, { archived: false });
      await refresh();
      toast({ tone: "success", text: m.dialog.reregistered(value.project.name) });
      onClose();
      openHome(value.project.id);
      return;
    }
    if (v.kind === "add") {
      const { value } = await rest.createProject({
        folder: v.folder,
        name: v.name,
        ...(v.id === undefined ? {} : { id: v.id }),
        ...(v.description === undefined ? {} : { description: v.description }),
      });
      await refresh();
      toast({
        tone: v.manifestInvalid ? "warning" : "success",
        text: v.manifestInvalid ? m.dialog.addedInvalid(value.project.name) : v.adopted !== null ? m.dialog.addedAdopted(value.project.name, v.adopted) : m.dialog.added(value.project.name),
      });
      onClose();
      if (request.mode === "add") request.onAdded?.(value);
      openHome(value.project.id);
    }
  };

  return <ProjectFolderDialog mode={request.mode} target={target} api={api} onSubmit={onSubmit} onClose={onClose} onOpenProject={(id) => { onClose(); openHome(id); }} projectName={nameOf} />;
}
