import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { Banner, Button, Tag } from "@agent-console/ui";
import { logFilterFor, readProjectParam } from "@agent-console/projects";
import { CURRENT_PROJECT_PARAM } from "../../app/projectScope";
import { useStorage } from "../../app/StorageContext";
import { ROUTE_ROLES, routePath } from "../library";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";
import { SETTINGS_PROJECTS_HASH } from "./sectionId";

/** 사용자가 필터를 초기화한 프로젝트 id(그 프로젝트가 현재인 동안 자동 적용을 멈춘다). */
export const LOG_RESET_KEY = "ac.projectLogReset";

/**
 * 사용량 화면 머리의 "계정 전체" 표시. 구독 사용량은 프로젝트와 무관한 계정 기준이라, 프로젝트를 고른 상태에서만 알려 준다.
 * 프로젝트 기능이 꺼져 있거나 모든 프로젝트 보기면 아무것도 그리지 않는다.
 */
export function AccountWideNote() {
  const p = useProjects();
  if (!p.enabled || p.current === null) return null;
  return <Tag className="prj-tag" data-tone="neutral" title={t.usage.accountWideTitle}>{t.usage.accountWide}</Tag>;
}

/**
 * 로그 화면 위 줄(`filterParam` = 로그 화면의 프로젝트 묶음 필터 이름, 로그 화면이 정한다): 현재 프로젝트의 로그 묶음으로 거르는 중이면 알리고 [필터 초기화]를 준다.
 * 프로젝트에 연결된 로그가 없으면 [로그 연결](설정 > 프로젝트)을 준다. 프로젝트를 고르고 처음 들어오면(주소에 로그 필터 `filterParam`이 없을 때) 필터를 한 번 채운다.
 */
export function LogProjectNote({ filterParam }: { filterParam: string }) {
  const p = useProjects();
  const storage = useStorage();
  const location = useLocation();
  const navigate = useNavigate();
  const info = logFilterFor(p.currentProject === undefined ? null : { log_projects: p.currentProject.log_projects ?? [] });
  const params = new URLSearchParams(location.search);
  const urlProject = params.get(filterParam);
  const active = p.enabled && p.current !== null;
  const wanted = info.filter?.project;
  const currentId = p.current;

  // 프로젝트를 바꾸면 이전 프로젝트가 채운 필터를 새 프로젝트 것으로 바꾼다(사용자가 직접 고친 값은 건드리지 않는다).
  // 주소의 현재 프로젝트 쿼리가 새 값으로 정리된 뒤에 쓴다(정리 중인 주소를 덮어쓰지 않게).
  const seen = useRef({ id: currentId, wanted });
  const stale = useRef<string | null>(null);
  const urlCurrent = readProjectParam(location.search, CURRENT_PROJECT_PARAM) ?? null;
  useEffect(() => {
    if (seen.current.id !== currentId) {
      stale.current = seen.current.wanted ?? null;
      seen.current = { id: currentId, wanted };
    } else {
      // 같은 프로젝트 안에서 목록이 늦게 로드돼 wanted가 정해지면 기준을 갱신한다(첫 렌더 값에 고정하면 교체를 놓친다).
      seen.current.wanted = wanted;
    }
    const old = stale.current;
    if (old === null || urlCurrent !== currentId) return;
    stale.current = null;
    if (urlProject !== old || old === wanted) return;
    const next = new URLSearchParams(location.search);
    if (wanted === undefined) next.delete(filterParam);
    else next.set(filterParam, wanted);
    const q = next.toString();
    void navigate({ pathname: location.pathname, search: q === "" ? "" : `?${q}`, hash: location.hash }, { replace: true });
  }, [currentId, wanted, urlProject, urlCurrent, filterParam, location.pathname, location.search, location.hash, navigate]);

  useEffect(() => {
    if (!active || wanted === undefined || urlProject !== null || storage.get(LOG_RESET_KEY) === currentId) return;
    const next = new URLSearchParams(location.search);
    next.set(filterParam, wanted);
    void navigate({ pathname: location.pathname, search: `?${next.toString()}`, hash: location.hash }, { replace: true });
  }, [active, wanted, urlProject, filterParam, storage, currentId, location.pathname, location.search, location.hash, navigate]);

  if (!active || p.currentProject === undefined) return null;
  const name = p.currentProject.name;
  if (!info.linked) {
    return (
      <Banner tone="info" actions={<Button size="sm" onClick={() => void navigate(`${routePath(ROUTE_ROLES.settings)}${SETTINGS_PROJECTS_HASH}`)}>{t.logs.connect}</Button>}>
        {t.logs.notConnected(name)}
      </Banner>
    );
  }
  if (urlProject === null || urlProject !== wanted) return null;
  return (
    <Banner
      tone="info"
      actions={
        <Button
          size="sm"
          onClick={() => {
            if (p.current !== null) storage.set(LOG_RESET_KEY, p.current);
            const next = new URLSearchParams(location.search);
            next.delete(filterParam);
            const s = next.toString();
            void navigate({ pathname: location.pathname, search: s === "" ? "" : `?${s}`, hash: location.hash }, { replace: true });
          }}
        >
          {t.logs.resetFilter}
        </Button>
      }
    >
      {t.logs.filterFromProject(name)}
    </Banner>
  );
}
