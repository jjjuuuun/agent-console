import { createContext, useContext, useEffect, useRef } from "react";

/**
 * 현재 프로젝트를 담는 주소 쿼리 이름. 로그 필터 `project`(로그 묶음 id)와 이름이 겹치면 안 되므로 따로 둔다.
 * 로그 화면은 이 이름을 화면 전용 파라미터로 보존한다(서버 필터로 보내지 않는다).
 */
export const CURRENT_PROJECT_PARAM = "prj";

/**
 * 현재 프로젝트 id를 화면 아래쪽에 알리는 가벼운 컨텍스트(프로젝트 기능이 공급, 없으면 null).
 * 프로젝트 기능 폴더를 import하지 않고도 새 대화에 `project_id`를 찍을 수 있게 한다(기능 폴더 사이 순환 방지).
 */
export const CurrentProjectContext = createContext<string | null>(null);

/**
 * 현재 프로젝트가 정해졌는지(프로젝트 기능 여부·목록 로딩이 끝났는지). 기본 true(공급자 없음 = 정해질 것이 없음).
 * 프로젝트 id를 질의 키·인자에 넣는 조회는 false인 동안 미뤄서, null -> 실제 id 전환으로 같은 조회가 두 번 나가지 않게 한다.
 */
export const ProjectScopeReadyContext = createContext<boolean>(true);

/** `ProjectScopeReadyContext` 값. */
export function useProjectScopeReady(): boolean {
  return useContext(ProjectScopeReadyContext);
}

/**
 * 새 대화·실행에 찍을 프로젝트 id. 모든 프로젝트 보기이거나 프로젝트 기능이 꺼져 있으면 null.
 */
export function useProjectId(): string | null {
  return useContext(CurrentProjectContext);
}

/** `project_id` 필드 조각(공용이면 빈 객체). 본문에 `...projectBody(id)`로 펼친다. */
export function projectBody(id: string | null): { project_id?: string } {
  return id === null ? {} : { project_id: id };
}

/**
 * 주소로 다른 프로젝트의 대화·실행을 연 뒤 현재 프로젝트를 그쪽으로 바꾸는 함수를 알리는 컨텍스트
 * (프로젝트 기능이 공급, 없으면 undefined = 바꿀 프로젝트가 없음). 기능 폴더 사이 import 없이 쓰게 한다.
 */
export const AdoptProjectContext = createContext<((id: string) => void) | undefined>(undefined);

/**
 * 찾기(locate)로 알게 된 프로젝트(`located`)가 현재 프로젝트와 다르면 현재 프로젝트를 그쪽으로 바꾼다
 * (주소 `?prj=`는 프로젝트 기능이 history replace로 맞춘다). 같은 프로젝트로는 한 번만 바꾸므로
 * 사용자가 나중에 직접 다른 프로젝트를 고르면 되돌리지 않는다.
 */
export function useAdoptLocatedProject(located: string | null | undefined): void {
  const current = useProjectId();
  const adopt = useContext(AdoptProjectContext);
  const done = useRef<string | null>(null);
  useEffect(() => {
    if (adopt === undefined || located === undefined || located === null || located === current || done.current === located) return;
    done.current = located;
    adopt(located);
  }, [adopt, located, current]);
}
