import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import type { SpaceRestClient } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { KIND_LISTERS, kindTitle } from "./useProjectHomeData";

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

/** 목록을 읽을 수 있는 정의 종류(`KIND_LISTERS` 표의 키). 공용 공간은 이 전체를 대상으로 한다. */
export const LISTABLE_KINDS: readonly string[] = Object.keys(KIND_LISTERS);

/**
 * 공간 하나의 정의 목록(종류별 병렬 조회). 공용 = `space` null.
 * @param kinds 읽을 종류(프로젝트는 `ProjectView.kinds`, 공용은 `LISTABLE_KINDS`). 목록을 읽을 수 없는 종류는 건너뛴다.
 * @param enabled false면 읽지 않는다(대화상자가 닫혀 있을 때).
 */
export function useSpaceItems(space: string | null, kinds: readonly string[], enabled: boolean): SpaceItems {
  const { space: spaceClient } = useApi();
  const readable = useMemo(() => kinds.filter((k) => Object.hasOwn(KIND_LISTERS, k)), [kinds]);
  const queries = useQueries({
    queries: readable.map((kind) => ({
      queryKey: ["list", "space-items", space ?? "", kind] as const,
      queryFn: () => (KIND_LISTERS[kind] as (c: SpaceRestClient) => Promise<{ id: string; name?: string | undefined; description?: string | undefined }[]>)(spaceClient(space)),
      enabled,
      retry: false,
      meta: { silentBackgroundError: true },
    })),
  });
  const items: SpaceItem[] = [];
  readable.forEach((kind, i) => {
    for (const x of queries[i]?.data ?? []) items.push({ kind, kindTitle: kindTitle(kind), id: x.id, name: x.name ?? x.id, description: x.description });
  });
  return {
    items,
    loading: enabled && queries.some((q) => q.isPending),
    failed: queries.some((q) => q.isError),
    retry: () => queries.forEach((q) => void q.refetch()),
  };
}
