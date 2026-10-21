import type { DefinitionDiff, DefinitionVersion, ResourceFile } from "@agent-console/contracts";
import type { UseQueryResult } from "@tanstack/react-query";
import { useApiQuery } from "../../app/queries";

/** 버전 질의 키(정의 경로 `base`별). 되돌린 뒤 `["versions", base]`를 무효화하면 전부 다시 읽는다. */
export const versionKeys = {
  all: (base: string) => ["versions", base] as const,
  list: (base: string) => ["versions", base, "list"] as const,
  doc: (base: string, hash: string) => ["versions", base, "doc", hash] as const,
  diff: (base: string, from: string, to: string | undefined) => ["versions", base, "diff", from, to ?? "current"] as const,
  files: (base: string, hash: string) => ["versions", base, "files", hash] as const,
};

/** 버전 목록(최신순, 본문 없음). 열 때마다 최신을 읽는다. */
export function useVersionList(base: string): UseQueryResult<DefinitionVersion[], Error> {
  return useApiQuery(versionKeys.list(base), (rest) => rest.listDefinitionVersions(base), { staleTime: 0 });
}

/** 한 버전의 정의 원문(`content`). `hash`가 없으면 읽지 않는다. */
export function useVersionDoc(base: string, hash: string | undefined): UseQueryResult<DefinitionVersion, Error> {
  return useApiQuery(versionKeys.doc(base, hash ?? ""), (rest) => rest.getDefinitionVersion(base, hash ?? ""), { enabled: hash !== undefined });
}

/** 두 버전 비교(`to` 생략 = 현재). `from`이 없으면 읽지 않는다. */
export function useVersionDiff(base: string, from: string | undefined, to: string | undefined, enabled = true): UseQueryResult<DefinitionDiff, Error> {
  return useApiQuery(versionKeys.diff(base, from ?? "", to), (rest) => rest.diffDefinitionVersions(base, from ?? "", to), {
    enabled: enabled && from !== undefined,
    staleTime: 0,
    retry: false,
  });
}

/** 그 버전의 본문 파일 목록(스냅샷이 없으면 404 -> 오류 상태, 호출 측은 크기를 모르는 것으로 본다). */
export function useVersionFiles(base: string, hash: string | undefined, enabled: boolean): UseQueryResult<ResourceFile[], Error> {
  return useApiQuery(versionKeys.files(base, hash ?? ""), (rest) => rest.listVersionFiles(base, hash ?? ""), { enabled: enabled && hash !== undefined, retry: false });
}
