import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { RunEvent } from "@agent-console/contracts";
import { useApiQuery } from "../../app/queries";
import { RUN_REFETCH_DEBOUNCE_MS } from "./runsConfig";

const NO_EVENTS: readonly RunEvent[] = [];
const nodeEventsKey = (runId: string, nodeId: string) => ["run", runId, "events-node", nodeId] as const;

/**
 * 한 노드의 이벤트를 서버가 거른 대로 읽는다(`GET /runs/{id}/events?node=`, 하위 그래프 안 이벤트 포함).
 * 노드를 고르지 않았으면 읽지 않는다. 실행 중에 새 이벤트가 오면(`lastSeq`가 바뀌면) 짧게 모아 다시 읽는다.
 * @param lastSeq 지금까지 받은 마지막 이벤트 seq(없으면 undefined)
 */
export function useRunNodeEvents(runId: string, nodeId: string | null, lastSeq: number | undefined): { events: readonly RunEvent[]; loading: boolean } {
  const qc = useQueryClient();
  const q = useApiQuery<RunEvent[]>(nodeEventsKey(runId, nodeId ?? ""), (r) => r.listRunEvents(runId, { node: nodeId as string }), { enabled: nodeId !== null });
  useEffect(() => {
    if (nodeId === null || lastSeq === undefined) return;
    const timer = setTimeout(() => void qc.invalidateQueries({ queryKey: nodeEventsKey(runId, nodeId), exact: true }), RUN_REFETCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [qc, runId, nodeId, lastSeq]);
  return { events: nodeId === null ? NO_EVENTS : (q.data ?? NO_EVENTS), loading: nodeId !== null && q.isPending };
}
