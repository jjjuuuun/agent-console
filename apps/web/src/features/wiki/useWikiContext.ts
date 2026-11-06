import { useMemo } from "react";
import { createProjectsText, projectAbilities } from "@agent-console/projects";
import type { WikiCapabilities, WikiInfo, WikiLimits } from "@agent-console/contracts/wiki";
import { useProjectId } from "../../app/projectScope";
import { useProjects } from "../projects";
import { useWikiInfo } from "./useWikiApi";
import { wikiMessages } from "./messages";

const text = createProjectsText();

/** 위키 화면 하나가 쓰는 문맥: 현재 프로젝트·쓰기 가능 여부와 이유·서버 능력. 화면 컴포넌트는 이 값만 읽는다. */
export interface WikiContext {
  /** 현재 프로젝트 id(프로젝트 기능이 꺼졌거나 없으면 null = 단독 루트) */
  projectId: string | null;
  projectName: string | undefined;
  /** 폴더 문제·쓰기 불가로 만들기·편집·이름 바꾸기·지우기·되돌리기가 막혔는가 */
  readOnly: boolean;
  /** 막힌 이유(`projects.blocked.*` 문구). 막히지 않았으면 undefined */
  readOnlyReason: string | undefined;
  /** 기록 파일을 쓸 수 없어 이번 변경은 기록되지 않는가(저장은 된다). 되돌리기는 막힌다 */
  recordsUnwritable: boolean;
  /** 서버 능력. 아직 모르거나 값이 없으면 모두 false(켜진 것이 확인된 기능만 그린다) */
  capabilities: Readonly<Required<WikiCapabilities>>;
  limits: WikiLimits | undefined;
  info: WikiInfo | undefined;
  /** 위키 페이지 폴더(프로젝트 폴더 기준 상대 경로, 서버 값). 모르면 undefined */
  pagesRoot: string | undefined;
}

const NONE: Required<WikiCapabilities> = { history: false, search: false, runs: false, rules_library: false, import_export: false };

export function useWikiContext(): WikiContext {
  const projectId = useProjectId();
  const projects = useProjects();
  const info = useWikiInfo().data;
  const view = projectId === null ? undefined : projects.views.find((v) => v.project.id === projectId);
  return useMemo(() => {
    const abilities = view === undefined ? undefined : projectAbilities(view, { recordsWritable: view.records_writable !== false });
    const editBlocked = abilities?.edit.allowed === false ? abilities.edit.reason : null;
    // 위키 정보(`writable === false`)는 프로젝트 목록보다 새 값이다: 폴더를 쓸 수 없으면 편집 막힘 이유와 같은 문구로 읽기 전용이 된다(null/생략 = 쓸 수 있다고 본다)
    const infoBlocked = info?.writable === false;
    return {
      projectId,
      projectName: view?.project.name,
      readOnly: editBlocked !== null || infoBlocked,
      readOnlyReason: editBlocked !== null ? text(editBlocked) : infoBlocked ? text("projects.blocked.edit") : undefined,
      recordsUnwritable: view?.records_writable === false,
      capabilities: { ...NONE, ...(info?.capabilities ?? {}) } as Required<WikiCapabilities>,
      limits: info?.limits,
      info,
      pagesRoot: info?.pages_root,
    };
  }, [projectId, view, info]);
}

/** 읽기 전용 이유가 비었을 때의 기본 문구(요청이 막힌 경우). */
export const READONLY_FALLBACK = wikiMessages.readonly.title;
