import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectionStatus, WsClient } from "@agent-console/api-client";
import { useConnectionStatus } from "./useConnectionStatus";

/** 띠 타이밍·횟수(데이터). 값은 ux-overhaul §15.3 명세 A. */
export const CONNECTION_BANNER_TIMING = {
  /** 연결된 적 있는 뒤 `reconnecting`이 이어질 때 띠를 띄우기까지 */
  graceMs: 2500,
  /** 첫 접속이 이어질 때 띠를 띄우기까지 */
  firstMs: 8000,
  /** 복구 문구 노출 시간 */
  recoveredMs: 2000,
  /** 이 횟수만큼 `closed`가 되면 [새로고침]도 보인다 */
  reloadAfterClosed: 2,
} as const;

export type ConnectionBannerKind = "connecting" | "reconnecting" | "closed" | "closedAgain" | "retrying" | "recovered";
export interface ConnectionBannerView {
  kind: ConnectionBannerKind;
  tone: "warning" | "danger" | "success";
  canRetry: boolean;
  canReload: boolean;
  retryBusy: boolean;
}

export interface ConnectionBannerState {
  /** null이면 아무것도 그리지 않는다 */
  view: ConnectionBannerView | null;
  retry(): void;
  reload(): void;
}

export interface ConnectionBannerOptions {
  timing?: typeof CONNECTION_BANNER_TIMING;
  onReload?: () => void;
}

/**
 * 연결 상태 → 띠 표시 상태. `open`·`idle`은 숨김, 문제는 유예 뒤에만, `closed`는 즉시.
 * `open`이 아닌 상태가 이어지는 동안 유예 타이머는 하나다.
 */
export function useConnectionBanner(ws: WsClient, options: ConnectionBannerOptions = {}): ConnectionBannerState {
  const timing = options.timing ?? CONNECTION_BANNER_TIMING;
  const status = useConnectionStatus(ws);
  const [waited, setWaited] = useState(false); // 유예가 지났다
  const [recovered, setRecovered] = useState(false);
  const [closedCount, setClosedCount] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const everOpen = useRef(false);
  const shown = useRef(false);
  const prev = useRef<ConnectionStatus>(status);

  // 상태 전환 기록: closed 횟수, open 복구, 재시도 표시
  useEffect(() => {
    const before = prev.current;
    prev.current = status;
    if (status === "closed" && before !== "closed") setClosedCount((n) => n + 1);
    if (status === "closed") setRetrying(false);
    if (status !== "open") {
      setRecovered(false);
      return undefined;
    }
    everOpen.current = true;
    setClosedCount(0);
    setRetrying(false);
    if (!shown.current) return undefined;
    shown.current = false;
    setRecovered(true);
    const t = setTimeout(() => setRecovered(false), timing.recoveredMs);
    return () => clearTimeout(t);
  }, [status, timing.recoveredMs]);

  // 유예 타이머: open이 아닌 상태가 이어지는 동안 하나(connecting<->reconnecting 전환으로 다시 시작하지 않는다)
  const trouble = status === "connecting" || status === "reconnecting";
  useEffect(() => {
    if (!trouble) {
      setWaited(false);
      return undefined;
    }
    const t = setTimeout(() => setWaited(true), everOpen.current ? timing.graceMs : timing.firstMs);
    return () => clearTimeout(t);
  }, [trouble, timing.graceMs, timing.firstMs]);

  const retry = useCallback(() => {
    setRetrying(true);
    ws.connect();
  }, [ws]);
  const reload = useCallback(() => (options.onReload ?? (() => window.location.reload()))(), [options.onReload]);

  let view: ConnectionBannerView | null = null;
  if (status === "closed") {
    const again = closedCount >= timing.reloadAfterClosed;
    view = { kind: again ? "closedAgain" : "closed", tone: "danger", canRetry: true, canReload: again, retryBusy: false };
  } else if (status === "open") {
    if (recovered) view = { kind: "recovered", tone: "success", canRetry: false, canReload: false, retryBusy: false };
  } else if (status === "connecting" || status === "reconnecting") {
    if (retrying) view = { kind: "retrying", tone: "danger", canRetry: true, canReload: closedCount >= timing.reloadAfterClosed, retryBusy: true };
    else if (waited) view = { kind: status, tone: "warning", canRetry: false, canReload: false, retryBusy: false };
  }
  if (view !== null && view.kind !== "recovered") shown.current = true;
  return { view, retry, reload };
}
