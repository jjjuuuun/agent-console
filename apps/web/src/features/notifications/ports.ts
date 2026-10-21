import type { PermissionState } from "./core";

/** 브라우저 알림 API를 감싼 주입점. 테스트는 가짜를 넣는다. 전역 `Notification`은 이 파일의 어댑터에서만 만진다. */
export interface NotificationPort {
  permission(): PermissionState;
  /** 사용자의 클릭 핸들러에서만 부른다 */
  requestPermission(): Promise<PermissionState>;
  /** 알림을 띄운다. 실패(예외)는 삼킨다. `onClick`은 알림을 눌렀을 때 */
  show(input: { title: string; body: string; tag?: string; onClick?: () => void }): void;
  /** 보안 컨텍스트가 아니라 못 쓰는 경우의 안내용 */
  insecureContext(): boolean;
}

/** 신호음 주입점. */
export interface SoundPort {
  /** 알림 소리 재생. 막히면 false */
  play(): Promise<boolean>;
  /** 첫 사용자 제스처에서 호출: 오디오 컨텍스트 생성/재개 */
  unlock(): void;
  /** 제스처를 받아 소리를 낼 수 있는 상태인가 */
  unlocked(): boolean;
}

interface NotificationLike {
  onclick: ((this: unknown, ev: unknown) => unknown) | null;
  close(): void;
}
export interface NotificationCtorLike {
  new (title: string, options?: { body?: string; tag?: string }): NotificationLike;
  permission: string;
  requestPermission(): Promise<string>;
}

export interface BrowserNotificationEnv {
  Notification?: NotificationCtorLike | undefined;
  isSecureContext?: boolean | undefined;
  focus?: (() => void) | undefined;
}

const asPermission = (value: string): PermissionState => (value === "granted" || value === "denied" || value === "default" ? value : "default");

/** 브라우저 환경(`window` 같은 객체)을 받아 `NotificationPort`를 만든다. */
export function createBrowserNotificationPort(env: BrowserNotificationEnv): NotificationPort {
  const ctor = env.Notification;
  const secure = env.isSecureContext !== false;
  return {
    permission: () => (ctor === undefined || !secure ? "unsupported" : asPermission(ctor.permission)),
    insecureContext: () => ctor !== undefined && !secure,
    async requestPermission() {
      if (ctor === undefined || !secure) return "unsupported";
      try {
        return asPermission(await ctor.requestPermission());
      } catch {
        return asPermission(ctor.permission);
      }
    },
    show({ title, body, tag, onClick }) {
      if (ctor === undefined) return;
      try {
        const n = new ctor(title, { body, ...(tag === undefined ? {} : { tag }) });
        n.onclick = () => {
          env.focus?.();
          n.close();
          onClick?.();
        };
      } catch {
        // 알림 생성 실패가 앱 동작을 막지 않는다
      }
    },
  };
}

interface GainLike {
  gain: { setValueAtTime(v: number, t: number): unknown; linearRampToValueAtTime(v: number, t: number): unknown };
  connect(n: unknown): unknown;
}
interface OscillatorLike {
  type: string;
  frequency: { setValueAtTime(v: number, t: number): unknown };
  connect(n: unknown): unknown;
  start(t: number): void;
  stop(t: number): void;
}
export interface AudioContextLike {
  currentTime: number;
  state: string;
  destination: unknown;
  resume(): Promise<void>;
  createOscillator(): OscillatorLike;
  createGain(): GainLike;
}

/** 두 음 톤: 높은 음 -> 낮은 음, sine, 각 음에 짧은 페이드 인/아웃. 파일에 의존하지 않는다. */
export interface ToneSpec {
  notes: readonly { hz: number; seconds: number }[];
  peakGain: number;
  fadeSeconds: number;
}
export const DEFAULT_TONE: ToneSpec = { notes: [{ hz: 880, seconds: 0.12 }, { hz: 660, seconds: 0.12 }], peakGain: 0.08, fadeSeconds: 0.01 };

/** WebAudio 신호음. `createContext`는 첫 `unlock()`/`play()`에서만 불린다. */
export function createWebAudioSound(createContext: () => AudioContextLike | undefined, tone: ToneSpec = DEFAULT_TONE): SoundPort {
  let ctx: AudioContextLike | undefined;
  const ensure = (): AudioContextLike | undefined => {
    if (ctx === undefined) {
      try {
        ctx = createContext();
      } catch {
        ctx = undefined;
      }
    }
    return ctx;
  };
  return {
    unlock() {
      const c = ensure();
      if (c !== undefined && c.state === "suspended") void c.resume().catch(() => undefined);
    },
    unlocked: () => ctx !== undefined && ctx.state === "running",
    async play() {
      const c = ensure();
      if (c === undefined) return false;
      try {
        if (c.state === "suspended") await c.resume();
        if (c.state !== "running") return false;
        let t = c.currentTime;
        for (const note of tone.notes) {
          const osc = c.createOscillator();
          const gain = c.createGain();
          osc.type = "sine";
          osc.frequency.setValueAtTime(note.hz, t);
          gain.gain.setValueAtTime(0, t);
          gain.gain.linearRampToValueAtTime(tone.peakGain, t + tone.fadeSeconds);
          gain.gain.setValueAtTime(tone.peakGain, t + note.seconds - tone.fadeSeconds);
          gain.gain.linearRampToValueAtTime(0, t + note.seconds);
          osc.connect(gain);
          gain.connect(c.destination);
          osc.start(t);
          osc.stop(t + note.seconds);
          t += note.seconds;
        }
        return true;
      } catch {
        return false;
      }
    },
  };
}
