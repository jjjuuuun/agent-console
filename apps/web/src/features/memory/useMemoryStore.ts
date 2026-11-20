/**
 * 메모리를 보는 저장소(screen-memory §1.3): 현재 프로젝트 폴더의 저장소(`?project=<id>`) 또는 공용(`?project=` 없음).
 * 이 상태와 "어느 저장소를 읽는가"의 판단은 이 파일 하나가 한다(메모리 화면·설정 › 정리 대상 선택이 같은 훅을 쓴다).
 * 공용을 고른다는 사실은 화면에 따라 주소 인자(`store=library`)이거나 화면 상태이고, 이 훅은 그 값을 인자로 받는다.
 */
import { useContext, useMemo } from "react";
import { UNSAFE_LocationContext } from "react-router";
import { useProjects } from "../projects";
import { MEMORY_PARAMS, MEMORY_STORE_LIBRARY } from "./memoryConfig";

export interface MemoryStoreState {
  /** 프로젝트 기능이 켜져 있는가(꺼져 있으면 칩·선택 없이 공용만) */
  projectsOn: boolean;
  /** 프로젝트가 하나도 없다(기능이 켜져 있고 목록을 받은 뒤) */
  noProjects: boolean;
  /** 현재 프로젝트 id(저장소로 고를 수 있는 프로젝트). 없으면 null */
  currentProject: string | null;
  currentName: string | null;
  /** 프로젝트와 공용 중 고를 수 있는가(프로젝트 기능 켜짐 + 현재 프로젝트 있음) */
  canChoose: boolean;
  /** 지금 읽는 저장소의 프로젝트 id. null = 공용 */
  project: string | null;
  /** 지금 읽는 저장소가 공용인가 */
  library: boolean;
}

/** 순수 계산: 프로젝트 목록 상태와 "공용을 원함" 값으로 읽을 저장소를 정한다. */
export function resolveMemoryStore(input: { projectsOn: boolean; loaded: boolean; current: string | null; currentName: string | null; wantLibrary: boolean }): MemoryStoreState {
  const { projectsOn, loaded, current, currentName, wantLibrary } = input;
  const currentProject = projectsOn ? current : null;
  const canChoose = currentProject !== null;
  const project = canChoose && !wantLibrary ? currentProject : null;
  return {
    projectsOn,
    noProjects: projectsOn && loaded && currentProject === null,
    currentProject,
    currentName: currentProject === null ? null : currentName,
    canChoose,
    project,
    library: project === null,
  };
}

/** 공용을 원하는지 값으로 받아 저장소를 계산한다(설정 › 정리 대상 선택처럼 주소가 아닌 상태용). */
export function useMemoryStoreState(wantLibrary: boolean): MemoryStoreState {
  const projects = useProjects();
  const current = projects.enabled ? projects.current : null;
  const currentName = current === null ? null : (projects.names.get(current) ?? current);
  return useMemo(
    () => resolveMemoryStore({ projectsOn: projects.enabled, loaded: projects.loaded, current, currentName, wantLibrary }),
    [projects.enabled, projects.loaded, current, currentName, wantLibrary],
  );
}

/** 메모리 화면의 저장소: 주소의 `store=library`를 읽는다(전역 `?prj=`는 건드리지 않는다). */
export function useMemoryStore(): MemoryStoreState {
  // 라우터 밖(위젯 단독 테스트 등)에서도 읽을 수 있게 위치 문맥을 직접 읽는다. 라우터가 없으면 주소 인자가 없는 것으로 본다.
  const search = useContext(UNSAFE_LocationContext)?.location.search ?? "";
  const library = new URLSearchParams(search).get(MEMORY_PARAMS.store) === MEMORY_STORE_LIBRARY;
  return useMemoryStoreState(library);
}
