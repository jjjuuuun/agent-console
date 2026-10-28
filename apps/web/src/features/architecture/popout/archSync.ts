/**
 * 구조도 창 사이 동기화 채널(BroadcastChannel 얇은 래퍼). 화면·React를 모른다.
 * 채널 이름은 범위 키(세션 id·실행 id)로 정한다: 같은 범위를 보는 창끼리만 주고받는다.
 * `BroadcastChannel`이 없으면 `createArchSync`가 null을 돌려주고, 호출하는 쪽은 분리 기능만 끈다.
 */
import type { LogQueryParams } from "@agent-console/api-client";
import type { ArchitectureSyncState } from "../useArchitectureController";
import { ARCH_POPOUT } from "./popoutConfig";

/** 창이 주고받는 메시지. `from`은 보낸 쪽 id(자기가 보낸 것은 무시한다). */
export type ArchSyncMessage =
  | { kind: "state"; from: string; state: ArchitectureSyncState }
  /** 원래 창에서 고른 로그 행(uid). 분리 창이 그 이벤트가 맞은 칸을 강조한다. */
  | { kind: "highlight"; from: string; uid: string | null }
  /** 원래 창의 범위 인자(레인 필터 등)가 바뀜. */
  | { kind: "scope"; from: string; scope: LogQueryParams }
  /** 원래 창이 분리 창이 있는지 묻는다. */
  | { kind: "ping"; from: string }
  /** 분리 창이 열려 있다(ping 답, 또는 막 열렸다). */
  | { kind: "hello"; from: string }
  /** 분리 창이 닫힌다. */
  | { kind: "bye"; from: string }
  /** 원래 창이 분리 창에 닫으라고 한다([다시 합치기]). */
  | { kind: "close"; from: string };

/** `BroadcastChannel`과 같은 모양(주입·테스트용). */
export interface ChannelLike {
  postMessage(message: unknown): void;
  /** 받은 메시지 처리기(`BroadcastChannel.onmessage`와 같다). 하나만 걸 수 있어 구독 목록은 `createArchSync`가 관리한다. */
  onmessage: ((event: { data: unknown }) => void) | null;
  close(): void;
}
/** 채널 만드는 함수. 지원하지 않으면 null. */
export type ChannelFactory = (name: string) => ChannelLike | null;

/** 브라우저 `BroadcastChannel`. 없거나 만들 수 없으면 null. */
export const browserChannelFactory: ChannelFactory = (name) => {
  try {
    return typeof BroadcastChannel === "undefined" ? null : (new BroadcastChannel(name) as unknown as ChannelLike);
  } catch {
    return null;
  }
};

export interface ArchSync {
  /** 이 창의 id */
  id: string;
  post(message: DistributiveOmit<ArchSyncMessage, "from">): void;
  /** 다른 창의 메시지를 받는다. 해제 함수를 돌려준다. */
  subscribe(listener: (message: ArchSyncMessage) => void): () => void;
  close(): void;
}
type DistributiveOmit<T, K extends keyof never> = T extends unknown ? Omit<T, K> : never;

/** 범위 키 → 채널 이름. 범위 키는 `session:<id>`·`run:<id>`처럼 호출하는 쪽이 정한다. */
export const archChannelName = (key: string): string => `${ARCH_POPOUT.channelPrefix}${key}`;

/** 분리 기능을 쓸 수 있는가(채널을 만들 수 있는가). */
export function isArchSyncSupported(factory: ChannelFactory = browserChannelFactory): boolean {
  const probe = factory(archChannelName("probe"));
  probe?.close();
  return probe !== null;
}

const isMessage = (v: unknown): v is ArchSyncMessage => typeof v === "object" && v !== null && typeof (v as { kind?: unknown }).kind === "string" && typeof (v as { from?: unknown }).from === "string";

/** 동기화 채널. 지원하지 않으면 null. */
export function createArchSync(key: string, opts: { factory?: ChannelFactory; id?: string } = {}): ArchSync | null {
  const channel = (opts.factory ?? browserChannelFactory)(archChannelName(key));
  if (channel === null) return null;
  const id = opts.id ?? `w${Math.random().toString(36).slice(2, 10)}`;
  const listeners = new Set<(message: ArchSyncMessage) => void>();
  channel.onmessage = (e) => {
    if (isMessage(e.data) && e.data.from !== id) for (const l of [...listeners]) l(e.data);
  };
  return {
    id,
    post(message) {
      try {
        channel.postMessage({ ...message, from: id });
      } catch {
        /* 직렬화·닫힌 채널 오류는 무시한다(동기화만 끊긴다) */
      }
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    close() {
      listeners.clear();
      channel.onmessage = null;
      channel.close();
    },
  };
}
