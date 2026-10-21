import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, type RestClient } from "@agent-console/api-client";
import type { ModuleInfo } from "@agent-console/contracts";
import { useToast } from "@agent-console/ui";
import { useApi } from "../app/ApiContext";
import type { FeatureSignal } from "../app/apiClients";
import { messages as m } from "../app/messages";
import { knownNames, resolveRequires, type UnmetItem } from "./resolve";

/** `GET /modules` 질의 키. 서버가 진실이므로 저장소에 쓰지 않는다. */
export const MODULES_QUERY_KEY = ["modules"] as const;

/** 마지막 조회가 이 시간보다 오래됐을 때만 창 포커스 복귀가 다시 읽는다(screen-modules.md 2). */
const FOCUS_STALE_MS = 60_000;
/** 켜져 있다고 믿던 기능의 404가 연달아 와도 모듈 목록은 이 간격보다 자주 다시 읽지 않는다. */
const SIGNAL_MIN_GAP_MS = 5_000;
const RETRY_COUNT = 3;
const retryDelay = (attempt: number) => 1000 * 2 ** attempt;

/**
 * 모듈 목록의 상태.
 * - `loading`: 첫 응답 전. 화면은 안내 화면도 본문도 그리지 않는다.
 * - `ready`: 목록을 받았다.
 * - `unavailable`: 목록을 못 받았다(구버전 서버의 404, 또는 재시도 뒤 네트워크·5xx 실패, 또는 공급자 없음).
 *   웹은 **모든 `requires`를 만족한 것으로** 본다(fail-open). 열어 두고 화면별 오류로 알리는 쪽이 피해가 작다.
 */
export type ModulesState =
  | { phase: "loading" }
  | { phase: "ready"; modules: readonly ModuleInfo[] }
  | { phase: "unavailable"; reason: "no-endpoint" | "failed" | "no-provider" };

export interface ModulesValue {
  state: ModulesState;
  /** 즉시 다시 읽는다([새로고침]). */
  refetch: () => Promise<void>;
  /** 다시 읽는 중인가(목록은 그대로 둔다). */
  refetching: boolean;
}

const FAIL_OPEN: ModulesValue = { state: { phase: "unavailable", reason: "no-provider" }, refetch: async () => {}, refetching: false };
const ModulesContext = createContext<ModulesValue>(FAIL_OPEN);

type Loaded = { kind: "list"; modules: readonly ModuleInfo[] } | { kind: "no-endpoint" };

/** 모듈 목록을 읽는다. 404이거나 배열이 아닌 응답이면 "목록 없음"(오류가 아님)으로 돌려준다. */
export async function loadModules(rest: Pick<RestClient, "listModules">): Promise<Loaded> {
  try {
    const list = await rest.listModules();
    return Array.isArray(list) ? { kind: "list", modules: list } : { kind: "no-endpoint" };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { kind: "no-endpoint" };
    throw error;
  }
}

export interface ModulesProviderProps {
  children: ReactNode;
  /** 기능 신호(404·409)를 받는 구독 함수. 앱 루트가 REST 응답에서 만든다. 생략하면 신호를 보지 않는다. */
  subscribeSignals?: (listener: (signal: FeatureSignal) => void) => () => void;
}

/**
 * `/modules`를 읽어 하위 훅(`useModules`·`useRequires`·`useModule`)에 공급한다.
 * 부팅 때 한 번, WS 재연결 때, 창 포커스 복귀 때(60초 넘게 지났을 때), [새로고침], 기능 REST 404/409 신호 때 읽는다.
 */
export function ModulesProvider({ children, subscribeSignals }: ModulesProviderProps) {
  const { rest, ws } = useApi();
  const client = useQueryClient();
  const toast = useToast();
  const baseRetry = client.getDefaultOptions().queries?.retry;
  const query = useQuery<Loaded, Error>({
    queryKey: MODULES_QUERY_KEY,
    queryFn: () => loadModules(rest),
    staleTime: FOCUS_STALE_MS,
    refetchOnWindowFocus: true,
    // 앱 기본이 재시도 없음(테스트)이면 따른다. 그 밖에는 1초·2초·4초 간격 3회.
    retry: baseRetry === false ? false : RETRY_COUNT,
    retryDelay,
    meta: { silentBackgroundError: true },
  });

  const { refetch: queryRefetch } = query;
  const refetch = useCallback(async () => {
    await queryRefetch();
  }, [queryRefetch]);

  // WS가 끊겼다가 다시 열리면 서버가 재시작되어 구성이 바뀌었을 수 있다.
  useEffect(() => {
    let wasOpen = ws.status === "open";
    return ws.onStatus((status) => {
      if (status === "open" && !wasOpen) void client.invalidateQueries({ queryKey: MODULES_QUERY_KEY });
      wasOpen = status === "open";
    });
  }, [ws, client]);

  // 기능 REST의 404는 한 번만 다시 읽고, 409 feature_unavailable은 안내 토스트 + 한 번 다시 읽는다.
  const lastSignal = useRef(0);
  useEffect(() => {
    if (subscribeSignals === undefined) return;
    return subscribeSignals((signal) => {
      if (signal.kind === "unavailable") toast({ tone: "warning", text: m.modules.featureUnavailable(signal.module, signal.port) });
      const now = Date.now();
      if (now - lastSignal.current < SIGNAL_MIN_GAP_MS) return;
      lastSignal.current = now;
      void client.invalidateQueries({ queryKey: MODULES_QUERY_KEY });
    });
  }, [subscribeSignals, client, toast]);

  const state = useMemo<ModulesState>(() => {
    if (query.data !== undefined) return query.data.kind === "list" ? { phase: "ready", modules: query.data.modules } : { phase: "unavailable", reason: "no-endpoint" };
    if (query.isError) return { phase: "unavailable", reason: "failed" };
    return { phase: "loading" };
  }, [query.data, query.isError]);
  const value = useMemo<ModulesValue>(() => ({ state, refetch, refetching: query.isFetching }), [state, refetch, query.isFetching]);
  return <ModulesContext.Provider value={value}>{children}</ModulesContext.Provider>;
}

/** 모듈 목록 상태와 [새로고침]. 공급자 밖이면 fail-open(모두 켜짐). */
export function useModules(): ModulesValue {
  return useContext(ModulesContext);
}

/** 목록이 있을 때의 모듈들(없으면 빈 배열). */
export function useModuleList(): readonly ModuleInfo[] {
  const { state } = useModules();
  return state.phase === "ready" ? state.modules : EMPTY;
}
const EMPTY: readonly ModuleInfo[] = [];

/** `requires` 판정 결과. 목록이 없으면(`unavailable`) 만족으로 본다. */
export type RequiresState = { phase: "loading" } | { phase: "met" } | { phase: "unmet"; unmet: UnmetItem[] };

const MET: RequiresState = { phase: "met" };
const LOADING: RequiresState = { phase: "loading" };
const warned = new Set<string>();

/** 개발 중 오타를 잡는다: 목록 어디에도 없는 `requires` 항목은 콘솔에 한 번만 알린다(화면 동작은 같다). */
function warnUnknown(requires: readonly string[], modules: readonly ModuleInfo[]): void {
  if (!import.meta.env.DEV || import.meta.env.MODE === "test") return;
  const known = knownNames(modules);
  for (const item of requires) {
    if (known.has(item) || warned.has(item)) continue;
    warned.add(item);
    console.warn(`[modules] requires "${item}"가 서버 모듈 목록의 id·역할 어디에도 없습니다`);
  }
}

/** 순수 판정: 상태와 `requires` -> 결과. 훅과 컨테이너가 같이 쓴다. */
export function evaluateRequires(requires: readonly string[], state: ModulesState): RequiresState {
  if (requires.length === 0) return MET;
  if (state.phase === "loading") return LOADING;
  if (state.phase === "unavailable") return MET;
  const result = resolveRequires(requires, state.modules);
  return result.satisfied ? MET : { phase: "unmet", unmet: result.unmet };
}

/**
 * `requires`(모든 항목 AND; 모듈 id 또는 역할)가 지금 만족되는가. 라우트·연동 부분·설정 섹션이 모두 이 훅 하나를 거친다.
 * 빈 배열은 항상 만족(로딩 중에도).
 */
export function useRequires(requires: readonly string[]): RequiresState {
  const { state } = useModules();
  const key = requires.join("\u0000");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stable = useMemo(() => requires, [key]);
  useEffect(() => {
    if (state.phase === "ready") warnUnknown(stable, state.modules);
  }, [state, stable]);
  return useMemo(() => evaluateRequires(stable, state), [stable, state]);
}

export interface ModuleLookup {
  /** 만족하면 true(목록을 못 받았으면 fail-open으로 true). 로딩 중에는 false. */
  active: boolean;
  loading: boolean;
  /** id 또는 역할이 일치하는 모듈들(켜짐 여부와 무관). */
  modules: ModuleInfo[];
}

/** 모듈 id 또는 역할 하나가 켜져 있는가(`useRequires([x])`의 단축형). */
export function useModule(idOrRole: string): ModuleLookup {
  const r = useRequires([idOrRole]);
  const list = useModuleList();
  return useMemo(
    () => ({ active: r.phase === "met", loading: r.phase === "loading", modules: list.filter((x) => x.id === idOrRole || (x.web_roles ?? []).includes(idOrRole)) }),
    [r.phase, list, idOrRole],
  );
}

/** `requires`를 가진 항목들(라우트·섹션 등)을 켜짐/꺼짐/확인 중으로 나눈다(순수). 순서는 입력 순서를 지킨다. */
export function partitionByRequires<T extends { requires?: readonly string[] | undefined }>(items: readonly T[], state: ModulesState): { met: T[]; unmet: T[]; loading: T[] } {
  const out: { met: T[]; unmet: T[]; loading: T[] } = { met: [], unmet: [], loading: [] };
  for (const item of items) {
    const r = evaluateRequires(item.requires ?? [], state);
    (r.phase === "met" ? out.met : r.phase === "unmet" ? out.unmet : out.loading).push(item);
  }
  return out;
}

/** 훅 형태의 {@link partitionByRequires}. 결과 배열은 목록 상태가 같으면 같은 참조다. */
export function useRequiresPartition<T extends { requires?: readonly string[] | undefined }>(items: readonly T[]) {
  const { state } = useModules();
  return useMemo(() => partitionByRequires(items, state), [items, state]);
}
