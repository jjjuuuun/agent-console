import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import type { SpaceRestClient } from "@agent-console/api-client";
import type { CopyKindInfo, ProjectView } from "@agent-console/contracts/projects";
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

/** 종류별 삭제(데이터 표): 정의 종류 -> 공간 클라이언트로 하나 지우는 함수. 표에 없는 종류는 행 메뉴에 삭제가 없다. */
export const KIND_DELETERS: Readonly<Record<string, (c: SpaceRestClient, id: string) => Promise<void>>> = {
  ...(DEFINITION_KINDS.agent === undefined ? {} : { [DEFINITION_KINDS.agent]: (c: SpaceRestClient, id: string) => c.deleteAgent(id) }),
  ...(DEFINITION_KINDS.graph === undefined ? {} : { [DEFINITION_KINDS.graph]: (c: SpaceRestClient, id: string) => c.deleteGraph(id) }),
  ...(DEFINITION_KINDS.resource === undefined ? {} : { [DEFINITION_KINDS.resource]: (c: SpaceRestClient, id: string) => c.deleteResource(id) }),
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
 * 프로젝트 사본 저장소의 구성 목록: 서버가 주는 종류 목록(`GET /projects/copy/kinds?project=`, 프로젝트에 둘 수 있는 `portable` 종류)을
 * 순서대로 `GET /projects/copy/items`로 읽어 합친다(병렬, 일부 실패해도 나머지는 보인다). 종류 이름은 코드에 없다 —
 * 기능 모듈이 기여한 종류(문서 틀·위키 등)도 코드 수정 없이 나온다. 종류 제목은 `CopyKindInfo.title` → 편집 화면 제목 → 종류 원문.
 * `enabled=false`(폴더를 읽을 수 없음 등)면 읽지 않는다.
 */
export function useProjectConfig(view: ProjectView | undefined, enabled: boolean): ProjectConfig {
  const { rest } = useApi();
  const id = view?.project.id ?? "";
  const on = enabled && id !== "";
  const kindsQuery = useQuery({
    queryKey: ["list", "project-config-kinds", id] as const,
    queryFn: async () => (await rest.listCopyKinds(id)) ?? [],
    enabled: on,
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const infos = useMemo(() => (kindsQuery.data ?? []).filter((k) => k.portable), [kindsQuery.data]);
  const titleOf = (info: CopyKindInfo): string => (info.title != null && info.title !== "" ? info.title : kindTitle(info.kind));
  const queries = useQueries({
    queries: infos.map((info) => ({
      queryKey: ["list", "project-config", id, info.kind] as const,
      queryFn: async () => (await rest.listCopyItems(id, info.kind)) ?? [],
      enabled: on,
      retry: false,
      meta: { silentBackgroundError: true },
    })),
  });
  const rows: ConfigRow[] = [];
  const failed: { kind: string; title: string }[] = [];
  if (kindsQuery.isError) failed.push({ kind: "", title: "" }) // kind "" = 종류 목록 자체를 못 읽음;
  infos.forEach((info, i) => {
    const q = queries[i];
    const title = titleOf(info);
    if (q?.isError) failed.push({ kind: info.kind, title });
    for (const item of q?.data ?? []) {
      const path = definitionPath(info.kind, item.id);
      rows.push({
        key: `${info.kind}:${item.id}`,
        kind: info.kind,
        kindTitle: title,
        id: item.id,
        name: item.name !== undefined && item.name !== "" ? item.name : item.id,
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
    loading: on && (kindsQuery.isPending || queries.some((q) => q.isPending)),
    failed,
    retry: (kind: string) => {
      if (kind === "") void kindsQuery.refetch();
      void queries[infos.findIndex((k) => k.kind === kind)]?.refetch();
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
