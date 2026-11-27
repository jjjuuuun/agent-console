import type { ReactNode } from "react";
import { PageHeader } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { NoProjectState } from "./NoProjectState";
import { useScopeMessages } from "./scopeMessages";
import { useProjects } from "./ProjectsContext";

/** 게이트가 보는 상태. `ready`·`off`는 화면 본문을 그대로 그린다. */
export type ProjectGateState = "off" | "loading" | "error" | "none" | "ready";

/**
 * 프로젝트 문맥 화면의 본문 상태: 프로젝트 기능이 꺼져 있으면 `off`(각 화면이 단독 동작), 목록을 처음 받기 전은 `loading`,
 * 조회 실패는 `error`(0개로 단정하지 않는다), 등록 프로젝트가 0개면 `none`, 그 밖에는 `ready`(현재 프로젝트가 있다).
 */
export function useProjectGateState(): ProjectGateState {
  const p = useProjects();
  if (!p.enabled) return "off";
  if (p.loadFailed && !p.loaded) return "error";
  if (!p.loaded) return "loading";
  return p.projects.every((x) => x.archived === true) ? "none" : "ready";
}

export interface ProjectGateProps {
  /** 제목만 남는 머리의 제목 */
  title: string;
  /** 공용 구성 화면 주소(없으면 링크 버튼 없음) */
  libraryHref?: string | undefined;
  /** 프로젝트 0개일 때: `"state"`(기본) = `NoProjectState`로 대체, `"pass"` = 화면을 그대로 그린다(화면이 공용으로 동작) */
  none?: "state" | "pass" | undefined;
  children: ReactNode;
}

/**
 * 프로젝트 문맥 화면을 감싸는 문지기(screen-projects §7.2): 프로젝트가 0개면 본문 전체를 `NoProjectState` 하나로 대체한다
 * (필터·탭·화면 액션 없음, `PageHeader`는 제목만). 로딩은 스켈레톤, 조회 실패는 `ErrorBlock` + 다시 시도.
 * 기능 이름을 모르므로 어떤 화면이든 감쌀 수 있다.
 */
export function ProjectGate({ title, libraryHref, none, children }: ProjectGateProps) {
  const scopeMessages = useScopeMessages();
  const p = useProjects();
  const state = useProjectGateState();
  if (state === "off" || state === "ready" || (state === "none" && none === "pass")) return <>{children}</>;
  let body: ReactNode;
  if (state === "loading") {
    body = (
      <div className="app-skeleton" role="status" aria-busy="true" aria-label={scopeMessages.gate.loading}>
        {Array.from({ length: 6 }, (_, i) => <div key={i} className="app-skeleton-row" />)}
      </div>
    );
  } else if (state === "error") {
    body = <ErrorBlock title={scopeMessages.gate.loadFailed} retryLabel={scopeMessages.gate.retry} onRetry={() => void p.refresh()} />;
  } else {
    body = <NoProjectState onAddFolder={() => p.requestAddFolder()} libraryHref={libraryHref} />;
  }
  return (
    <div className="app-screen-frame" data-screen-state={state}>
      <PageHeader title={title} />
      <div className="prj-gate-body">{body}</div>
    </div>
  );
}
