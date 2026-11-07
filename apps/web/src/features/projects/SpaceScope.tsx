import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { createProjectsText } from "@agent-console/projects";
import type { ProjectView } from "@agent-console/contracts/projects";
import { Button, Icon, MiddleEllipsis, Popover } from "@agent-console/ui";
import { ApiProvider, useApi } from "../../app/ApiContext";
import { HintBanner } from "../../app/hints";
import { createAppQueryClient } from "../../app/queries";
import { CURRENT_PROJECT_PARAM } from "../../app/projectScope";
import { useProjects } from "./ProjectsContext";

const text = createProjectsText();

/** 구성 화면이 보고 있는 공간. null = 공용(라이브러리), 값 = 그 프로젝트의 사본 저장소. */
const SpaceContext = createContext<ProjectView | null>(null);

/** 지금 구성 화면이 보는 프로젝트 사본(`?prj=`). 공용이면 null. */
export function useSpace(): ProjectView | null {
  return useContext(SpaceContext);
}

/** 프로젝트 사본 안에서만 쓰는 하위 층: 정의 REST를 그 프로젝트 공간으로 돌리고, 캐시를 공용과 따로 둔다. */
function ProjectSpace({ view, children }: { view: ProjectView; children: ReactNode }) {
  const base = useApi();
  const id = view.project.id;
  const clients = useMemo(() => ({ ...base, rest: { ...base.rest, ...base.space(id) } }), [base, id]);
  // 공간마다 질의 캐시를 따로 둔다(같은 질의 키가 공용과 프로젝트 사이에서 섞이지 않게)
  const [queryClient] = useState(() => createAppQueryClient({ retry: false }));
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider clients={clients}>
        <SpaceContext.Provider value={view}>{children}</SpaceContext.Provider>
      </ApiProvider>
    </QueryClientProvider>
  );
}

/**
 * 구성 화면(팀·에이전트·리소스) 바깥에 두는 공간 선택(screen-projects §5.3): 주소의 `?prj=<프로젝트 id>`가 그 프로젝트의 사본을 가리키면
 * 아래 화면의 모든 정의 요청이 그 프로젝트 공간(`?project=`)으로 가고, 없으면 공용이다. 화면은 공간을 모른 채 같은 코드로 동작한다.
 * 프로젝트 기능이 꺼져 있거나 목록에 없는 id면 공용으로 본다. 프로젝트 목록을 받기 전에는 아무것도 그리지 않는다.
 */
export function SpaceScope({ children }: { children: ReactNode }) {
  const p = useProjects();
  const [params] = useSearchParams();
  const wanted = params.get(CURRENT_PROJECT_PARAM);
  if (!p.enabled || wanted === null) return <SpaceContext.Provider value={null}>{children}</SpaceContext.Provider>;
  if (!p.loaded) return null;
  const view = p.views.find((v) => v.project.id === wanted && v.project.archived !== true);
  if (view === undefined) return <SpaceContext.Provider value={null}>{children}</SpaceContext.Provider>;
  return (
    <ProjectSpace key={view.project.id} view={view}>
      {children}
    </ProjectSpace>
  );
}

/**
 * 머리의 공간 칩: 공용 화면은 "공용", 프로젝트 사본은 "프로젝트: {이름}"(+ 경로). 클릭하면 설명 팝오버.
 * 프로젝트 기능이 꺼져 있거나 프로젝트가 없으면 아무것도 그리지 않는다.
 */
export function SpaceChip() {
  const p = useProjects();
  const space = useSpace();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  if (!p.enabled || (space === null && p.views.every((v) => v.project.archived === true))) return null;
  const name = space?.project.name ?? "";
  const dir = space?.project.folder ?? "";
  const label = space === null ? text("space.library") : text({ key: "space.project", params: { name } });
  const current = p.currentView;
  // 같은 화면의 공용 주소: 프로젝트 질의만 뺀다
  const libraryParams = new URLSearchParams(location.search);
  libraryParams.delete(CURRENT_PROJECT_PARAM);
  const libraryTo = `${location.pathname}${libraryParams.size === 0 ? "" : `?${libraryParams.toString()}`}`;
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelRole="dialog"
      panelLabel={label}
      renderTrigger={(tp) => (
        <button {...tp} type="button" className="space-chip" data-space={space === null ? "library" : "project"} aria-label={space === null ? label : `${label} ${dir}`}>
          <Icon name={space === null ? "library" : "folder"} size={14} />
          {space === null ? <span>{label}</span> : (
            <>
              <span className="ac-ellipsis space-chip-name">{text({ key: "space.project", params: { name } })}</span>
              <MiddleEllipsis value={dir} head={10} tail={16} className="space-chip-dir" />
            </>
          )}
        </button>
      )}
    >
      <div className="space-pop">
        <p className="space-pop-note">{space === null ? text("space.library_tip") : text("space.project_note")}</p>
        {space === null ? (
          current === undefined ? null : <Link to={`/projects/${encodeURIComponent(current.project.id)}`} onClick={() => setOpen(false)}>{text("space.view_in_project")}</Link>
        ) : (
          <>
            <p className="space-pop-path ac-mono-wrap">{dir}</p>
            <div className="space-pop-actions">
              <Button size="sm" variant="secondary" onClick={() => { setOpen(false); p.openHome(space.project.id); }}>{text("space.open_home")}</Button>
              <Link className="ac-btn" data-variant="secondary" data-size="sm" to={libraryTo} onClick={() => setOpen(false)}>
                {text("space.view_library")}
              </Link>
            </div>
          </>
        )}
      </div>
    </Popover>
  );
}

/** 프로젝트 사본 화면의 맨 위 한 줄 안내(닫을 수 있음)와 뒤로 가기. 공용 화면이면 아무것도 그리지 않는다. */
export function SpaceNote() {
  const space = useSpace();
  const p = useProjects();
  if (space === null) return null;
  return (
    <div className="space-note">
      <button type="button" className="app-link-btn" onClick={() => p.openHome(space.project.id)}>{text({ key: "space.back_home", params: { name: space.project.name } })}</button>
      <HintBanner id="space.project">{text("space.project_note")}</HintBanner>
    </div>
  );
}
