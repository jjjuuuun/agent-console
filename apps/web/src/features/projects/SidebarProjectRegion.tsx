import { useEffect, useMemo, useState } from "react";
import { useDelayed } from "../../app/useDelayed";
import { useStorage } from "../../app/StorageContext";
import { useProjects } from "./ProjectsContext";
import { ProjectRegion } from "./ProjectRegion";
import { parseCollapsed, regionProjects } from "./projectRegionLib";

/** 영역 접힘 저장 키(명세 screen-projects §2.2). 값 `"1"` = 접힘. */
export const PROJECT_REGION_COLLAPSED_KEY = "ac.sidebar.projects.collapsed";

export interface SidebarProjectRegionProps {
  /** 사이드바가 접혀(레일) 있는가 */
  rail: boolean;
}

/**
 * 사이드바 프로젝트 영역(컨테이너): 프로젝트 목록·현재 프로젝트·만들기 대화상자(`useProjects`)와 접힘 저장(`ac.sidebar.projects.collapsed`)을
 * 표현 컴포넌트에 잇는다. 프로젝트 기능이 꺼져 있으면 아무것도 그리지 않는다(구분선·여백 포함).
 */
export function SidebarProjectRegion({ rail }: SidebarProjectRegionProps) {
  const p = useProjects();
  const storage = useStorage();
  const [collapsed, setCollapsed] = useState(() => parseCollapsed(storage.get(PROJECT_REGION_COLLAPSED_KEY)));
  const rows = useMemo(() => regionProjects(p.projects), [p.projects]);
  const slow = useDelayed(p.loading);
  // 목록 조회 오류는 ProjectsProvider가 삼킨다(silent). 오류 표시는 조회 상태를 직접 보지 않으므로 지금은 노출하지 않는다.
  const current = p.current;
  useEffect(() => {
    // 다른 탭이 바꾼 값도 따라간다
    const onStorage = (e: StorageEvent) => {
      if (e.key === PROJECT_REGION_COLLAPSED_KEY) setCollapsed(parseCollapsed(storage.get(PROJECT_REGION_COLLAPSED_KEY)));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [storage]);
  if (!p.enabled) return null;
  return (
    <div className="prj-region-wrap" data-rail={rail ? "true" : undefined}>
      <ProjectRegion
        projects={rows.map((x) => ({ id: x.id, name: x.name, folder: x.folder ?? null }))}
        currentId={current}
        rail={rail}
        collapsed={collapsed}
        onCollapsedChange={(next) => {
          setCollapsed(next);
          storage.set(PROJECT_REGION_COLLAPSED_KEY, next ? "1" : "0");
        }}
        onSelect={(id) => p.setCurrent(id)}
        onAdd={() => p.requestCreate()}
        loadingSlow={slow}
        railOpen={p.switcherOpen}
        onRailOpenChange={p.setSwitcherOpen}
      />
    </div>
  );
}
