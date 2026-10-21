import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Versioned } from "@agent-console/api-client";
import type { WorkspaceSettings } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { queryKeys } from "../../app/queries";
import { INDICATOR_REFRESH_GAP_MS } from "./usageConfig";
import { canRefreshNow } from "./usageLib";

export interface IndicatorActionsOptions {
  /** 마지막 조회 시각(ms). 수동 새로 고침 연타 판단에 같이 쓴다 */
  lastFetchedAt: number;
  /** 지금(ms). 테스트 주입용, 기본 `Date.now` */
  now?: () => number;
  gapMs?: number;
}

/**
 * 표시기 메뉴의 데이터 동작(컨테이너용 훅).
 * - `refresh()`: 사용량 조회(`["usage"]`)를 무효화한다. 마지막 조회·새로 고침이 `gapMs`(기본 `INDICATOR_REFRESH_GAP_MS`) 안이면 하지 않고 false.
 * - `hide()`: 설정 `ui.usage_indicator.enabled=false`를 저장한다(다른 키는 그대로, `If-Match` 사용). 실패하면 throw.
 */
export function useIndicatorActions({ lastFetchedAt, now = Date.now, gapMs = INDICATOR_REFRESH_GAP_MS }: IndicatorActionsOptions) {
  const queryClient = useQueryClient();
  const { rest } = useApi();
  const lastManual = useRef(0);
  const refresh = useCallback((): boolean => {
    const t = now();
    if (!canRefreshNow(t, Math.max(lastManual.current, lastFetchedAt), gapMs)) return false;
    lastManual.current = t;
    void queryClient.invalidateQueries({ queryKey: ["usage"] });
    return true;
  }, [queryClient, lastFetchedAt, now, gapMs]);
  const hide = useCallback(async (): Promise<void> => {
    const current = await rest.getSettingsVersioned();
    const value: WorkspaceSettings = current.value;
    const next: WorkspaceSettings = { ...value, ui: { ...(value.ui ?? {}), usage_indicator: { ...(value.ui?.usage_indicator ?? {}), enabled: false } } };
    const saved: Versioned<WorkspaceSettings> = await rest.putSettingsVersioned(next, current.version_hash);
    queryClient.setQueryData(queryKeys.settings(), saved);
  }, [rest, queryClient]);
  return { refresh, hide };
}
