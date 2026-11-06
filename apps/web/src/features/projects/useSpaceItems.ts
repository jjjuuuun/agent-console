import { useQueries, useQuery } from "@tanstack/react-query";
import type { CopyKindInfo } from "@agent-console/contracts/projects";
import { useApi } from "../../app/ApiContext";
import { kindTitle } from "./useProjectHomeData";

/** 한 공간(공용 또는 프로젝트 사본)에 있는 정의 하나. 종류 이름은 서버가 준 문자열 그대로다. */
export interface SpaceItem {
  kind: string;
  kindTitle: string;
  id: string;
  name: string;
  description: string | undefined;
}

export interface SpaceItems {
  items: SpaceItem[];
  loading: boolean;
  failed: boolean;
  retry: () => void;
}

/** 복사 방향을 가르는 종류 플래그(서버 `CopyKindInfo`의 불리언 필드 이름). `portable` = 프로젝트에 둘 수 있음, `library` = 공용에 둘 수 있음 */
export type CopyKindFlag = keyof Pick<CopyKindInfo, "library" | "portable">;

/**
 * 한 공간의 정의 목록. 종류 목록과 항목은 서버가 준다(`GET /projects/copy/kinds`·`/items`) — 웹은 종류 이름을 모르고,
 * 새 종류(기능 모듈이 기여한 종류)는 코드 수정 없이 나온다. 공용 = `space` null.
 * @param flag 이 플래그가 true인 종류만 읽는다(공용 → 프로젝트·프로젝트 쪽 목록 = `portable`, 프로젝트 → 공용·공용 쪽 목록 = `library`).
 * @param enabled false면 읽지 않는다(대화상자가 닫혀 있을 때).
 */
export function useSpaceItems(space: string | null, flag: CopyKindFlag, enabled: boolean): SpaceItems {
  const { rest } = useApi();
  const kindsQuery = useQuery({
    queryKey: ["list", "copy-kinds", space ?? ""] as const,
    queryFn: async () => (await rest.listCopyKinds(space)) ?? [],
    enabled,
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const kinds = (kindsQuery.data ?? []).filter((k) => k[flag]).map((k) => k.kind);
  const queries = useQueries({
    queries: kinds.map((kind) => ({
      queryKey: ["list", "space-items", space ?? "", kind] as const,
      queryFn: async () => (await rest.listCopyItems(space, kind)) ?? [],
      enabled,
      retry: false,
      meta: { silentBackgroundError: true },
    })),
  });
  const items: SpaceItem[] = [];
  kinds.forEach((kind, i) => {
    for (const x of queries[i]?.data ?? []) items.push({ kind, kindTitle: kindTitle(kind), id: x.id, name: x.name !== undefined && x.name !== "" ? x.name : x.id, description: x.description === "" ? undefined : x.description });
  });
  return {
    items,
    loading: enabled && (kindsQuery.isPending || queries.some((q) => q.isPending)),
    failed: kindsQuery.isError || queries.some((q) => q.isError),
    retry: () => {
      void kindsQuery.refetch();
      queries.forEach((q) => void q.refetch());
    },
  };
}
