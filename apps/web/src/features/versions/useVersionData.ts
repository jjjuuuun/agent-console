import type { DefinitionDiff, DefinitionVersion, ResourceFile } from "@agent-console/contracts";
import type { UseQueryResult } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import type { SpaceRestClient } from "@agent-console/api-client";

/** 버전 질의 키(정의 경로 `base`별). 되돌린 뒤 `["versions", base]`를 무효화하면 전부 다시 읽는다. */
export const versionKeys = {
  all: (base: string, scope = "") => ["versions", base, scope] as const,
  list: (base: string, scope = "") => ["versions", base, scope, "list"] as const,
  doc: (base: string, hash: string, scope = "") => ["versions", base, scope, "doc", hash] as const,
  diff: (base: string, from: string, to: string | undefined, scope = "") => ["versions", base, scope, "diff", from, to ?? "current"] as const,
  files: (base: string, hash: string, scope = "") => ["versions", base, scope, "files", hash] as const,
};

/** 버전 질의가 쓰는 클라이언트와 캐시 구분값(공간 id, 없으면 ""). 공간이 다르면 같은 `base`도 다른 데이터다. */
export interface VersionSource {
  client: SpaceRestClient;
  scope: string;
}

/** 버전 목록(최신순, 본문 없음). 열 때마다 최신을 읽는다. */
export function useVersionList(base: string, src: VersionSource): UseQueryResult<DefinitionVersion[], Error> {
  return useQuery({ queryKey: versionKeys.list(base, src.scope), queryFn: () => src.client.listDefinitionVersions(base), staleTime: 0 });
}

/** 한 버전의 정의 원문(`content`). `hash`가 없으면 읽지 않는다. */
export function useVersionDoc(base: string, hash: string | undefined, src: VersionSource): UseQueryResult<DefinitionVersion, Error> {
  return useQuery({ queryKey: versionKeys.doc(base, hash ?? "", src.scope), queryFn: () => src.client.getDefinitionVersion(base, hash ?? ""), enabled: hash !== undefined });
}

/** 두 버전 비교(`to` 생략 = 현재). `from`이 없으면 읽지 않는다. */
export function useVersionDiff(base: string, from: string | undefined, to: string | undefined, src: VersionSource, enabled = true): UseQueryResult<DefinitionDiff, Error> {
  return useQuery({
    queryKey: versionKeys.diff(base, from ?? "", to, src.scope),
    queryFn: () => src.client.diffDefinitionVersions(base, from ?? "", to),
    enabled: enabled && from !== undefined,
    staleTime: 0,
    retry: false,
  });
}

/** 그 버전의 본문 파일 목록(스냅샷이 없으면 404 -> 오류 상태, 호출 측은 크기를 모르는 것으로 본다). */
export function useVersionFiles(base: string, hash: string | undefined, enabled: boolean, src: VersionSource): UseQueryResult<ResourceFile[], Error> {
  return useQuery({ queryKey: versionKeys.files(base, hash ?? "", src.scope), queryFn: () => src.client.listVersionFiles(base, hash ?? ""), enabled: enabled && hash !== undefined, retry: false });
}
