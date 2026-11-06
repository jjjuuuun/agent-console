import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router";
import type { MenuItemDef } from "@agent-console/ui";
import { createProjectsText, statusInfo, type StatusTone } from "@agent-console/projects";
import { useDelayed } from "../../app/useDelayed";
import { useStorage } from "../../app/StorageContext";
import { useToast } from "@agent-console/ui";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { useProjects } from "./ProjectsContext";
import { ProjectRegion } from "./ProjectRegion";
import { parseCollapsed, regionViews } from "./projectRegionLib";
import type { RegionProject } from "./ProjectRegion";

const text = createProjectsText();

/** 프로젝트 홈(`/projects/:id`) 주소에서 id를 읽는다. 아니면 null. */
function homeProjectId(pathname: string): string | null {
  if (!pathname.startsWith("/projects/")) return null;
  const raw = pathname.slice("/projects/".length).split("/")[0] ?? "";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
const FOLDER_ICONS: Readonly<Record<string, string>> = {
  folder_missing: "folder-off",
  not_a_directory: "folder-off",
  no_access: "folder-lock",
  folder_unset: "folder-help",
  folder_conflict: "folder-alert",
  manifest_invalid: "folder-alert",
};
const TONE_OF: Readonly<Record<StatusTone, "ok" | "neutral" | "warning" | "danger">> = { ok: "ok", neutral: "neutral", warning: "warning", danger: "danger" };

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
  const toast = useToast();
  const location = useLocation();
  const rows = useMemo<RegionProject[]>(
    () =>
      regionViews(p.views).map((v) => {
        const info = statusInfo(v);
        return {
          id: v.project.id,
          name: v.project.name,
          folder: v.project.folder ?? null,
          status: { icon: FOLDER_ICONS[v.status] ?? (v.status === "ready" ? "folder" : "folder-alert"), tone: TONE_OF[info.tone], label: text(info.label), plain: info.plain },
        };
      }),
    [p.views],
  );
  const copy = (value: string, done: string) => {
    const fail = () => toast({ tone: "warning", text: m.menu.copyFailed });
    if (navigator.clipboard === undefined) return fail();
    navigator.clipboard.writeText(value).then(() => toast({ tone: "success", text: done, durationMs: 2000 }), fail);
  };
  const menuItems = (row: RegionProject): MenuItemDef[] => [
    { id: "open", label: m.menu.openHome, onSelect: () => p.openHome(row.id) },
    ...(row.folder === null || row.folder === ""
      ? []
      : [
          { id: "copy-path", label: m.menu.copyPath, onSelect: () => copy(row.folder ?? "", m.menu.pathCopied) },
          { id: "copy-cd", label: m.menu.copyCd, title: m.menu.copyCdHelp, onSelect: () => copy(`cd "${row.folder ?? ""}"`, m.menu.cdCopied) },
        ]),
    { id: "repath", label: m.menu.repath, onSelect: () => p.requestRepath(row.id) },
    { id: "unregister", label: m.menu.unregister, danger: true, onSelect: () => p.requestUnregister(row.id) },
  ];
  const homeOpenId = homeProjectId(location.pathname);
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
        projects={rows}
        menuItems={menuItems}
        homeOpenId={homeOpenId}
        currentId={current}
        rail={rail}
        collapsed={collapsed}
        onCollapsedChange={(next) => {
          setCollapsed(next);
          storage.set(PROJECT_REGION_COLLAPSED_KEY, next ? "1" : "0");
        }}
        onSelect={(id) => p.openHome(id)}
        onAdd={() => p.requestAddFolder()}
        loadingSlow={slow}
        railOpen={p.switcherOpen}
        onRailOpenChange={p.setSwitcherOpen}
      />
    </div>
  );
}
