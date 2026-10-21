import type { BackendDescriptor } from "@agent-console/contracts";

export { effectiveBackendId } from "../../backendChoice";

/** 디스크립터 `ui_hints.badge` 문구(없으면 undefined). 어떤 백엔드가 칩을 다는지는 서버 데이터가 정한다. */
export function badgeOfBackend(backends: ReadonlyMap<string, BackendDescriptor>, backendId: string | undefined): string | undefined {
  if (backendId === undefined) return undefined;
  const badge = backends.get(backendId)?.ui_hints?.badge;
  return badge ? badge : undefined;
}
