import { afterEach, describe, expect, it, vi } from "vitest";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { buildBody, resolveTarget, shouldNotify, toNotifyEvents, type NotifySettings } from "./core";
import { createNotifier } from "./notifier";
import { createBrowserNotificationPort, createWebAudioSound, type AudioContextLike, type NotificationPort, type SoundPort } from "./ports";
import { NotificationsProvider, resolveNotifySettings, type NotificationPorts } from "./NotificationsContext";
import { NotificationsEditor } from "../settings";
import { isViewingTarget, targetPath } from "./routing";
import { createFakeWs } from "../../testing/fakes";

afterEach(cleanup);

const settings = (over: Partial<NotifySettings> = {}): NotifySettings => ({ enabled: true, sound: false, events: ["x.happened"], onlyWhenHidden: true, ...over });

function fakePorts(permission: "default" | "granted" | "denied" | "unsupported" = "granted") {
  const shown: { title: string; body: string; tag?: string; onClick?: () => void }[] = [];
  const state = { permission: permission as typeof permission };
  const notification: NotificationPort = {
    permission: () => state.permission,
    insecureContext: () => false,
    requestPermission: vi.fn(async () => {
      state.permission = "granted";
      return "granted" as const;
    }),
    show: (i) => void shown.push(i),
  };
  let unlocked = false;
  const sound: SoundPort = { play: vi.fn(async () => true), unlock: vi.fn(() => void (unlocked = true)), unlocked: () => unlocked };
  return { shown, state, ports: { notification, sound } satisfies NotificationPorts };
}

describe("core", () => {
  it("이벤트 이름은 설정과 정확히 일치할 때만, 임의 이름도 동작한다", () => {
    const base = { eventName: "zzz.custom", permission: "granted" as const, hidden: true, viewing: false };
    expect(shouldNotify({ ...base, settings: settings({ events: ["zzz.custom"] }) })).toBe(true);
    expect(shouldNotify({ ...base, settings: settings({ events: ["zzz"] }) })).toBe(false);
    expect(shouldNotify({ ...base, settings: settings({ events: [] }) })).toBe(false);
  });
  it("enabled·권한·보임 여부 조건", () => {
    const base = { eventName: "x.happened", hidden: false, viewing: false };
    expect(shouldNotify({ ...base, settings: settings({ enabled: false }), permission: "granted" })).toBe(false);
    expect(shouldNotify({ ...base, settings: settings(), permission: "default" })).toBe(false);
    expect(shouldNotify({ ...base, settings: settings(), permission: "granted" })).toBe(false);
    expect(shouldNotify({ ...base, settings: settings({ onlyWhenHidden: false }), permission: "granted" })).toBe(true);
    expect(shouldNotify({ ...base, settings: settings({ onlyWhenHidden: false }), permission: "granted", viewing: true })).toBe(false);
    expect(shouldNotify({ ...base, settings: settings(), permission: "granted", hidden: true, viewing: true })).toBe(true);
  });
  it("이동 대상은 이름이 아니라 payload 필드로 정한다", () => {
    expect(resolveTarget({ interaction_id: "i", conversation_id: "c" })).toEqual({ kind: "conversation", conversationId: "c", interactionId: "i" });
    expect(resolveTarget({ interaction: { id: "i", conversation_id: "c2" } })).toMatchObject({ kind: "conversation", conversationId: "c2" });
    expect(resolveTarget({ run_id: "r" })).toEqual({ kind: "run", runId: "r" });
    expect(resolveTarget({})).toEqual({ kind: "none" });
  });
  it("문구: 템플릿 없으면 일반 형식, 값 없으면 조각 생략, 120자 말줄임", () => {
    expect(buildBody("a.b", "PL")).toBe("a.b · PL");
    expect(buildBody("a.b", undefined)).toBe("a.b");
    expect(buildBody("a.b", "PL", { "a.b": "응답 대기 · {requester}" })).toBe("응답 대기 · PL");
    expect(buildBody("a.b", undefined, { "a.b": "응답 대기 · {requester}" })).toBe("응답 대기");
    expect(Array.from(buildBody("n", "가".repeat(300))).length).toBe(120);
  });
  it("run.event는 안쪽 type, 별칭은 데이터", () => {
    const run = toNotifyEvents({ type: "run.event", payload: { type: "run.failed", run_id: "r1", ts: 5, payload: {} } });
    expect(run[0]).toMatchObject({ name: "run.failed", data: { run_id: "r1" }, ts: 5000 });
    const rule = [{ type: "m.up", when: { path: "s", equals: "pending" }, as: "m.req" }];
    expect(toNotifyEvents({ type: "m.up", payload: { s: "pending" } }, rule).map((e) => e.name)).toEqual(["m.up", "m.req"]);
    expect(toNotifyEvents({ type: "m.up", payload: { s: "done" } }, rule)).toHaveLength(1);
  });
  it("라우팅", () => {
    const routes = { conversations: "/chat", runs: "/runs" };
    expect(targetPath({ kind: "conversation", conversationId: "a b" }, routes)).toBe("/chat/a%20b");
    expect(targetPath({ kind: "none" }, routes)).toBeUndefined();
    expect(isViewingTarget("/runs/r1/x", { kind: "run", runId: "r1" }, routes)).toBe(true);
  });
});

describe("createNotifier", () => {
  const make = (over: { s?: NotifySettings; permission?: "granted" | "default"; hidden?: boolean; now?: () => number } = {}) => {
    const f = fakePorts(over.permission ?? "granted");
    const open = vi.fn();
    const n = createNotifier({
      notification: f.ports.notification,
      sound: f.ports.sound,
      settings: () => over.s ?? settings({ events: ["interaction.asked"], sound: true }),
      hidden: () => over.hidden ?? true,
      viewing: () => false,
      open,
      title: "앱",
      ...(over.now ? { now: over.now } : {}),
      lookups: () => ({ actorName: (id) => (id === "a1" ? "디자이너" : undefined) }),
    });
    return { ...f, n, open };
  };
  const msg = (extra: Record<string, unknown> = {}) => ({ type: "run.event", payload: { type: "interaction.asked", run_id: "r1", actor: "a1", payload: { interaction: { id: "i1", conversation_id: "c1", node_label: "노드" } }, ...extra } });

  it("조건이 맞으면 알림·소리, 클릭 시 대화로 이동", () => {
    const { n, shown, ports, open } = make();
    expect(n.handle(msg())).toBe(true);
    expect(shown[0]).toMatchObject({ title: "앱", body: "interaction.asked · 디자이너", tag: "c:c1|interaction.asked" });
    expect(ports.sound.play).toHaveBeenCalledTimes(1);
    shown[0]?.onClick?.();
    expect(open).toHaveBeenCalledWith({ kind: "conversation", conversationId: "c1", interactionId: "i1" });
  });
  it("보이는 탭·권한 없음·목록 밖 이벤트는 알리지 않고 소리도 없다", () => {
    expect(make({ hidden: false }).n.handle(msg())).toBe(false);
    expect(make({ permission: "default" }).n.handle(msg())).toBe(false);
    const c = make();
    expect(c.n.handle({ type: "run.event", payload: { type: "other.event", run_id: "r" } })).toBe(false);
    expect(c.shown).toHaveLength(0);
    expect(c.ports.sound.play).not.toHaveBeenCalled();
  });
  it("1초 안 같은 tag는 하나로", () => {
    let t = 1000;
    const { n, shown } = make({ now: () => t });
    n.handle(msg());
    t += 500;
    n.handle(msg());
    t += 600;
    n.handle(msg());
    expect(shown).toHaveLength(2);
  });
  it("시작 전에 만들어진 이벤트(재접속 스냅샷)는 무시", () => {
    const { n, shown } = make({ now: () => 1_000_000 });
    n.handle(msg({ ts: 1 }));
    expect(shown).toHaveLength(0);
  });
});

describe("브라우저 어댑터", () => {
  it("Notification이 없거나 비보안 컨텍스트면 unsupported", async () => {
    expect(createBrowserNotificationPort({}).permission()).toBe("unsupported");
    const P = createBrowserNotificationPort({ Notification: { permission: "granted", requestPermission: async () => "granted" } as never, isSecureContext: false });
    expect(P.permission()).toBe("unsupported");
    expect(P.insecureContext()).toBe(true);
    expect(await P.requestPermission()).toBe("unsupported");
  });
  it("show는 생성 예외를 삼키고 클릭 시 focus·onClick", () => {
    const focus = vi.fn();
    const onClick = vi.fn();
    const made: { onclick: (() => void) | null; close: () => void }[] = [];
    class N {
      static permission = "granted";
      static requestPermission = async () => "granted";
      onclick: (() => void) | null = null;
      close = vi.fn();
      constructor() {
        made.push(this);
      }
    }
    createBrowserNotificationPort({ Notification: N as never, focus }).show({ title: "t", body: "b", onClick });
    made[0]?.onclick?.();
    expect(focus).toHaveBeenCalled();
    expect(onClick).toHaveBeenCalled();
    class Bad {
      static permission = "granted";
      static requestPermission = async () => "granted";
      constructor() {
        throw new Error("x");
      }
    }
    expect(() => createBrowserNotificationPort({ Notification: Bad as never }).show({ title: "t", body: "b" })).not.toThrow();
  });
  it("WebAudio: 두 음, 컨텍스트는 사용 전에 만들지 않고 막히면 false", async () => {
    const oscs: number[] = [];
    const ctx: AudioContextLike = {
      currentTime: 0,
      state: "running",
      destination: {},
      resume: async () => undefined,
      createGain: () => ({ gain: { setValueAtTime: () => 0, linearRampToValueAtTime: () => 0 }, connect: () => 0 }),
      createOscillator: () => ({ type: "", frequency: { setValueAtTime: (v: number) => void oscs.push(v) }, connect: () => 0, start: () => 0, stop: () => 0 }),
    };
    const create = vi.fn(() => ctx);
    const s = createWebAudioSound(create);
    expect(create).not.toHaveBeenCalled();
    expect(await s.play()).toBe(true);
    expect(oscs).toEqual([880, 660]);
    expect(await createWebAudioSound(() => ({ ...ctx, state: "suspended" })).play()).toBe(false);
    expect(await createWebAudioSound(() => undefined).play()).toBe(false);
  });
});

describe("resolveNotifySettings", () => {
  it("빈 값은 스키마 기본값", () => {
    expect(resolveNotifySettings(undefined)).toEqual({ enabled: false, sound: false, events: ["interaction.requested"], onlyWhenHidden: true });
    expect(resolveNotifySettings({ events: [], only_when_hidden: false })).toMatchObject({ events: [], onlyWhenHidden: false });
  });
});

function wrap(ui: React.ReactNode, ports = fakePorts(), notif: Record<string, unknown> = { enabled: true, events: ["interaction.requested"] }) {
  const ws = createFakeWs();
  const navigate = vi.fn();
  const handlers: ((m: unknown) => void)[] = [];
  (ws as unknown as { onMessage: unknown }).onMessage = (h: (m: unknown) => void) => {
    handlers.push(h);
    return () => undefined;
  };
  const view = render(
    <QueryClientProvider client={new QueryClient()}>
      <NotificationsProvider ws={ws} settings={notif} ports={ports.ports} pathname="/x" navigate={navigate} pathFor={(t) => (t.kind === "conversation" ? `/chat/${t.conversationId}` : undefined)} isViewing={() => false}>
        {ui}
      </NotificationsProvider>
    </QueryClientProvider>,
  );
  return { ...view, handlers, ports, navigate };
}

describe("NotificationsProvider", () => {
  it("메시지를 받아 알림을 내고 클릭하면 이동한다(기본 별칭: 대기 상태 메시지)", () => {
    const f = fakePorts();
    const { handlers, navigate } = wrap(null, f);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    act(() => handlers[0]?.({ type: "interaction.updated", payload: { interaction: { id: "i", status: "pending", conversation_id: "c9", run_id: "r", created_at: Date.now() / 1000, kind: "k", node_id: "n" } } }));
    expect(f.shown).toHaveLength(1);
    f.shown[0]?.onClick?.();
    expect(navigate).toHaveBeenCalledWith("/chat/c9");
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });
});

describe("NotificationsEditor", () => {
  function editor(permission: "default" | "granted" | "denied" | "unsupported", value: Record<string, unknown> | undefined) {
    const f = fakePorts(permission);
    const onChange = vi.fn();
    const r = wrap(<NotificationsEditor value={value} onChange={onChange} />, f);
    return { ...r, f, onChange };
  }
  it("렌더만으로 권한을 요청하지 않고, 버튼 클릭에서만 요청한다", async () => {
    const { f } = editor("default", undefined);
    expect(f.ports.notification.requestPermission).not.toHaveBeenCalled();
    expect(screen.getByText("아직 허용하지 않았습니다")).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "브라우저 알림 허용 요청" })));
    expect(f.ports.notification.requestPermission).toHaveBeenCalledTimes(1);
    expect(screen.getByText("허용됨")).toBeTruthy();
    expect(screen.getByRole("button", { name: "테스트 알림 보내기" })).toBeTruthy();
  });
  it("차단·미지원 상태에는 요청 버튼이 없다", () => {
    const a = editor("denied", undefined);
    expect(screen.queryByRole("button", { name: "브라우저 알림 허용 요청" })).toBeNull();
    expect(screen.getByText(/사이트 설정/)).toBeTruthy();
    a.unmount();
    editor("unsupported", undefined);
    expect(screen.getByText(/이 브라우저\/주소에서는 알림을 쓸 수 없습니다/)).toBeTruthy();
  });
  it("테스트 알림은 초안의 sound 값 기준으로 클릭에서만", () => {
    const { f } = editor("granted", { sound: true });
    expect(f.shown).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "테스트 알림 보내기" }));
    expect(f.shown[0]?.body).toBe("테스트 알림입니다");
    expect(f.ports.sound.play).toHaveBeenCalled();
  });
  it("이벤트 이름 추가는 데이터로 onChange, 빈 목록 안내", () => {
    const { onChange } = editor("granted", { events: [] });
    // 기본값이 있는 선택 항목은 고급 영역(접힘)에 있다
    const advanced = screen.queryByRole("button", { name: /고급 설정/ });
    if (advanced && advanced.getAttribute("aria-expanded") === "false") fireEvent.click(advanced);
    expect(screen.getByText("비어 있으면 알림을 보내지 않습니다")).toBeTruthy();
    const input = screen.getByRole("combobox", { name: "이벤트 이름 추가" });
    fireEvent.change(input, { target: { value: "custom.thing" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ events: ["custom.thing"] }));
  });
  it("소리만 켜면 sound만 저장하고 나머지는 생략(상속)", () => {
    const { onChange } = editor("granted", undefined);
    fireEvent.click(screen.getByRole("checkbox", { name: /소리/ }));
    expect(onChange).toHaveBeenLastCalledWith({ sound: true });
  });
  it("수신한 이벤트 이름이 제안 목록에 나온다", () => {
    const { handlers, container } = editor("granted", undefined);
    act(() => handlers[0]?.({ type: "run.event", payload: { type: "seen.once", run_id: "r", ts: 1, payload: {} } }));
    expect(container.querySelector("datalist option[value='seen.once']")).not.toBeNull();
  });
});
