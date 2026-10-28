import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { createSafeStorage } from "../../../app/storage";
import type { ArchitectureController, ArchitectureSyncState } from "../useArchitectureController";
import { archChannelName, createArchSync, isArchSyncSupported, type ChannelFactory, type ChannelLike } from "./archSync";
import { ARCH_POPOUT, preferKey } from "./popoutConfig";
import { useArchPopout, type PopoutWindowLike } from "./useArchPopout";
import { useArchSync } from "./useArchSync";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

/** 같은 이름의 다른 채널 인스턴스에만 전달하는 가짜 BroadcastChannel(실제 동작과 같다). */
function hub() {
  type Peer = { ch: ChannelLike };
  const open = new Map<string, Set<Peer>>();
  const factory: ChannelFactory = (name) => {
    const set = open.get(name) ?? new Set<Peer>();
    open.set(name, set);
    const me: Peer = { ch: undefined as unknown as ChannelLike };
    me.ch = {
      onmessage: null,
      postMessage: (data) => set.forEach((o) => o !== me && o.ch.onmessage?.({ data: JSON.parse(JSON.stringify(data)) })),
      close: () => void set.delete(me),
    };
    set.add(me);
    return me.ch;
  };
  return { factory, names: () => [...open.keys()] };
}
const memory = () => {
  const m = new Map<string, string>();
  return createSafeStorage({ getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) } as unknown as Storage);
};

describe("archSync 채널", () => {
  it("채널 이름은 범위 키로 정해지고 같은 범위의 창끼리만 주고받는다", () => {
    const h = hub();
    const a = createArchSync("session:s1", { factory: h.factory, id: "a" })!;
    const b = createArchSync("session:s1", { factory: h.factory, id: "b" })!;
    const other = createArchSync("session:s2", { factory: h.factory, id: "c" })!;
    const got: string[] = [];
    const otherGot: string[] = [];
    const selfGot: string[] = [];
    b.subscribe((m) => got.push(m.kind));
    other.subscribe((m) => otherGot.push(m.kind));
    a.subscribe((m) => selfGot.push(m.kind));
    a.post({ kind: "highlight", uid: "u1" });
    expect(got).toEqual(["highlight"]);
    expect(otherGot).toEqual([]);
    expect(selfGot).toEqual([]);
    expect(h.names()).toContain(archChannelName("session:s1"));
  });
  it("BroadcastChannel이 없으면 null이고 지원하지 않는다고 답한다", () => {
    expect(createArchSync("run:r", { factory: () => null })).toBeNull();
    expect(isArchSyncSupported(() => null)).toBe(false);
    expect(isArchSyncSupported(hub().factory)).toBe(true);
  });
  it("형식이 다른 메시지는 무시한다", () => {
    const h = hub();
    const a = createArchSync("k", { factory: h.factory, id: "a" })!;
    const raw = h.factory(archChannelName("k"))!;
    const got: unknown[] = [];
    a.subscribe((m) => got.push(m));
    raw.postMessage("뭔가");
    raw.postMessage({ kind: 3 });
    expect(got).toEqual([]);
  });
});

const fakeWindow = () => ({ closed: false, focus: vi.fn(), close: vi.fn() });

describe("useArchPopout", () => {
  const setup = (over: { openWindow?: () => PopoutWindowLike | null; factory?: ChannelFactory; storage?: ReturnType<typeof memory> } = {}) => {
    const h = hub();
    const storage = over.storage ?? memory();
    const sync = createArchSync("run:r1", { factory: over.factory ?? h.factory, id: "origin" });
    const peer = createArchSync("run:r1", { factory: h.factory, id: "peer" })!;
    const openWindow = vi.fn(over.openWindow ?? (() => fakeWindow()));
    const hook = renderHook(() => useArchPopout({ sync, kind: "run", storage, windowName: "w", getUrl: () => "/popout/architecture?key=run%3Ar1", openWindow }));
    return { hook, peer, openWindow, storage, sync };
  };

  it("기본은 붙어 있고, 열면 주소·창 이름·모양으로 window.open을 부르고 분리 상태가 된다", () => {
    const { hook, openWindow, storage } = setup();
    expect(hook.result.current.mode).toBe("docked");
    expect(hook.result.current.supported).toBe(true);
    act(() => hook.result.current.open());
    expect(openWindow).toHaveBeenCalledWith("/popout/architecture?key=run%3Ar1", "w", ARCH_POPOUT.features);
    expect(hook.result.current.mode).toBe("detached");
    expect(storage.get(preferKey("run"))).toBe("1"); // 분리를 기억한다
  });
  it("팝업이 막히면(null) 분리하지 않고 안내 상태가 된다", () => {
    const { hook } = setup({ openWindow: () => null });
    act(() => hook.result.current.open());
    expect(hook.result.current.mode).toBe("docked");
    expect(hook.result.current.blocked).toBe(true);
  });
  it("분리 창이 bye를 보내면 다시 붙고 기억도 지운다", () => {
    const { hook, peer, storage } = setup();
    act(() => hook.result.current.open());
    act(() => peer.post({ kind: "bye" }));
    expect(hook.result.current.mode).toBe("docked");
    expect(storage.get(preferKey("run"))).toBeNull();
  });
  it("[다시 합치기]는 분리 창에 닫으라고 알리고 창도 닫는다", () => {
    const w = fakeWindow();
    const { hook, peer } = setup({ openWindow: () => w });
    const got: string[] = [];
    peer.subscribe((m) => got.push(m.kind));
    act(() => hook.result.current.open());
    act(() => hook.result.current.redock());
    expect(got).toContain("close");
    expect(w.close).toHaveBeenCalled();
    expect(hook.result.current.mode).toBe("docked");
  });
  it("이미 열려 있으면 다시 열지 않고 앞으로 가져온다", () => {
    const w = fakeWindow();
    const { hook, openWindow } = setup({ openWindow: () => w });
    act(() => hook.result.current.open());
    act(() => hook.result.current.open());
    expect(openWindow).toHaveBeenCalledTimes(1);
    expect(w.focus).toHaveBeenCalled();
  });
  it("창이 bye 없이 닫혀도 점검으로 알아채고 다시 붙는다", () => {
    vi.useFakeTimers();
    const w = fakeWindow();
    const { hook } = setup({ openWindow: () => w });
    act(() => hook.result.current.open());
    w.closed = true;
    act(() => void vi.advanceTimersByTime(ARCH_POPOUT.closedPollMs + 10));
    expect(hook.result.current.mode).toBe("docked");
  });
  it("이 화면을 다시 열었을 때 이미 열린 분리 창이 hello로 답하면 분리 상태가 된다", () => {
    const h = hub();
    const peer = createArchSync("run:r1", { factory: h.factory, id: "peer" })!;
    peer.subscribe((m) => m.kind === "ping" && peer.post({ kind: "hello" })); // 분리 창은 ping에 hello로 답한다
    const sync = createArchSync("run:r1", { factory: h.factory, id: "origin" });
    const hook = renderHook(() => useArchPopout({ sync, kind: "run", storage: memory(), windowName: "w", getUrl: () => "/x" }));
    expect(hook.result.current.mode).toBe("detached");
  });
  it("분리 선호가 기억돼 있으면 창이 없을 때 pending(자리 안내)이다", () => {
    const storage = memory();
    storage.set(preferKey("run"), "1");
    const { hook } = setup({ storage });
    expect(hook.result.current.mode).toBe("pending");
  });
  it("채널이 없으면 분리 기능만 꺼진다", () => {
    const hook = renderHook(() => useArchPopout({ sync: null, kind: "run", storage: memory(), windowName: "w", getUrl: () => "/x" }));
    expect(hook.result.current.supported).toBe(false);
    expect(hook.result.current.mode).toBe("docked");
    act(() => hook.result.current.open()); // 아무 일도 없다
  });
});

describe("useArchSync", () => {
  const controller = (state: ArchitectureSyncState) => ({ syncState: state, applySyncState: vi.fn() }) as unknown as ArchitectureController;
  const s0: ArchitectureSyncState = { selection: null, drill: [], profile: undefined };
  const s1: ArchitectureSyncState = { selection: { kind: "cell", id: "llm" }, drill: [], profile: "p" };

  it("분리 창에서 칸을 고르면 원래 창 컨트롤러가 그 상태를 받는다(되울림 없음)", () => {
    const h = hub();
    const hostSync = createArchSync("session:s", { factory: h.factory, id: "origin" });
    const popSync = createArchSync("session:s", { factory: h.factory, id: "pop" });
    const host = controller(s0);
    const pop = renderHook(({ c }) => useArchSync({ sync: popSync, controller: c, role: "popout" }), { initialProps: { c: controller(s0) } });
    renderHook(() => useArchSync({ sync: hostSync, controller: host, role: "origin", highlightUid: null }));
    const posts = vi.spyOn(hostSync!, "post");
    pop.rerender({ c: controller(s1) }); // 분리 창에서 선택
    expect(host.applySyncState).toHaveBeenCalledWith(s1);
    expect(posts).not.toHaveBeenCalledWith(expect.objectContaining({ kind: "state" }));
  });
  it("원래 창에서 고른 로그 행(uid)과 범위가 분리 창에 전달된다", () => {
    const h = hub();
    const hostSync = createArchSync("session:s", { factory: h.factory, id: "origin" });
    const popSync = createArchSync("session:s", { factory: h.factory, id: "pop" });
    const onHighlight = vi.fn();
    const onScope = vi.fn();
    renderHook(() => useArchSync({ sync: popSync, controller: controller(s0), role: "popout", onHighlight, onScope }));
    const host = renderHook(({ uid, scope }) => useArchSync({ sync: hostSync, controller: controller(s0), role: "origin", highlightUid: uid, scope }), { initialProps: { uid: null as string | null, scope: { session: "s" } } });
    onHighlight.mockClear();
    host.rerender({ uid: "u7", scope: { session: "s" } });
    expect(onHighlight).toHaveBeenLastCalledWith("u7");
    host.rerender({ uid: "u7", scope: { session: "s", thread: "a" } as never });
    expect(onScope).toHaveBeenLastCalledWith({ session: "s", thread: "a" });
  });
  it("분리 창이 열려 hello를 보내면 원래 창이 지금 상태를 모두 보내 준다", () => {
    const h = hub();
    const hostSync = createArchSync("run:r", { factory: h.factory, id: "origin" });
    const popSync = createArchSync("run:r", { factory: h.factory, id: "pop" })!;
    renderHook(() => useArchSync({ sync: hostSync, controller: controller(s1), role: "origin", highlightUid: "u1", scope: { scope: "run:r" } }));
    const got: string[] = [];
    popSync.subscribe((m) => got.push(m.kind));
    popSync.post({ kind: "hello" });
    expect(got).toEqual(expect.arrayContaining(["state", "highlight", "scope"]));
  });
  it("채널이 없으면 아무 일도 하지 않는다", () => {
    const c = controller(s0);
    renderHook(() => useArchSync({ sync: null, controller: c, role: "origin" }));
    expect(c.applySyncState).not.toHaveBeenCalled();
  });
});
