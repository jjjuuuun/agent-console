import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { Project, ProjectView } from "@agent-console/contracts/projects";
import {
  DEFAULT_SCOPE_VIEW_MODE,
  SCOPE_VIEW_MODES,
  createCurrentProjectStore,
  filterByScope,
  readProjectParam,
  writeProjectParam,
  createProjectsText,
  type CurrentProject,
  type CurrentProjectStore,
  type ProjectsClient,
  type Scope,
  type ScopeViewMode,
} from "@agent-console/projects";
import { useApi } from "../../app/ApiContext";
import { CURRENT_PROJECT_PARAM, CurrentProjectContext } from "../../app/projectScope";
import { PROJECT_REQUIRES } from "../../app/requirements";
import { useApiQuery } from "../../app/queries";
import type { RestClient } from "@agent-console/api-client";
import { useStorage } from "../../app/StorageContext";
import type { SafeStorage } from "../../app/storage";
import { ApiError } from "@agent-console/api-client";
import { useModules, useRequires } from "../../modules";
import { useToast } from "@agent-console/ui";
import { folderHomeMessages } from "./folderHomeMessages";
import { UnregisterDialog } from "./UnregisterDialog";
import { regionProjects } from "./projectRegionLib";
import { ProjectFolderHost, type FolderRequest } from "./ProjectFolderHost";

/** 프로젝트 홈 주소(라우트 `/projects/:id`). 현재 프로젝트 질의는 주소에 `?prj=`로 이어 붙는다. */
export function projectHomePath(id: string): string {
  return `/projects/${encodeURIComponent(id)}`;
}

const dirFallback = createProjectsText()("projects.dir_fallback");
const loadProjects = (rest: RestClient): Promise<ProjectView[]> => rest.listProjects();

/** 목록 질의 키(`["list", …]` 아래라 쓰기 뒤 다른 목록과 함께 갱신된다). */
export const PROJECTS_QUERY_KEY = ["list", "projects"] as const;
/** 목록 보기 범위(공용 + 이 프로젝트 / 이 프로젝트만 / 공용만)를 브라우저에 기억하는 키. 현재 프로젝트 키(`ac.project`)는 패키지 기본값이다. */
export const SCOPE_VIEW_STORAGE_KEY = "ac.projectView";

export interface ProjectsValue {
  /** 프로젝트 기능이 켜져 있는가. false면 아래 값은 모두 비어 있고 프로젝트 UI는 그려지지 않는다 */
  enabled: boolean;
  loading: boolean;
  /** 등록한 프로젝트(보관 포함)의 `Project` 부분. 상태·구성 폴더 등은 `views`에 있다 */
  projects: readonly Project[];
  /** 서버가 계산한 프로젝트 보기(상태·쓰기 가능·기록 상태 포함, 보관 포함) */
  views: readonly ProjectView[];
  currentView: ProjectView | undefined;
  /** 목록 조회가 실패했는가(0개로 단정하지 않는다) */
  loadFailed: boolean;
  /** 지금까지 한 번이라도 목록을 받았는가 */
  loaded: boolean;
  /** 프로젝트 홈으로 간다: 현재 프로젝트를 바꾸고 `/projects/:id`로 이동 */
  openHome(id: string): void;
  /** 폴더 추가 대화상자를 연다(사이드바·시작하기·NoProjectState가 모두 이것을 부른다) */
  requestAddFolder(onAdded?: (view: ProjectView) => void): void;
  /** 등록 해제 확인 대화상자를 연다(해제 = 서버에서 보관) */
  requestUnregister(id: string): void;
  /** 경로 다시 지정 대화상자를 연다 */
  requestRepath(id: string): void;
  /** id -> 표시 이름 */
  names: ReadonlyMap<string, string>;
  /** 현재 프로젝트 id. null = 모든 프로젝트(기능이 꺼져 있어도 null) */
  current: CurrentProject;
  currentProject: Project | undefined;
  setCurrent(id: CurrentProject): void;
  /** 프로젝트를 고른 목록 보기에서 무엇을 보일지(모든 목록이 공유하는 하나의 값) */
  viewMode: ScopeViewMode;
  setViewMode(mode: ScopeViewMode): void;
  client: ProjectsClient | undefined;
  /** 프로젝트 목록을 다시 읽는다 */
  refresh(): Promise<void>;
  /** 사이드바 전환기가 열려 있는가(단축키·팔레트가 연다) */
  switcherOpen: boolean;
  setSwitcherOpen(open: boolean): void;
  /** `requestAddFolder`와 같다(옛 이름). 추가하면 그 프로젝트로 전환하고 `onCreated`를 부른다 */
  requestCreate(onCreated?: (project: Project) => void): void;
  /** 항목 목록을 현재 보기 범위로 거른다(꺼져 있거나 모든 프로젝트 보기면 그대로) */
  filter<T>(items: readonly T[], scopeOf: (item: T) => Scope): T[];
}

const OFF: ProjectsValue = {
  enabled: false,
  loading: false,
  projects: [],
  views: [],
  currentView: undefined,
  loadFailed: false,
  loaded: false,
  openHome: () => {},
  requestAddFolder: () => {},
  requestRepath: () => {},
  requestUnregister: () => {},
  names: new Map(),
  current: null,
  currentProject: undefined,
  setCurrent: () => {},
  viewMode: DEFAULT_SCOPE_VIEW_MODE,
  setViewMode: () => {},
  client: undefined,
  refresh: async () => {},
  switcherOpen: false,
  setSwitcherOpen: () => {},
  requestCreate: () => {},
  filter: (items) => [...items],
};

const ProjectsContext = createContext<ProjectsValue>(OFF);

/** 프로젝트 상태 읽기. `ProjectsProvider` 밖이면 "꺼짐" 값(프로젝트 UI 없음)이다. */
export function useProjects(): ProjectsValue {
  return useContext(ProjectsContext);
}

function asProjectStorage(storage: SafeStorage) {
  return { getItem: (k: string) => storage.get(k), setItem: (k: string, v: string) => storage.set(k, v), removeItem: (k: string) => storage.remove(k) };
}

function readViewMode(storage: SafeStorage): ScopeViewMode {
  const raw = storage.get(SCOPE_VIEW_STORAGE_KEY);
  return SCOPE_VIEW_MODES.find((m) => m === raw) ?? DEFAULT_SCOPE_VIEW_MODE;
}

/**
 * 프로젝트 상태 공급자(앱 셸 안, 라우터 안). 서버에 프로젝트 역할이 켜져 있을 때만 목록을 읽는다.
 * 현재 프로젝트는 주소 `?prj=`가 우선이고 없으면 브라우저 저장값이다(서버 상태가 아님).
 * 화면 이동 때 주소 질의가 사라지면 다시 붙여 공유 가능한 주소를 유지한다.
 */
export function ProjectsProvider({ children }: { children: ReactNode }) {
  const phase = useRequires(PROJECT_REQUIRES).phase;
  // 모듈 목록을 못 받은 서버(구버전 등)에서는 켜져 있는지 알 수 없으므로 프로젝트 UI를 만들지 않는다(다른 기능의 fail-open과 달리 이 UI는 덧붙는 것이다).
  const listKnown = useModules().state.phase === "ready";
  const requiredMet = phase === "met" && listKnown;
  const { projects: client, rest } = useApi();
  const storage = useStorage();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // 저장소·주소는 한 번 읽어 시작 값을 정한다. 주소는 라우터 위치를 쓰므로 store에는 저장소만 준다.
  const [store] = useState<CurrentProjectStore>(() => {
    const created = createCurrentProjectStore({ storage: asProjectStorage(storage) });
    const fromUrl = readProjectParam(location.search, CURRENT_PROJECT_PARAM);
    if (fromUrl !== undefined) created.set(fromUrl);
    return created;
  });
  const current = useSyncExternalStore(store.subscribe, store.get, store.get);
  const [viewMode, setViewModeState] = useState<ScopeViewMode>(() => readViewMode(storage));

  const list = useApiQuery<ProjectView[]>(PROJECTS_QUERY_KEY, loadProjects, { enabled: requiredMet, retry: false, meta: { silentBackgroundError: true } });
  // 목록 REST가 404면 서버에 프로젝트 기능이 없다(모듈 목록이 낡았을 때): 꺼진 것으로 본다.
  const enabled = requiredMet && !(list.error instanceof ApiError && list.error.status === 404);
  const views = useMemo<readonly ProjectView[]>(() => (enabled ? (list.data ?? []) : []), [enabled, list.data]);
  const projects = useMemo<readonly Project[]>(() => views.map((v) => v.project), [views]);
  const listed = enabled && list.isSuccess;

  // 목록을 받은 뒤 없는 프로젝트를 가리키면 모든 프로젝트로 돌린다(삭제된 프로젝트의 저장값·주소)
  useEffect(() => {
    if (listed) store.reconcile(projects.map((p) => p.id));
  }, [listed, projects, store]);

  // 주소 질의와 맞춘다: 주소가 바뀌어 값이 다르면 따르고, 값이 있는데 주소에 없으면 붙인다.
  // 프로젝트가 1개 이상이면 현재 프로젝트가 늘 있다("모든 프로젝트" 없음, screen-projects §7.4): 값이 없거나 보관·삭제된 것이면 이름순 첫 프로젝트.
  // 저장소·주소를 바꾸지 않고 파생한다(주소를 덮어쓰는 이동과 경쟁하지 않는다).
  const active = useMemo(() => regionProjects(projects), [projects]);
  const fallbackId = listed ? (active[0]?.id ?? null) : null;
  const effective = !enabled ? null : current !== null && (!listed || active.some((p) => p.id === current)) ? current : listed ? fallbackId : current;
  const lastSearch = useRef(location.search);
  useEffect(() => {
    if (!enabled) return;
    const fromUrl = readProjectParam(location.search, CURRENT_PROJECT_PARAM);
    const urlChanged = lastSearch.current !== location.search;
    lastSearch.current = location.search;
    if (urlChanged && fromUrl !== undefined && fromUrl !== store.get()) {
      store.set(fromUrl);
      return;
    }
    if ((fromUrl ?? null) !== store.get()) {
      void navigate({ pathname: location.pathname, search: writeProjectParam(location.search, store.get(), CURRENT_PROJECT_PARAM), hash: location.hash }, { replace: true });
    }
  }, [enabled, location.pathname, location.search, location.hash, current, navigate, store]);

  const setCurrent = useCallback((id: CurrentProject) => store.set(id), [store]);
  const setViewMode = useCallback(
    (mode: ScopeViewMode) => {
      setViewModeState(mode);
      storage.set(SCOPE_VIEW_STORAGE_KEY, mode);
    },
    [storage],
  );
  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY }), [queryClient]);
  const names = useMemo(() => new Map(projects.map((p) => [p.id, p.name])), [projects]);

  const [switcherOpen, setSwitcherOpen] = useState(false);

  // 폴더 추가·경로 다시 지정: 어디서든 같은 대화상자를 연다(요청이 있을 때만 마운트되어 열 때마다 새로 시작한다)
  const [folderRequest, setFolderRequest] = useState<FolderRequest | null>(null);
  const requestAddFolder = useCallback((onAdded?: (view: ProjectView) => void) => setFolderRequest({ mode: "add", onAdded }), []);
  const requestCreate = useCallback((onCreated?: (project: Project) => void) => setFolderRequest({ mode: "add", onAdded: onCreated === undefined ? undefined : (v) => onCreated(v.project) }), []);
  const requestRepath = useCallback(
    (id: string) => {
      const view = views.find((v) => v.project.id === id);
      if (view !== undefined) setFolderRequest({ mode: "repath", view });
    },
    [views],
  );
  const [unregistering, setUnregistering] = useState<string | null>(null);
  const requestUnregister = useCallback((id: string) => setUnregistering(id), []);
  const openHome = useCallback(
    (id: string) => {
      // 현재 프로젝트는 주소 `?prj=`가 따라 정한다(주소 → 저장소 동기화 효과). 저장소를 먼저 바꾸면 효과가 옛 주소를 덮어쓰는 경쟁이 생긴다.
      void navigate({ pathname: projectHomePath(id), search: writeProjectParam("", id, CURRENT_PROJECT_PARAM) });
    },
    [navigate],
  );
  const unregisterView = unregistering === null ? undefined : views.find((v) => v.project.id === unregistering);
  const toast = useToast();
  const unregister = async () => {
    if (unregisterView === undefined) return;
    const { id, name } = unregisterView.project;
    await rest.unregisterProject(id, unregisterView.version_hash ?? undefined);
    await refresh();
    toast({
      tone: "success",
      text: folderHomeMessages.unregister.done(name),
      action: {
        label: folderHomeMessages.unregister.undo,
        onClick: () => void rest.updateProject(id, { archived: false }).then(() => refresh()),
      },
    });
  };
  const knownIds = useMemo(() => projects.map((p) => p.id), [projects]);

  const value = useMemo<ProjectsValue>(
    () => ({
      enabled,
      loading: phase === "loading" || (enabled && list.isLoading),
      projects,
      views,
      currentView: effective === null ? undefined : views.find((v) => v.project.id === effective),
      loadFailed: enabled && list.isError,
      loaded: listed,
      openHome,
      requestAddFolder,
      requestRepath,
      requestUnregister,
      names,
      current: effective,
      currentProject: effective === null ? undefined : projects.find((p) => p.id === effective),
      setCurrent,
      viewMode,
      setViewMode,
      client: enabled ? client : undefined,
      refresh,
      switcherOpen,
      setSwitcherOpen,
      requestCreate,
      filter: (items, scopeOf) => (!enabled || effective === null ? [...items] : filterByScope(items, effective, { mode: viewMode, knownProjects: listed ? knownIds : undefined, scopeOf })),
    }),
    [enabled, phase, list.isLoading, list.isError, projects, views, names, effective, setCurrent, viewMode, setViewMode, client, refresh, switcherOpen, requestCreate, requestAddFolder, requestRepath, requestUnregister, openHome, listed, knownIds],
  );
  return (
    <ProjectsContext.Provider value={value}>
      <CurrentProjectContext.Provider value={effective}>{children}</CurrentProjectContext.Provider>
      {folderRequest === null ? null : (
        <ProjectFolderHost request={folderRequest} projects={views} refresh={refresh} openHome={openHome} onClose={() => setFolderRequest(null)} />
      )}
      {unregisterView === undefined ? null : (
        <UnregisterDialog
          name={unregisterView.project.name}
          folder={unregisterView.project.folder}
          configDir={unregisterView.config_dir ?? dirFallback}
          onClose={() => setUnregistering(null)}
          onConfirm={unregister}
        />
      )}
    </ProjectsContext.Provider>
  );
}

