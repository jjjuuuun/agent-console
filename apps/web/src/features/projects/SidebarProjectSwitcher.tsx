import { useNavigate } from "react-router";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { useProjects } from "./ProjectsContext";
import { ROUTE_ROLES, routePath } from "../library";
import { SETTINGS_PROJECTS_HASH } from "./sectionId";

export interface SidebarProjectSwitcherProps {
  collapsed: boolean;
  /** 트리거 툴팁에 덧붙일 단축키 표기(없으면 생략) */
  shortcutHint?: string | undefined;
}

/**
 * 사이드바 `header` 슬롯에 끼우는 프로젝트 전환기(컨테이너). 프로젝트 기능이 꺼져 있으면 아무것도 그리지 않는다.
 * [관리…]는 설정 화면의 프로젝트 섹션으로 간다(별도 메뉴를 늘리지 않음).
 */
export function SidebarProjectSwitcher({ collapsed, shortcutHint }: SidebarProjectSwitcherProps) {
  const p = useProjects();
  const navigate = useNavigate();
  if (!p.enabled) return null;
  return (
    <ProjectSwitcher
      projects={p.projects}
      current={p.current}
      onSelect={p.setCurrent}
      onCreate={() => p.requestCreate()}
      onManage={() => void navigate(`${routePath(ROUTE_ROLES.settings)}${SETTINGS_PROJECTS_HASH}`)}
      collapsed={collapsed}
      shortcutHint={shortcutHint}
      open={p.switcherOpen}
      onOpenChange={p.setSwitcherOpen}
    />
  );
}
