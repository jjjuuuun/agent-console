import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, type BackendDescriptor, type BackendUnresolvedDetails } from "@agent-console/contracts";

/** `backend.unresolved` 오류에서 읽은 해결 카드 데이터. */
export interface UnresolvedBackend {
  /** 백엔드가 비어 있는 노드의 화면 이름(label). 노드 id는 화면에 내지 않는다 */
  labels: string[];
  options: BackendDescriptor[];
}

/** 오류가 `backend.unresolved`(422)면 카드에 필요한 데이터를, 아니면 undefined. */
export function unresolvedBackendOf(error: unknown): UnresolvedBackend | undefined {
  if (!(error instanceof ApiError) || error.code !== ERROR_CODES.BACKEND_UNRESOLVED) return undefined;
  const d = error.details as Partial<BackendUnresolvedDetails>;
  return {
    labels: (d.nodes ?? []).map((n) => n.label ?? "").filter((l) => l !== ""),
    options: d.options ?? [],
  };
}
