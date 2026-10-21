import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { useToast } from "@agent-console/ui";
import { useQueryClient } from "@tanstack/react-query";
import type { Project, ProjectCreate } from "@agent-console/contracts/projects";
import {
  DEFAULT_SCOPE_VIEW_MODE,
  SCOPE_VIEW_MODES,
  createCurrentProjectStore,
  filterByScope,
  readProjectParam,
  writeProjectParam,
  type CurrentProject,
  type CurrentProjectStore,
  type ProjectsClient,
  type Scope,
  type ScopeViewMode,
} from "@agent-console/projects";
import { useApi } from "../../app/ApiContext";
import { CURRENT_PROJECT_PARAM, CurrentProjectContext } from "../../app/projectScope";
import { describeError } from "../../app/errors";
import { PROJECT_REQUIRES } from "../../app/requirements";
import { useApiQuery } from "../../app/queries";
import { useStorage } from "../../app/StorageContext";
import type { SafeStorage } from "../../app/storage";
import { ApiError } from "@agent-console/api-client";
import { useModules, useRequires } from "../../modules";
import { ROUTE_ROLES, routePath } from "../library";
import { SETTINGS_PROJECTS_HASH } from "./sectionId";
import { ProjectCreateDialog } from "./ProjectCreateDialog";
import { projectMessages as t } from "./messages";

/** 목록 질의 키(`["list", …]` 아래라 쓰기 뒤 다른 목록과 함께 갱신된다). */
export const PROJECTS_QUERY_KEY = ["list", "projects"] as const;
/** 목록 보기 범위(공용 + 이 프로젝트 / 이 프로젝트만 / 공용만)를 브라우저에 기억하는 키. 현재 프로젝트 키(`ac.project`)는 패키지 기본값이다. */
export const SCOPE_VIEW_STORAGE_KEY = "ac.projectView";

export interface ProjectsValue {
  /** 프로젝트 기능이 켜져 있는가. false면 아래 값은 모두 비어 있고 프로젝트 UI는 그려지지 않는다 */
  enabled: boolean;
  loading: boolean;
  projects: readonly Project[];
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
  /** 새 프로젝트 만들기 대화상자를 연다. 만들면 그 프로젝트로 전환하고 `onCreated`를 부른다 */
  requestCreate(onCreated?: (project: Project) => void): void;
  /** 항목 목록을 현재 보기 범위로 거른다(꺼져 있거나 모든 프로젝트 보기면 그대로) */
  filter<T>(items: readonly T[], scopeOf: (item: T) => Scope): T[];
}

const OFF: ProjectsValue = {
  enabled: false,
  loading: false,
  projects: [],
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
  const { projects: client } = useApi();
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

  const list = useApiQuery<Project[]>(PROJECTS_QUERY_KEY, () => client.listProjects(), { enabled: requiredMet, retry: false, meta: { silentBackgroundError: true } });
  // 목록 REST가 404면 서버에 프로젝트 기능이 없다(모듈 목록이 낡았을 때): 꺼진 것으로 본다.
  const enabled = requiredMet && !(list.error instanceof ApiError && list.error.status === 404);
  const projects = useMemo<readonly Project[]>(() => (enabled ? (list.data ?? []) : []), [enabled, list.data]);
  const listed = enabled && list.isSuccess;

  // 목록을 받은 뒤 없는 프로젝트를 가리키면 모든 프로젝트로 돌린다(삭제된 프로젝트의 저장값·주소)
  useEffect(() => {
    if (listed) store.reconcile(projects.map((p) => p.id));
  }, [listed, projects, store]);

  // 주소 질의와 맞춘다: 주소가 바뀌어 값이 다르면 따르고, 값이 있는데 주소에 없으면 붙인다.
  const effective = enabled ? current : null;
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

  // 새 프로젝트 만들기: 어디서든 `requestCreate()`로 같은 대화상자를 연다
  const toast = useToast();
  const [creating, setCreating] = useState<{ onCreated?: (project: Project) => void } | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const requestCreate = useCallback((onCreated?: (project: Project) => void) => {
    setCreateError(null);
    setCreating(onCreated === undefined ? {} : { onCreated });
  }, []);
  const create = (body: ProjectCreate) => {
    setCreateBusy(true);
    setCreateError(null);
    client
      .createProject(body)
      .then(async ({ value }) => {
        await refresh();
        store.set(value.id);
        const first = projects.length === 0;
        toast({
          tone: "success",
          text: t.create.created(value.name),
          ...(first ? { action: { label: t.create.guideAction, onClick: () => void navigate(`${routePath(ROUTE_ROLES.settings)}${SETTINGS_PROJECTS_HASH}`) } } : {}),
        });
        const done = creating?.onCreated;
        setCreating(null);
        done?.(value);
      })
      .catch((e: unknown) => setCreateError(describeError(e, t.create.failed).message))
      .finally(() => setCreateBusy(false));
  };
  const knownIds = useMemo(() => projects.map((p) => p.id), [projects]);

  const value = useMemo<ProjectsValue>(
    () => ({
      enabled,
      loading: phase === "loading" || (enabled && list.isLoading),
      projects,
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
    [enabled, phase, list.isLoading, projects, names, effective, setCurrent, viewMode, setViewMode, client, refresh, switcherOpen, requestCreate, listed, knownIds],
  );
  return (
    <ProjectsContext.Provider value={value}>
      <CurrentProjectContext.Provider value={effective}>{children}</CurrentProjectContext.Provider>
      {creating === null ? null : (
        <ProjectCreateDialog open existingIds={new Set(projects.map((p) => p.id))} busy={createBusy} error={createError} onSubmit={create} onClose={() => setCreating(null)} />
      )}
    </ProjectsContext.Provider>
  );
}

