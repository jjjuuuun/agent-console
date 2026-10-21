import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { WsClient } from "@agent-console/api-client";
import type { Interaction } from "@agent-console/contracts";

export interface PendingInteractions {
  /** 응답 대기 중인 상호작용(가장 오래 기다린 것이 앞) */
  items: readonly Interaction[];
  count: number;
}

const PendingContext = createContext<PendingInteractions>({ items: [], count: 0 });

/**
 * WS 전역 토픽 `interactions`를 구독해 응답 대기 목록을 유지한다(사이드바 배지·문서 제목·단축키의 원천).
 * 구독 직후 현재 대기 목록이 하나씩 오고, 이후 `pending`이 아닌 상태가 오면 목록에서 뺀다.
 */
export function PendingInteractionsProvider({ ws, enabled = true, children }: { ws: WsClient; /** false면 구독하지 않고 대기 목록은 비어 있다(상호작용 연동이 꺼진 서버) */ enabled?: boolean; children: ReactNode }) {
  const [map, setMap] = useState<ReadonlyMap<string, Interaction>>(new Map());
  useEffect(() => {
    if (!enabled) return;
    const sub = ws.subscribeInteractions((interaction) => {
      setMap((cur) => {
        const next = new Map(cur);
        if (interaction.status === "pending") next.set(interaction.id, interaction);
        else next.delete(interaction.id);
        return next;
      });
    });
    return () => sub.unsubscribe();
  }, [ws, enabled]);
  const value = useMemo<PendingInteractions>(() => {
    const items = !enabled ? [] : [...map.values()].sort((a, b) => a.created_at - b.created_at);
    return { items, count: items.length };
  }, [map, enabled]);
  return <PendingContext.Provider value={value}>{children}</PendingContext.Provider>;
}

export function usePendingInteractions(): PendingInteractions {
  return useContext(PendingContext);
}
