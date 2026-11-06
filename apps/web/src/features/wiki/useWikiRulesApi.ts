/**
 * 공용 구성 › 위키 규칙 화면의 서버 상태 훅. 공간(공용·프로젝트 사본)은 주소의 `?prj=`가 정하고(`SpaceScope`) 이 훅이 그 공간의 위키 클라이언트를 만든다.
 * 위키 규칙 REST는 정의 모듈 없이도 동작한다. 질의 키는 `["wiki", 공간, "rules", …]` 아래라 `useInvalidateWiki` 한 번으로 함께 무효화된다.
 */
import { useMemo } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { Versioned, WikiClient } from "@agent-console/api-client";
import { createProjectsText, projectAbilities } from "@agent-console/projects";
import type { ResourceFile } from "@agent-console/contracts";
import type { WikiInfo, WikiRulesListItem, WikiRulesView } from "@agent-console/contracts/wiki";
import { useApi } from "../../app/ApiContext";
import { type FileEntry } from "../resources";
import { useSpace } from "../projects";
import { wikiKeys } from "./useWikiApi";

const text = createProjectsText();

export const wikiRulesKeys = {
  list: (p: string) => wikiKeys.rules(p),
  one: (p: string, id: string) => [...wikiKeys.rules(p), id] as const,
  files: (p: string, id: string) => [...wikiKeys.rules(p), id, "files"] as const,
  info: (p: string) => wikiKeys.info(p),
};

/** 위키 규칙 화면이 보는 공간: 그 공간의 클라이언트와 쓰기 가능 여부. */
export interface WikiRulesSpace {
  /** 프로젝트 사본이면 그 id, 공용(또는 단독)이면 null */
  projectId: string | null;
  projectName: string | undefined;
  /** 질의 키에 쓰는 공간 문자열 */
  key: string;
  client: WikiClient;
  info: WikiInfo | undefined;
  infoQuery: UseQueryResult<WikiInfo, Error>;
  readOnly: boolean;
  readOnlyReason: string | undefined;
}

export function useWikiRulesSpace(): WikiRulesSpace {
  const { wiki } = useApi();
  const view = useSpace();
  const projectId = view?.project.id ?? null;
  const client = useMemo(() => wiki(projectId), [wiki, projectId]);
  const key = projectId ?? "";
  const infoQuery = useQuery({ queryKey: wikiRulesKeys.info(key), queryFn: () => client.getWikiInfo(), retry: false, staleTime: 30_000 });
  const info = infoQuery.data;
  return useMemo(() => {
    const abilities = view === null ? undefined : projectAbilities(view, { recordsWritable: view.records_writable !== false });
    const editBlocked = abilities?.edit.allowed === false ? abilities.edit.reason : null;
    const infoReadonly = info?.writable === false;
    return {
      projectId,
      projectName: view?.project.name,
      key,
      client,
      info,
      infoQuery,
      readOnly: editBlocked !== null || infoReadonly,
      readOnlyReason: editBlocked !== null ? text(editBlocked) : infoReadonly ? text("projects.blocked.edit") : undefined,
    };
  }, [view, projectId, key, client, info, infoQuery]);
}

export function useWikiRulesItems(space: WikiRulesSpace): UseQueryResult<WikiRulesListItem[], Error> {
  return useQuery({ queryKey: wikiRulesKeys.list(space.key), queryFn: () => space.client.listWikiRules(), retry: false, staleTime: 0 });
}

/** 규칙 원문 + `ETag` + 쓰는 위키 + 서버 검사 이슈. */
export function useWikiRulesView(space: WikiRulesSpace, id: string): UseQueryResult<Versioned<WikiRulesView>, Error> {
  return useQuery({ queryKey: wikiRulesKeys.one(space.key, id), queryFn: () => space.client.getWikiRules(id), retry: false, staleTime: 0 });
}

/** 본문 파일 목록과 텍스트 내용(텍스트가 아닌 파일은 `text` null). 파일 수가 적다는 전제로 한 번에 읽는다. */
export function useWikiRuleFiles(space: WikiRulesSpace, id: string): UseQueryResult<FileEntry[], Error> {
  return useQuery({
    queryKey: wikiRulesKeys.files(space.key, id),
    queryFn: async (): Promise<FileEntry[]> => {
      const list: ResourceFile[] = await space.client.listWikiRulesFiles(id);
      return Promise.all(
        list.map(async (f) => {
          const read = await space.client.readWikiRulesFile(id, f.path);
          return { path: f.path, text: read.text, size: read.size, ...(f.media_type == null ? {} : { mediaType: f.media_type }) };
        }),
      );
    },
    retry: false,
    staleTime: 0,
  });
}

/**
 * 위키 규칙의 정의 종류 이름. 계약 스키마에는 이름이 없고(설치자 데이터) 규칙 원문의 `kind`만 알려 주므로 규칙 하나를 읽어 얻는다.
 * 규칙이 하나도 없으면 undefined — 복사할 규칙도 없다.
 */
export function useWikiRulesKind(client: WikiClient, key: string, sampleId: string | undefined, enabled: boolean): string | undefined {
  const q = useQuery({
    queryKey: [...wikiKeys.rules(key), "kind", sampleId ?? ""] as const,
    queryFn: async (): Promise<string | null> => {
      const id = sampleId ?? (await client.listWikiRules())[0]?.id;
      if (id === undefined) return null;
      const read = await client.getWikiRules(id);
      return read.value.rules.kind === "" ? null : read.value.rules.kind;
    },
    enabled,
    retry: false,
    staleTime: 60_000,
  });
  return q.data ?? undefined;
}
