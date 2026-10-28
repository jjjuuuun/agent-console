import { useEffect, useMemo } from "react";
import type { LogQueryParams } from "@agent-console/api-client";
import { useStorage } from "../../../app/StorageContext";
import { archChannelName, createArchSync, type ArchSync, type ChannelFactory } from "./archSync";
import { ARCH_POPOUT } from "./popoutConfig";
import { useArchPopout, type ArchPopout, type OpenWindow } from "./useArchPopout";

export interface UseArchPopoutHostOptions {
  /** 범위 종류(`session`·`run` 등. 채널 이름·분리 선호 저장 키에 쓴다) */
  kind: string;
  /** 범위 id(세션 id·실행 id). 비면 분리를 쓸 수 없다. */
  id: string;
  /** 분리 창이 그릴 범위 인자 */
  scope: LogQueryParams;
  /** 구조도 연동이 있는가(없으면 분리를 쓸 수 없다) */
  enabled: boolean;
  channelFactory?: ChannelFactory;
  openWindow?: OpenWindow;
}

/** 원래 창 쪽 분리 준비: 채널 + 분리 창 관리. 상태 맞춤(`useArchSync`)은 구조도 컨트롤러가 생긴 뒤 같은 `sync`로 따로 건다. */
export function useArchPopoutHost(o: UseArchPopoutHostOptions): { sync: ArchSync | null; popout: ArchPopout } {
  const storage = useStorage();
  const key = `${o.kind}:${o.id}`;
  const usable = o.enabled && o.id !== "";
  const sync = useMemo(() => (usable ? createArchSync(key, o.channelFactory === undefined ? {} : { factory: o.channelFactory }) : null), [usable, key, o.channelFactory]);
  useEffect(() => () => sync?.close(), [sync]);
  const popout = useArchPopout({
    sync,
    kind: o.kind,
    storage,
    windowName: archChannelName(key),
    getUrl: () => `${ARCH_POPOUT.path}?${ARCH_POPOUT.queryKey}=${encodeURIComponent(key)}&${ARCH_POPOUT.queryScope}=${encodeURIComponent(JSON.stringify(o.scope))}`,
    ...(o.openWindow === undefined ? {} : { openWindow: o.openWindow }),
    enabled: usable,
  });
  return { sync, popout };
}
