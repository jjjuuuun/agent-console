import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { BackendDescriptor, BackendProbeResult, BackendReadiness } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { queryKeys } from "../../app/queries";

const statusKey = () => queryKeys.list("backend-status");

/**
 * 모든 백엔드의 정적 점검 상태. 화면이 열릴 때 한 번 읽고 [다시 확인]으로만 갱신한다(폴링·창 포커스 갱신 없음).
 * 실행 백엔드 모듈이 꺼져 404면 빈 표(카드·칩이 사라진다).
 */
export function useBackendReadiness() {
  const { rest } = useApi();
  const query = useQuery<Record<string, BackendReadiness>, Error>({
    queryKey: statusKey(),
    queryFn: async () => {
      try {
        const list = await rest.listBackendStatuses();
        return Object.fromEntries(list.map((r) => [r.backend_id, r]));
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return {};
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
        queryClient.setQueryData<Record<string, BackendReadiness>>(statusKey(), (old) => ({ ...(old ?? {}), [id]: next }));
      } finally {
        setRechecking(null);
      }
    },
    [rest, queryClient],
  );
  return { ...query, readiness: query.data ?? {}, recheck, rechecking };
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
