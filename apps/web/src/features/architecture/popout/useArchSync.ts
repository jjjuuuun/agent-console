/**
 * 구조도 상태(선택·하위 구조도·프로필)와 로그 쪽 신호(고른 이벤트·범위)를 다른 창과 맞춘다.
 * 같은 훅이 원래 창(`origin`)과 분리 창(`popout`)에서 쓰인다. 채널은 주입하므로 테스트는 가짜 채널로 돈다.
 */
import { useEffect, useRef } from "react";
import type { LogQueryParams } from "@agent-console/api-client";
import type { ArchitectureController } from "../useArchitectureController";
import type { ArchSync, ArchSyncMessage } from "./archSync";

export interface UseArchSyncOptions {
  /** null이면(채널 없음) 아무것도 하지 않는다. 참조가 안정적이어야 한다(`useMemo`). */
  sync: ArchSync | null;
  controller: ArchitectureController;
  role: "origin" | "popout";
  /** origin: 지금 고른 로그 이벤트(분리 창이 강조한다) */
  highlightUid?: string | null | undefined;
  /** origin: 구조도·표 질의에 실리는 범위(분리 창이 같은 범위로 그린다) */
  scope?: LogQueryParams | undefined;
  /** popout: origin이 고른 이벤트를 받는다 */
  onHighlight?: ((uid: string | null) => void) | undefined;
  /** popout: origin의 범위가 바뀌었다 */
  onScope?: ((scope: LogQueryParams) => void) | undefined;
  /** 그 밖의 메시지(hello·bye·close·ping)를 보고 싶을 때 */
  onMessage?: ((message: ArchSyncMessage) => void) | undefined;
}

const key = (v: unknown) => JSON.stringify(v) ?? "";

/** 창 사이 상태 동기화. 보낼 때와 받을 때 같은 값이면 다시 보내지 않아 되울림이 없다. */
export function useArchSync(opts: UseArchSyncOptions): void {
  const { sync, controller, role } = opts;
  const latest = useRef(opts);
  useEffect(() => {
    latest.current = opts;
  });
  const lastState = useRef(key(controller.syncState));
  const { applySyncState } = controller;

  // ---- 받기
  useEffect(() => {
    if (sync === null) return;
    return sync.subscribe((m) => {
      const o = latest.current;
      switch (m.kind) {
        case "state":
          lastState.current = key(m.state);
          applySyncState(m.state);
          break;
        case "highlight":
          if (role === "popout") o.onHighlight?.(m.uid);
          break;
        case "scope":
          if (role === "popout") o.onScope?.(m.scope);
          break;
        case "hello":
          // 분리 창이 열렸다: 지금 상태를 모두 보내 준다.
          if (role === "origin") {
            sync.post({ kind: "state", state: o.controller.syncState });
            sync.post({ kind: "highlight", uid: o.highlightUid ?? null });
            if (o.scope !== undefined) sync.post({ kind: "scope", scope: o.scope });
          }
          break;
        case "ping":
          if (role === "popout") sync.post({ kind: "hello" });
          break;
        case "close":
          break;
        case "bye":
          break;
      }
      o.onMessage?.(m);
    });
  }, [sync, role, applySyncState]);

  // ---- 보내기
  const stateKey = key(controller.syncState);
  useEffect(() => {
    if (sync === null || stateKey === lastState.current) return;
    lastState.current = stateKey;
    sync.post({ kind: "state", state: latest.current.controller.syncState });
  }, [sync, stateKey]);

  const highlightKey = role === "origin" ? (opts.highlightUid ?? null) : null;
  useEffect(() => {
    if (sync === null || role !== "origin") return;
    sync.post({ kind: "highlight", uid: highlightKey });
  }, [sync, role, highlightKey]);

  const scopeKey = role === "origin" ? key(opts.scope) : "";
  useEffect(() => {
    if (sync === null || role !== "origin" || latest.current.scope === undefined) return;
    sync.post({ kind: "scope", scope: latest.current.scope });
  }, [sync, role, scopeKey]);
}
