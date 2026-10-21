/**
 * WS 토픽 `logs`(수집 알림) 구독을 화면 하나에 한 번만 열고, 화면 안의 소비자에게 나눠 준다.
 * `logs.ingested`는 어느 세션이 바뀌었는지 모르므로 행을 끼워 넣지 않고, 각 화면이 규칙(`screen-logs.md` 1.6)대로 다시 조회한다.
 * 재연결에 성공하면 모든 로그 질의를 한 번 무효화한다.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { LogsIngestedPayload } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { LOGS_LIMITS } from "./logsConfig";
import { logKeys } from "./useLogsApi";

type Listener = (payload: LogsIngestedPayload) => void;
interface LiveValue {
  subscribe(listener: Listener): () => void;
}
const LiveContext = createContext<LiveValue>({ subscribe: () => () => undefined });

export function LogsLiveProvider({ children, enabled = true }: { children: ReactNode; enabled?: boolean }) {
  const { ws } = useApi();
  const qc = useQueryClient();
  const listeners = useRef(new Set<Listener>());
  const subscribe = useCallback((l: Listener) => {
    listeners.current.add(l);
    return () => void listeners.current.delete(l);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sub = ws.subscribeLogs((p) => {
      void qc.invalidateQueries({ queryKey: logKeys.total0() });
      // 출처 상태는 1초 디바운스로 다시 읽는다.
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(() => void qc.invalidateQueries({ queryKey: logKeys.sources() }), LOGS_LIMITS.sourcesDebounceMs);
      for (const l of [...listeners.current]) l(p);
    });
    let seenOpen = ws.status === "open";
    const off = ws.onStatus((status) => {
      if (status !== "open") return;
      if (seenOpen) void qc.invalidateQueries({ queryKey: logKeys.root });
      seenOpen = true;
    });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      off();
      sub.unsubscribe();
    };
  }, [ws, qc, enabled]);

  const value = useMemo(() => ({ subscribe }), [subscribe]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export interface IngestInfo {
  /** 디바운스 동안 모인 새 이벤트 수 */
  count: number;
}

/**
 * 수집 알림을 `debounceMs` 디바운스로 받는다(그동안의 `count`를 더해서). `enabled`가 false면 받지 않는다.
 * `onIngested`는 렌더마다 바뀌어도 된다(최신 함수를 부른다).
 */
export function useLogsIngested(onIngested: (info: IngestInfo) => void, debounceMs: number, enabled = true): void {
  const { subscribe } = useContext(LiveContext);
  const latest = useRef(onIngested);
  useEffect(() => {
    latest.current = onIngested;
  });
  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let count = 0;
    const off = subscribe((p) => {
      count += p.count;
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(() => {
        const n = count;
        count = 0;
        latest.current({ count: n });
      }, debounceMs);
    });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      off();
    };
  }, [subscribe, debounceMs, enabled]);
}
