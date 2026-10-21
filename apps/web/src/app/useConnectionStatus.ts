import { useCallback, useSyncExternalStore } from "react";
import type { ConnectionStatus, WsClient } from "@agent-console/api-client";

/** WS 연결 상태를 구독한다. */
export function useConnectionStatus(ws: WsClient): ConnectionStatus {
  const subscribe = useCallback((listener: () => void) => ws.onStatus(() => listener()), [ws]);
  const getSnapshot = useCallback(() => ws.status, [ws]);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
