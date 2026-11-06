import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import type { SpaceRestClient } from "@agent-console/api-client";
import type { ProjectView } from "@agent-console/contracts/projects";
import { useApi } from "../../app/ApiContext";
import { lookupMessage } from "../../app/messages";
import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { DEFINITION_KINDS, ROUTE_ROLES, definitionPath, useRouteOn } from "../library";
import { mergeActivity, type ActivityRow } from "./projectHomeLib";

/** 구성 표의 한 행. 종류 이름은 코드에 없다(`kind`는 서버가 준 문자열, 제목은 라우트 데이터에서). */
export interface ConfigRow {
  key: string;
  kind: string;
  kindTitle: string;
  id: string;
  name: string;
  /** 마지막 수정(초). 목록이 주지 않으면 undefined */
  modifiedAt: number | undefined;
  /** 편집 화면 주소(`?prj=`). 이 종류의 편집 화면이 없으면 undefined */
  href: string | undefined;
}

interface ListedItem {
  id: string;
  name?: string | undefined;
  saved_at?: number | null | undefined;
}

/**
 * 종류별 목록 읽기(데이터 표): 정의 종류(저장소 kind) -> 공간 클라이언트로 목록을 읽는 함수.
 * 종류가 늘면 항목을 더한다. 표에 없는 종류는 목록을 읽을 수 없어 구성 표에서 빠진다(오류 아님).
 */
const KIND_LISTERS: Readonly<Record<string, (c: SpaceRestClient) => Promise<ListedItem[]>>> = {
  ...(DEFINITION_KINDS.agent === undefined ? {} : { [DEFINITION_KINDS.agent]: (c: SpaceRestClient) => c.listAgents() }),
  ...(DEFINITION_KINDS.graph === undefined ? {} : { [DEFINITION_KINDS.graph]: (c: SpaceRestClient) => c.listGraphs() }),
  ...(DEFINITION_KINDS.resource === undefined ? {} : { [DEFINITION_KINDS.resource]: (c: SpaceRestClient) => c.listResources() }),
};

const collator = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });

/** 종류 제목: 그 종류를 편집하는 화면(라우트)의 제목. 화면이 없으면 종류 문자열 원문. */
export function kindTitle(kind: string): string {
  const route = routeServing(DEFAULT_ROUTES, `definition:${kind}`);
  return route === undefined ? kind : lookupMessage(route.titleKey);
}

export interface ProjectConfig {
  rows: ConfigRow[];
  loading: boolean;
  /** 읽지 못한 종류 */
  failed: { kind: string; title: string }[];
  retry: (kind: string) => void;
  /** 이 프로젝트에 둘 수 있는 종류(새로 만들기 메뉴): 편집 화면이 있는 종류 */
  creatable: { kind: string; title: string; href: string }[];
}

/**
 * 프로젝트 사본 저장소의 구성 목록: `ProjectView.kinds`를 순서대로 `?project=<id>`로 읽어 합친다(병렬, 일부 실패해도 나머지는 보인다).
 * `enabled=false`(폴더를 읽을 수 없음 등)면 읽지 않는다.
 */
export function useProjectConfig(view: ProjectView | undefined, enabled: boolean): ProjectConfig {
  const { space } = useApi();
  const id = view?.project.id ?? "";
  const kinds = useMemo(() => (view?.kinds ?? []).filter((k) => Object.hasOwn(KIND_LISTERS, k)), [view?.kinds]);
  const queries = useQueries({
    queries: kinds.map((kind) => ({
      queryKey: ["list", "project-config", id, kind] as const,
      queryFn: () => (KIND_LISTERS[kind] as (c: SpaceRestClient) => Promise<ListedItem[]>)(space(id)),
      enabled: enabled && id !== "",
      retry: false,
      meta: { silentBackgroundError: true },
    })),
  });
  const rows: ConfigRow[] = [];
  const failed: { kind: string; title: string }[] = [];
  kinds.forEach((kind, i) => {
    const q = queries[i];
    if (q?.isError) failed.push({ kind, title: kindTitle(kind) });
    for (const item of q?.data ?? []) {
      const path = definitionPath(kind, item.id);
      rows.push({
        key: `${kind}:${item.id}`,
        kind,
        kindTitle: kindTitle(kind),
        id: item.id,
        name: item.name ?? item.id,
        modifiedAt: item.saved_at ?? undefined,
        href: path === undefined ? undefined : `${path}?prj=${encodeURIComponent(id)}`,
      });
    }
  });
  rows.sort((a, b) => collator.compare(a.kindTitle, b.kindTitle) || collator.compare(a.name, b.name));
  const creatable = (view?.kinds ?? []).flatMap((kind) => {
    const route = routeServing(DEFAULT_ROUTES, `definition:${kind}`);
    return route === undefined ? [] : [{ kind, title: kindTitle(kind), href: `${route.path}?prj=${encodeURIComponent(id)}` }];
  });
  return {
    rows,
    loading: enabled && queries.some((q) => q.isPending),
    failed,
    retry: (kind: string) => {
      const i = kinds.indexOf(kind);
      void queries[i]?.refetch();
    },
    creatable,
  };
}

export interface ProjectActivity {
  rows: ActivityRow[];
  loading: boolean;
  failed: boolean;
  chatsOn: boolean;
  runsOn: boolean;
}

/** 최근 활동: 채팅과 실행을 합친 한 목록(최대 8행). 꺼진 기능의 질의는 하지 않는다. 폴더 기록을 읽을 수 없으면 읽지 않는다. */
export function useProjectActivity(projectId: string, enabled: boolean): ProjectActivity {
  const { rest } = useApi();
  const chatsOn = useRouteOn(ROUTE_ROLES.conversations);
  const runsOn = useRouteOn(ROUTE_ROLES.runs);
  const chats = useQuery({
    queryKey: ["list", "project-activity", "chats", projectId],
    queryFn: () => rest.listConversations({ project: projectId }),
    enabled: enabled && chatsOn && projectId !== "",
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const runs = useQuery({
    queryKey: ["list", "project-activity", "runs", projectId],
    queryFn: () => rest.listRuns({ project: projectId }),
    enabled: enabled && runsOn && projectId !== "",
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const rows = useMemo(() => mergeActivity(chats.data ?? [], runs.data ?? []), [chats.data, runs.data]);
  return { rows, loading: (chatsOn && chats.isPending && enabled) || (runsOn && runs.isPending && enabled), failed: chats.isError || runs.isError, chatsOn, runsOn };
}
