/**
 * 원래 창 쪽 분리 창 관리: 열기·다시 합치기·열려 있는지 확인·팝업 차단 감지·분리 선호 기억.
 * `window.open`·저장소·채널·타이머는 주입한다(기본은 브라우저). 화면은 이 훅의 값만 본다.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { SafeStorage } from "../../../app/storage";
import { ARCH_POPOUT, preferKey } from "./popoutConfig";
import type { ArchSync } from "./archSync";

/** `window.open`의 반환값에서 쓰는 부분 */
export interface PopoutWindowLike {
  closed: boolean;
  focus(): void;
  close(): void;
}
export type OpenWindow = (url: string, name: string, features: string) => PopoutWindowLike | null;

export interface UseArchPopoutOptions {
  /** 동기화 채널(null이면 분리 기능을 쓸 수 없다) */
  sync: ArchSync | null;
  /** 분리 창 주소(경로 + 쿼리). 열 때마다 `getUrl()`로 최신 값을 읽는다. */
  getUrl(): string;
  /** 같은 이름이면 이미 열린 창을 다시 쓴다(채널 이름과 같게). */
  windowName: string;
  /** 범위 종류(세션·실행): 분리 선호를 종류별로 기억한다. */
  kind: string;
  storage: SafeStorage;
  openWindow?: OpenWindow;
  /** false면 아무것도 하지 않는다(구조도 연동이 없을 때) */
  enabled?: boolean;
}

export type PopoutMode = "docked" | "detached" | "pending";

export interface ArchPopout {
  /** 분리할 수 있는가(채널이 있다) */
  supported: boolean;
  /** `detached` = 분리 창이 열려 있다 / `pending` = 분리해서 보기로 기억돼 있으나 창이 없다 / `docked` = 이 화면에 붙어 있다 */
  mode: PopoutMode;
  /** 마지막 열기가 브라우저에 막혔다 */
  blocked: boolean;
  /** 분리 창을 연다(이미 있으면 앞으로 가져온다). */
  open(): void;
  /** 분리 창을 닫고 이 화면에 다시 붙인다. */
  redock(): void;
}

const defaultOpen: OpenWindow = (url, name, features) => (typeof window === "undefined" ? null : window.open(url, name, features));

/** 구조도 분리 창 상태. */
export function useArchPopout(opts: UseArchPopoutOptions): ArchPopout {
  const { sync, storage, kind } = opts;
  const enabled = opts.enabled !== false;
  const supported = enabled && sync !== null;
  const [alive, setAlive] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [prefer, setPreferState] = useState(() => storage.get(preferKey(kind)) === "1");
  const win = useRef<PopoutWindowLike | null>(null);
  const lastSeen = useRef(0);
  const latest = useRef(opts);
  useEffect(() => {
    latest.current = opts;
  });

  const setPrefer = useCallback(
    (v: boolean) => {
      setPreferState(v);
      if (v) storage.set(preferKey(kind), "1");
      else storage.remove(preferKey(kind));
    },
    [storage, kind],
  );

  // 분리 창이 닫힘(bye·창 닫힘·응답 없음) = 다시 붙는다. 선호도 풀어 다음에 빈 자리표시가 남지 않게 한다.
  const gone = useCallback(() => {
    win.current = null;
    setAlive(false);
    setPrefer(false);
  }, [setPrefer]);

  useEffect(() => {
    if (!supported || sync === null) return;
    const off = sync.subscribe((m) => {
      if (m.kind === "hello") {
        lastSeen.current = Date.now();
        setAlive(true);
        setBlocked(false);
      } else if (m.kind === "bye") gone();
    });
    sync.post({ kind: "ping" }); // 이 화면을 다시 연 경우: 이미 열린 분리 창이 있는지 묻는다
    return off;
  }, [supported, sync, gone]);

  // 열려 있는 동안: 창이 닫혔는지, 응답이 끊겼는지 확인한다.
  useEffect(() => {
    if (!alive || sync === null) return;
    const timer = setInterval(() => {
      if (win.current?.closed === true) {
        gone();
        return;
      }
      if (Date.now() - lastSeen.current > ARCH_POPOUT.closedPollMs * 3) gone();
      else sync.post({ kind: "ping" });
    }, ARCH_POPOUT.closedPollMs);
    return () => clearInterval(timer);
  }, [alive, sync, gone]);

  const open = useCallback(() => {
    if (!supported) return;
    const o = latest.current;
    if (win.current !== null && !win.current.closed) {
      win.current.focus();
      return;
    }
    const w = (o.openWindow ?? defaultOpen)(o.getUrl(), o.windowName, ARCH_POPOUT.features);
    if (w === null) {
      setBlocked(true);
      return;
    }
    win.current = w;
    lastSeen.current = Date.now();
    setBlocked(false);
    setAlive(true);
    setPrefer(true);
  }, [supported, setPrefer]);

  const redock = useCallback(() => {
    sync?.post({ kind: "close" });
    try {
      win.current?.close();
    } catch {
      /* 이미 닫힌 창 */
    }
    gone();
  }, [sync, gone]);

  const mode: PopoutMode = !supported ? "docked" : alive ? "detached" : prefer ? "pending" : "docked";
  return { supported, mode, blocked, open, redock };
}
