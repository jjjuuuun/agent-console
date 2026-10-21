import { buildBody, notificationTag, requesterName, resolveTarget, shouldNotify, toNotifyEvents, type EventAlias, type NameLookups, type NotifySettings, type NotifyTarget, type PermissionState } from "./core";
import type { NotificationPort, SoundPort } from "./ports";

export interface NotifierDeps {
  notification: NotificationPort;
  sound: SoundPort;
  /** 현재 설정(호출 시점에 읽는다) */
  settings: () => NotifySettings;
  hidden: () => boolean;
  /** 지금 화면에서 이 대상을 보고 있는가 */
  viewing: (target: NotifyTarget) => boolean;
  /** 알림을 눌렀을 때 이동 */
  open: (target: NotifyTarget) => void;
  title: string;
  /** 이벤트 이름 -> 본문 템플릿(문구 데이터) */
  templates?: Readonly<Record<string, string>>;
  aliases?: readonly EventAlias[];
  lookups?: () => NameLookups;
  now?: () => number;
  /** 같은 tag 연속 이벤트를 하나로 묶는 시간(ms) */
  coalesceMs?: number;
  /** 시작 시각 이전 이벤트(재접속 스냅샷)는 무시하는 여유(ms) */
  staleMs?: number;
}

export interface Notifier {
  /** 서버 메시지 하나를 처리한다. 알림을 냈으면 true */
  handle(message: { type: string; payload?: unknown }): boolean;
}

/** 서버 메시지 -> 알림. 판정은 `core`, 브라우저 접근은 주입한 포트. */
export function createNotifier(deps: NotifierDeps): Notifier {
  const now = deps.now ?? Date.now;
  const coalesceMs = deps.coalesceMs ?? 1000;
  const staleMs = deps.staleMs ?? 5000;
  const startedAt = now();
  const lastByTag = new Map<string, number>();
  return {
    handle(message) {
      let fired = false;
      const permission: PermissionState = deps.notification.permission();
      for (const event of toNotifyEvents(message, deps.aliases)) {
        const target = resolveTarget(event.data);
        if (event.ts !== undefined && event.ts < startedAt - staleMs) continue;
        if (!shouldNotify({ settings: deps.settings(), eventName: event.name, permission, hidden: deps.hidden(), viewing: deps.viewing(target) })) continue;
        const tag = notificationTag(event.name, target);
        const t = now();
        const last = lastByTag.get(tag);
        if (last !== undefined && t - last < coalesceMs) continue;
        lastByTag.set(tag, t);
        const body = buildBody(event.name, requesterName(event.data, target, deps.lookups?.()), deps.templates);
        deps.notification.show({ title: deps.title, body, tag, onClick: () => deps.open(target) });
        if (deps.settings().sound) void deps.sound.play();
        fired = true;
        break; // 한 메시지에서 별칭이 겹쳐도 알림은 한 번
      }
      return fired;
    },
  };
}
