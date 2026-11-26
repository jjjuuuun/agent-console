import { useMemo } from "react";
import { ApiError } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { useVersionDiff, useVersionList } from "./useVersionData";

/**
 * 서버가 이 정의 경로의 버전 비교를 주는지 확인한다(능력 확인, 서버 버전 문자열은 보지 않는다).
 * 가장 새 버전을 현재와 비교하는 요청 하나를 보내 404면 "지원 안 함"(옛 서버)으로 본다.
 * 버전이 아직 없거나 확인 중이면 true(깜빡임 없이 비교 칸을 둔다), 404 아닌 오류도 true(비교 칸이 오류를 보인다).
 * @param base 정의 경로
 * @param space 프로젝트 사본 공간 id(없으면 공용)
 */
export function useCompareSupport(base: string, space?: string | null): boolean {
  const api = useApi();
  const rest = useMemo(() => (space === undefined || space === null ? api.rest : api.space(space)), [api, space]);
  const src = useMemo(() => ({ client: rest, scope: space ?? "" }), [rest, space]);
  const list = useVersionList(base, src);
  const probe = useVersionDiff(base, list.data?.[0]?.version_hash, undefined, src);
  return !(probe.error instanceof ApiError && probe.error.status === 404);
}
