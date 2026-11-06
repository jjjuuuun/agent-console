/**
 * 문서 틀 화면의 서버 상태 훅. 공간(공용·프로젝트 사본)은 주소의 `?prj=`가 정하고(`SpaceScope`), 이 훅이 그 공간의 스펙 클라이언트를 만든다.
 * 질의 키는 `["sdd", 공간, …]` 아래라 `useInvalidateSdd` 한 번으로 함께 무효화된다.
 */
import { useMemo } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { SddClient, Versioned } from "@agent-console/api-client";
import { createProjectsText, projectAbilities } from "@agent-console/projects";
import type { ResourceFile } from "@agent-console/contracts";
import type { SddInfo, SpecTemplate } from "@agent-console/contracts/sdd";
import { useApi } from "../../app/ApiContext";
import { type FileEntry } from "../resources";
import { useSpace } from "../projects";
import { sddKeys } from "./useSddApi";

const text = createProjectsText();

export const templateKeys = {
  one: (p: string, id: string) => ["sdd", p, "template", id] as const,
  files: (p: string, id: string) => ["sdd", p, "template", id, "files"] as const,
};

/** 문서 틀 화면이 보는 공간: 그 공간의 클라이언트와 쓰기 가능 여부. */
export interface TemplateSpace {
  /** 프로젝트 사본이면 그 id, 공용(또는 단독)이면 null */
  projectId: string | null;
  projectName: string | undefined;
  /** 질의 키에 쓰는 공간 문자열 */
  key: string;
  client: SddClient;
  info: SddInfo | undefined;
  infoQuery: UseQueryResult<SddInfo, Error>;
  readOnly: boolean;
  readOnlyReason: string | undefined;
}

export function useTemplateSpace(): TemplateSpace {
  const { sdd } = useApi();
  const view = useSpace();
  const projectId = view?.project.id ?? null;
  const client = useMemo(() => sdd(projectId), [sdd, projectId]);
  const key = projectId ?? "";
  const infoQuery = useQuery({ queryKey: sddKeys.info(key), queryFn: () => client.getSddInfo(), retry: false, staleTime: 30_000 });
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

/** 틀 원문 + `ETag`. */
export function useSpecTemplate(space: TemplateSpace, id: string): UseQueryResult<Versioned<SpecTemplate>, Error> {
  return useQuery({ queryKey: templateKeys.one(space.key, id), queryFn: () => space.client.getSpecTemplate(id), retry: false, staleTime: 0 });
}

/** 뼈대 파일 목록과 텍스트 내용(텍스트가 아닌 파일은 `text` null). 파일 수가 적다는 전제로 한 번에 읽는다. */
export function useTemplateFiles(space: TemplateSpace, id: string): UseQueryResult<FileEntry[], Error> {
  return useQuery({
    queryKey: templateKeys.files(space.key, id),
    queryFn: async (): Promise<FileEntry[]> => {
      const list: ResourceFile[] = await space.client.listSpecTemplateFiles(id);
      return Promise.all(
        list.map(async (f) => {
          const read = await space.client.readSpecTemplateFile(id, f.path);
          return { path: f.path, text: read.text, size: read.size, ...(f.media_type == null ? {} : { mediaType: f.media_type }) };
        }),
      );
    },
    retry: false,
    staleTime: 0,
  });
}

/**
 * 문서 틀의 정의 종류 이름. 계약 스키마에는 종류 이름이 없고(설치자 데이터) 틀 원문의 `kind`만 알려 주므로,
 * 틀 하나를 읽어 거기서 얻는다(`sampleId` 생략 시 목록의 첫 틀). 틀이 하나도 없으면 undefined — 복사할 틀도 없다.
 * @param client 읽을 공간의 스펙 클라이언트(공용 틀을 가져오는 화면은 공용 클라이언트)
 * @param key 질의 키에 쓰는 공간 문자열
 */
export function useTemplateKind(client: SddClient, key: string, sampleId: string | undefined, enabled: boolean): string | undefined {
  const q = useQuery({
    queryKey: ["sdd", key, "template-kind", sampleId ?? ""] as const,
    queryFn: async (): Promise<string | null> => {
      const id = sampleId ?? (await client.listSpecTemplates())[0]?.id;
      if (id === undefined) return null;
      const read = await client.getSpecTemplate(id);
      return read.value.kind === "" ? null : read.value.kind;
    },
    enabled,
    retry: false,
    staleTime: 60_000,
  });
  return q.data ?? undefined;
}
