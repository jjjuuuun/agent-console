/**
 * WS 토픽 `memory.changed` 구독. 알림은 본문 없이 "무엇이 바뀌었나"만 오므로(구독 직후 보내 주는 것도 없다)
 * 짧은 시간의 알림을 모아 한 번에 넘긴다(질의는 `debounceMs`당 최대 1회). 연결 상태도 함께 알려 준다.
 */
import { useEffect, useRef, useState } from "react";
import type { MemoryChanged } from "@agent-console/contracts/memory";
import { useApi } from "../../app/ApiContext";

export interface UseMemoryLiveOptions {
  enabled?: boolean;
  debounceMs: number;
  /** 모인 알림(오래된 것부터). 한 번에 최대 1회, 알림이 없으면 부르지 않는다 */
  onBatch: (batch: readonly MemoryChanged[]) => void;
  /** 끊겼다가 다시 연결되었을 때(알림을 놓쳤을 수 있으므로 앱이 다시 질의한다) */
  onReconnect?: () => void;
}

export interface MemoryLive {
  /** 실시간 연결이 끊겼는가(재접속 시도 중이거나 닫힘) */
  disconnected: boolean;
}

export function useMemoryLive({ enabled = true, debounceMs, onBatch, onReconnect }: UseMemoryLiveOptions): MemoryLive {
  const { ws } = useApi();
  const [disconnected, setDisconnected] = useState(() => ws.status === "reconnecting" || ws.status === "closed");
  const latest = useRef({ onBatch, onReconnect });
  useEffect(() => {
    latest.current = { onBatch, onReconnect };
  });

  useEffect(() => {
    if (!enabled) return;
    let buffer: MemoryChanged[] = [];
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      timer = undefined;
      const batch = buffer;
      buffer = [];
      if (batch.length > 0) latest.current.onBatch(batch);
    };
    const sub = ws.subscribeMemory((changed) => {
      buffer.push(changed);
      // 첫 알림에서 창을 열고, 창이 끝날 때 한 번 넘긴다(그동안 온 알림은 모두 포함)
      timer ??= setTimeout(flush, debounceMs);
    });
    let lost = ws.status === "reconnecting" || ws.status === "closed";
    const off = ws.onStatus((status) => {
      const down = status === "reconnecting" || status === "closed";
      if (lost && status === "open") latest.current.onReconnect?.();
      lost = down ? true : status === "open" ? false : lost;
      setDisconnected(down);
    });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      off();
      sub.unsubscribe();
    };
  }, [ws, enabled, debounceMs]);

  return { disconnected };
}
