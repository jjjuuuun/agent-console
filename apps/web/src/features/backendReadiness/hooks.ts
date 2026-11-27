import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { BackendDescriptor, BackendProbeResult, BackendReadiness } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { queryKeys } from "../../app/queries";

const statusKey = () => queryKeys.list("backend-status");

const NO_STATUS: Record<string, BackendReadiness> = {};

/** 캐시에 담는 값: 백엔드별 점검 결과 + 준비 상태 경로가 있는지(404면 없음). */
interface StatusSnapshot {
  byId: Record<string, BackendReadiness>;
  available: boolean;
}

/**
 * 모든 백엔드의 정적 점검 상태. 화면이 열릴 때 한 번 읽고 [다시 확인]으로만 갱신한다(폴링·창 포커스 갱신 없음).
 * 실행 백엔드 모듈이 꺼져 404면 빈 표이고 `available`이 false다.
 */
export function useBackendReadiness() {
  const { rest } = useApi();
  const query = useQuery<StatusSnapshot, Error>({
    queryKey: statusKey(),
    queryFn: async () => {
      try {
        const list = await rest.listBackendStatuses();
        return { byId: Object.fromEntries(list.map((r) => [r.backend_id, r])), available: true };
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return { byId: {}, available: false };
        throw e;
      }
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: false,
  });
  const queryClient = useQueryClient();
  const [rechecking, setRechecking] = useState<string | null>(null);
  /** 백엔드 하나만 다시 읽는다. */
  const recheck = useCallback(
    async (id: string) => {
      setRechecking(id);
      try {
        const next = await rest.getBackendStatus(id);
        queryClient.setQueryData<StatusSnapshot>(statusKey(), (old) => ({ byId: { ...(old?.byId ?? {}), [id]: next }, available: true }));
      } finally {
        setRechecking(null);
      }
    },
    [rest, queryClient],
  );
  // available: 준비 상태 경로가 있는가(404면 false, 아직 모르면 true)
  return { ...query, readiness: query.data?.byId ?? NO_STATUS, available: query.data?.available ?? true, recheck, rechecking };
}

/** 연결 테스트 한 번의 화면 상태(서버는 결과를 기억하지 않으므로 화면 메모리에만 둔다). */
export interface ProbeView {
  running: boolean;
  result: BackendProbeResult | null;
  /** 요청 자체가 실패했을 때(결과를 받지 못함) */
  requestError: Error | null;
  /** 이 화면이 마지막 결과를 받은 시각(ms) */
  finishedAtMs: number | null;
  run: () => void;
}

/** 연결 테스트. `run`을 부르는 곳이 실제 호출이 일어나는 유일한 지점이다. */
export function useBackendProbe(descriptor: Pick<BackendDescriptor, "id">): ProbeView {
  const { rest } = useApi();
  const [finishedAtMs, setFinishedAtMs] = useState<number | null>(null);
  const mutation = useMutation<BackendProbeResult, Error>({
    mutationFn: () => rest.probeBackend(descriptor.id),
    onSettled: () => setFinishedAtMs(Date.now()),
  });
  const run = useCallback(() => mutation.mutate(), [mutation]);
  return { running: mutation.isPending, result: mutation.data ?? null, requestError: mutation.error, finishedAtMs, run };
}
