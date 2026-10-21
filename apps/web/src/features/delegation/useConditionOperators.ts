import { useCallback } from "react";
import type { RestClient } from "@agent-console/api-client";
import { queryKeys, useApiQuery } from "../../app/queries";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import type { ConditionOperatorDescriptor } from "./conditions";
import type { OperatorsState } from "./ConditionList";

const loadOperators = (rest: RestClient) => rest.listConditionOperators();

/** 연산자 목록 캐시 시간(편집기 열 때 1회, screen-delegation.md 1.4). */
export const OPERATORS_STALE_MS = 5 * 60_000;

export interface ConditionOperatorsResult {
  operators: readonly ConditionOperatorDescriptor[] | null;
  state: OperatorsState;
  retry(): void;
}

/**
 * 조건 연산자 목록(`GET /condition-operators`). 연동 부분 `teams.condition-operators`가 꺼져 있으면(실행 기능 없음)
 * 서버를 부르지 않고 `absent`로 돌려준다 — 위젯은 연산자를 자유 입력으로 받는다. 모듈 목록을 확인하는 동안은 `loading`.
 */
export function useConditionOperators(): ConditionOperatorsResult {
  const part = useLinkPart(LINK_PART_IDS.teamsConditionOperators);
  const off = !part.visible && part.off;
  const query = useApiQuery(queryKeys.descriptors("condition-operators"), loadOperators, { enabled: part.visible, staleTime: OPERATORS_STALE_MS });
  const retry = useCallback(() => void query.refetch(), [query]);
  if (off) return { operators: null, state: "absent", retry };
  if (!part.visible) return { operators: null, state: "loading", retry };
  if (query.isError) return { operators: null, state: "error", retry };
  if (query.data === undefined) return { operators: null, state: "loading", retry };
  return { operators: query.data, state: "ready", retry };
}
