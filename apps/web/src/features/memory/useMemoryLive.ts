/**
 * WS 토픽 `memory.changed` 구독. 알림은 본문 없이 "무엇이 바뀌었나"만 오므로(구독 직후 보내 주는 것도 없다)
 * 짧은 시간의 알림을 모아 한 번에 넘긴다(질의는 `debounceMs`당 최대 1회). 연결 상태도 함께 알려 준다.
 */
import { useEffect, useRef, useState } from "react";
import type { MemoryChanged } from "@agent-console/contracts/memory";
import { useApi } from "../../app/ApiContext";

export interface UseMemoryLiveOptions {
  enabled?: boolean;
  /** 지금 보는 메모리 공간(null = 공용 라이브러리, 문자열 = 프로젝트 id). 알림의 `space`가 있고 이것과 다르면 무시한다. 생략하면 거르지 않는다 */
  space?: string | null;
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

/** 알림이 지금 공간이 아닌 다른 공간의 것인가. 알림에 `space`가 없거나 지금 공간을 모르면(`undefined`) false. */
export function isOtherSpace(changed: Pick<MemoryChanged, "space">, current: string | null | undefined): boolean {
  return changed.space !== undefined && current !== undefined && changed.space !== current;
}

export function useMemoryLive({ enabled = true, space, debounceMs, onBatch, onReconnect }: UseMemoryLiveOptions): MemoryLive {
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
      // 다른 공간의 알림은 지금 목록과 상관없다. `space`가 없으면(옛 서버) 지금 목록을 다시 읽는다.
      if (isOtherSpace(changed, space)) return;
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
  }, [ws, enabled, debounceMs, space]);

  return { disconnected };
}
