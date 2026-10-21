import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getDefaultValue, type JsonSchema } from "@agent-console/schema-form";
import { getContractSchema, type Agent, type NotificationSettings } from "@agent-console/contracts";
import type { WsClient } from "@agent-console/api-client";
import { messages as m } from "../../app/messages";
import { DEFAULT_EVENT_ALIASES, OBSERVED_NAMES_MAX } from "./config";
import { toNotifyEvents, type EventAlias, type NotifySettings, type NotifyTarget, type PermissionState } from "./core";
import { createNotifier } from "./notifier";
import { createBrowserNotificationPort, createWebAudioSound, type AudioContextLike, type NotificationCtorLike, type NotificationPort, type SoundPort } from "./ports";

/** 서버 스키마 기본값으로 빈 곳을 채운 알림 설정. 코드에 기본값이 없다. */
export function resolveNotifySettings(raw: NotificationSettings | null | undefined): NotifySettings {
  const defaults = getDefaultValue(getContractSchema("NotificationSettings") as JsonSchema) as NotificationSettings;
  const merged = { ...defaults, ...(raw ?? {}) };
  return { enabled: merged.enabled === true, sound: merged.sound === true, events: merged.events ?? [], onlyWhenHidden: merged.only_when_hidden !== false };
}

export interface NotificationPorts {
  notification: NotificationPort;
  sound: SoundPort;
}

/** 실제 브라우저 전역으로 포트를 만든다(앱 부팅에서만 부른다). */
export function createBrowserPorts(win: Window & typeof globalThis = window): NotificationPorts {
  const Ctor = (win as unknown as { AudioContext?: new () => AudioContextLike; webkitAudioContext?: new () => AudioContextLike }).AudioContext ?? (win as unknown as { webkitAudioContext?: new () => AudioContextLike }).webkitAudioContext;
  return {
    notification: createBrowserNotificationPort({ Notification: (win as unknown as { Notification?: NotificationCtorLike }).Notification, isSecureContext: win.isSecureContext, focus: () => win.focus() }),
    sound: createWebAudioSound(() => (Ctor === undefined ? undefined : new Ctor())),
  };
}

export interface NotificationsApi {
  permission: PermissionState;
  insecureContext: boolean;
  /** 클릭 핸들러에서만 부른다 */
  requestPermission(): Promise<PermissionState>;
  /** 초안 설정으로 테스트 알림(클릭 전용) */
  sendTest(draft: Pick<NotifySettings, "sound">): void;
  playSound(): Promise<boolean>;
  soundUnlocked: boolean;
  /** 이 세션에서 실제로 받은 이벤트 이름(최근 종류, 제안 목록 원천) */
  observedEvents: readonly string[];
}

const UNSUPPORTED: NotificationsApi = {
  permission: "unsupported",
  insecureContext: false,
  requestPermission: async () => "unsupported",
  sendTest: () => undefined,
  playSound: async () => false,
  soundUnlocked: false,
  observedEvents: [],
};

const Ctx = createContext<NotificationsApi>(UNSUPPORTED);
export const useNotifications = (): NotificationsApi => useContext(Ctx);

export interface NotificationsProviderProps {
  ws: WsClient;
  /** 저장된 `ui.notifications` */
  settings: NotificationSettings | null | undefined;
  ports: NotificationPorts;
  /** 이동: 대상 -> 앱 경로(없으면 이동 안 함) */
  pathFor: (target: NotifyTarget) => string | undefined;
  /** 현재 경로가 이 대상 화면인가 */
  isViewing: (pathname: string, target: NotifyTarget) => boolean;
  pathname: string;
  navigate: (path: string) => void;
  aliases?: readonly EventAlias[];
  children: ReactNode;
}

/**
 * WS 메시지를 받아 설정의 `events`에 맞으면 브라우저 알림·소리를 낸다. 권한 요청은 `requestPermission`(클릭)에서만.
 * 라우터·API를 모르며 이동/경로 판정은 props로 받는다.
 */
export function NotificationsProvider({ ws, settings, ports, pathFor, isViewing, pathname, navigate, aliases = DEFAULT_EVENT_ALIASES, children }: NotificationsProviderProps) {
  const queryClient = useQueryClient();
  const [permission, setPermission] = useState<PermissionState>(() => ports.notification.permission());
  const [observed, setObserved] = useState<readonly string[]>([]);
  const [soundUnlocked, setSoundUnlocked] = useState(() => ports.sound.unlocked());
  const resolved = useMemo(() => resolveNotifySettings(settings), [settings]);
  const live = useRef({ resolved, pathname, navigate, pathFor, isViewing });
  useEffect(() => {
    live.current = { resolved, pathname, navigate, pathFor, isViewing };
  });

  const refresh = useCallback(() => setPermission(ports.notification.permission()), [ports]);
  // 탭으로 돌아오면 권한을 다시 읽는다(permissionchange가 없는 브라우저 대비)
  useEffect(() => {
    const onVisible = () => refresh();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [refresh]);
  // 첫 사용자 제스처에서 오디오를 연다
  useEffect(() => {
    const unlock = () => {
      ports.sound.unlock();
      setSoundUnlocked(ports.sound.unlocked());
    };
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, [ports]);

  useEffect(() => {
    const notifier = createNotifier({
      notification: ports.notification,
      sound: ports.sound,
      settings: () => live.current.resolved,
      hidden: () => document.visibilityState === "hidden",
      viewing: (target) => live.current.isViewing(live.current.pathname, target),
      open: (target) => {
        const path = live.current.pathFor(target);
        if (path !== undefined) live.current.navigate(path);
      },
      title: m.notifications.title,
      templates: m.notifications.templates,
      aliases,
      lookups: () => {
        const agents = queryClient.getQueryData<Agent[]>(["list", "agents"]);
        return { actorName: (id: string) => agents?.find((a) => a.id === id)?.name };
      },
    });
    return ws.onMessage((message) => {
      const names = toNotifyEvents(message, aliases).map((e) => e.name);
      setObserved((cur) => {
        const fresh = names.filter((n) => !cur.includes(n));
        return fresh.length === 0 ? cur : [...cur, ...fresh].slice(-OBSERVED_NAMES_MAX);
      });
      notifier.handle(message);
    });
  }, [ws, ports, aliases, queryClient]);

  const api = useMemo<NotificationsApi>(
    () => ({
      permission,
      insecureContext: ports.notification.insecureContext(),
      async requestPermission() {
        const next = await ports.notification.requestPermission();
        setPermission(next);
        return next;
      },
      sendTest(draft) {
        ports.notification.show({ title: m.notifications.test.title, body: m.notifications.test.body, tag: "test" });
        if (draft.sound) void ports.sound.play().then(() => setSoundUnlocked(ports.sound.unlocked()));
      },
      async playSound() {
        const ok = await ports.sound.play();
        setSoundUnlocked(ports.sound.unlocked());
        return ok;
      },
      soundUnlocked,
      observedEvents: observed,
    }),
    [permission, ports, soundUnlocked, observed],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
