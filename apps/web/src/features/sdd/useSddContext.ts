import { useMemo } from "react";
import { createProjectsText, projectAbilities } from "@agent-console/projects";
import type { SddCapabilities, SddInfo } from "@agent-console/contracts/sdd";
import { useProjectId } from "../../app/projectScope";
import { useProjects } from "../projects";
import { useSddInfo } from "./useSddApi";

const text = createProjectsText();

/** 스펙 화면 하나가 쓰는 문맥: 현재 프로젝트·쓰기 가능 여부와 이유·서버 능력. 화면 컴포넌트는 이 값만 읽는다. */
export interface SddContext {
  /** 현재 프로젝트 id(프로젝트 기능이 꺼졌거나 없으면 null = 단독 루트) */
  projectId: string | null;
  projectName: string | undefined;
  /** 폴더 문제·쓰기 불가로 편집·상태 바꾸기·저장이 막혔는가 */
  readOnly: boolean;
  /** 막힌 이유(`projects.blocked.*` 문구). 막히지 않았으면 undefined */
  readOnlyReason: string | undefined;
  /** 실행을 막는 이유(기록 파일을 쓸 수 없음 등). 막히지 않았으면 undefined */
  runBlockedReason: string | undefined;
  /** 서버 능력. 아직 모르거나 값이 없으면 모두 false(켜진 것이 확인된 기능만 그린다) */
  capabilities: Readonly<Required<SddCapabilities>>;
  info: SddInfo | undefined;
  /** 스펙 문서 폴더(프로젝트 폴더 기준 상대 경로, 서버 값). 모르면 undefined */
  specRoot: string | undefined;
}

const NONE: Required<SddCapabilities> = { runs: false, templates: false, verification: false, automation: false, import_export: false };

export function useSddContext(): SddContext {
  const projectId = useProjectId();
  const projects = useProjects();
  const info = useSddInfo().data;
  const view = projectId === null ? undefined : projects.views.find((v) => v.project.id === projectId);
  return useMemo(() => {
    const abilities = view === undefined ? undefined : projectAbilities(view, { recordsWritable: view.records_writable !== false });
    const editBlocked = abilities?.edit.allowed === false ? abilities.edit.reason : null;
    const infoReadonly = info?.writable === false;
    const runBlocked = abilities?.start_run.allowed === false ? abilities.start_run.reason : null;
    return {
      projectId,
      projectName: view?.project.name,
      readOnly: editBlocked !== null || infoReadonly,
      readOnlyReason: editBlocked !== null ? text(editBlocked) : infoReadonly ? text("projects.blocked.edit") : undefined,
      runBlockedReason: runBlocked === null || runBlocked === undefined ? undefined : text(runBlocked),
      capabilities: { ...NONE, ...(info?.capabilities ?? {}) } as Required<SddCapabilities>,
      info,
      specRoot: info?.spec_root,
    };
  }, [projectId, view, info]);
}
