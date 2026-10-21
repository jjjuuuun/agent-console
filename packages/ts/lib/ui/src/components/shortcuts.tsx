import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { matchKeyCombo, parseKeyCombo, type KeyPlatform } from "./keyCombo";

/** 단축키 정의. 동작 id·키·핸들러는 모두 호출자가 데이터로 넘긴다(이 패키지는 동작 이름을 모른다). */
export interface ShortcutDef {
  id: string;
  /** `"global"` 또는 화면 id. 같은 범위(또는 global과 화면)끼리만 키 충돌로 본다. */
  scope: string;
  /** `"Mod+K"`, `"?"`, 시퀀스는 공백으로 구분(`"g c"`). */
  keys: string;
  /** 도움말·설정 화면이 messages에서 찾을 제목 키. */
  titleKey: string;
  /** true면 수식키(Ctrl/Meta/Alt)가 없는 키 조합을 거부한다(설정 검증용 표시). */
  modifierRequired?: boolean;
  run(): void;
}

export interface EffectiveShortcut {
  id: string;
  scope: string;
  titleKey: string;
  /** 실제 적용 중인 키(설정이 있으면 설정 값). 빈 문자열이면 비활성. */
  keys: string;
  /** 설정이 덮어쓰지 않은 기본 키인가. */
  isDefault: boolean;
  modifierRequired?: boolean;
  /** 같은 키를 쓰는 다른 항목의 id(없으면 생략). */
  conflict?: string;
}

/** 시퀀스 두 번째 키 대기 시간(ms). */
export const SEQUENCE_TIMEOUT_MS = 1000;

const MODIFIER_KEYS = new Set(["Shift", "Control", "Alt", "Meta", "AltGraph", "CapsLock", "OS"]);
const EDITABLE_SELECTOR = "input, textarea, select, [contenteditable]:not([contenteditable='false']), [data-ac-editable]";

/** 키 문자열을 조합 목록으로 나눈다("g c" → ["g","c"]). 비면 빈 배열. */
export function splitKeySequence(keys: string): string[] {
  return keys.trim() === "" ? [] : keys.trim().split(/\s+/);
}

/** 단일 문자 키(수식키 Ctrl/Meta/Alt 없이 글자·기호 한 자)인가. 입력창 안에서는 동작하지 않는 종류. */
export function isPlainCharCombo(combo: string, platform: KeyPlatform = "other"): boolean {
  const p = parseKeyCombo(combo, platform);
  return p !== undefined && !p.ctrl && !p.meta && !p.alt && p.key.length === 1;
}

/** 입력창 안에서 글자를 지우는 키(수식키 없는 Delete·Backspace). 단일 문자 키처럼 입력창 안에서는 동작하지 않는다. */
export function isPlainEditKeyCombo(combo: string, platform: KeyPlatform = "other"): boolean {
  const p = parseKeyCombo(combo, platform);
  return p !== undefined && !p.ctrl && !p.meta && !p.alt && (p.key === "delete" || p.key === "backspace");
}

function normalize(keys: string, platform: KeyPlatform): string {
  return splitKeySequence(keys)
    .map((c) => {
      const p = parseKeyCombo(c, platform);
      return p === undefined ? c : `${p.ctrl ? "c" : ""}${p.meta ? "m" : ""}${p.alt ? "a" : ""}${p.shift ? "s" : ""}:${p.key}`;
    })
    .join(" ");
}

function scopesOverlap(a: string, b: string): boolean {
  return a === b || a === "global" || b === "global";
}

/**
 * 기본 표와 설정(`ui.keybindings`)을 합쳐 실제 적용 키 표를 만든다. 순수 함수.
 * @param defs 기본 정의(같은 id가 여러 번이면 뒤의 것이 이김)
 * @param overrides `{동작 id: 키 문자열}`; 빈 문자열이면 그 동작을 끈다
 */
export function computeEffectiveKeys(defs: readonly Omit<ShortcutDef, "run">[], overrides: Readonly<Record<string, string>> = {}, platform: KeyPlatform = "other"): EffectiveShortcut[] {
  const byId = new Map<string, Omit<ShortcutDef, "run">>();
  for (const d of defs) byId.set(d.id, d);
  const list: EffectiveShortcut[] = [...byId.values()].map((d) => {
    const overridden = Object.prototype.hasOwnProperty.call(overrides, d.id);
    const keys = overridden ? (overrides[d.id] ?? "") : d.keys;
    return {
      id: d.id,
      scope: d.scope,
      titleKey: d.titleKey,
      keys,
      isDefault: !overridden || keys === d.keys,
      ...(d.modifierRequired === undefined ? {} : { modifierRequired: d.modifierRequired }),
    };
  });
  const norm = list.map((e) => normalize(e.keys, platform));
  return list.map((e, i) => {
    if (e.keys === "") return e;
    const other = list.find((o, j) => j !== i && norm[j] === norm[i] && scopesOverlap(e.scope, o.scope));
    return other === undefined ? e : { ...e, conflict: other.id };
  });
}

export interface ShortcutProviderProps {
  /** 웹의 기본 표. 핸들러를 포함한다. */
  defaults: readonly ShortcutDef[];
  /** 설정 `ui.keybindings`: 동작 id → 키. */
  overrides?: Readonly<Record<string, string>>;
  platform?: KeyPlatform;
  /** false면 모든 단축키를 끈다. */
  enabled?: boolean;
  /** 중복 키 경고를 받는다. 기본 console.warn(개발 중 확인용). `null`이면 경고하지 않는다. */
  onWarn?: ((message: string, conflict: EffectiveShortcut) => void) | null;
  /** 이벤트를 받을 대상. 기본 window. */
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
  children?: ReactNode;
}

interface Registry {
  getEffectiveKeys(): EffectiveShortcut[];
  register(owner: string, defs: readonly ShortcutDef[]): () => void;
  /** 등록·설정이 바뀔 때마다 증가(표를 그리는 훅이 다시 그리도록). */
  version: number;
}

const ShortcutContext = createContext<Registry | null>(null);

function isEditableTarget(t: EventTarget | null): boolean {
  return typeof Element !== "undefined" && t instanceof Element && t.closest(EDITABLE_SELECTOR) !== null;
}

/** 전역 단축키 처리기. 기본 표 + 화면이 `useShortcuts`로 등록한 정의를 합쳐 keydown 하나로 처리한다. */
export function ShortcutProvider({ defaults, overrides, platform = "other", enabled = true, onWarn, target, children }: ShortcutProviderProps) {
  const registered = useRef(new Map<string, readonly ShortcutDef[]>());
  const [version, setVersion] = useState(0);
  const defaultsRef = useRef(defaults);
  const overridesRef = useRef(overrides);
  useEffect(() => {
    defaultsRef.current = defaults;
    overridesRef.current = overrides;
  });

  const collect = useCallback((): { defs: ShortcutDef[]; effective: EffectiveShortcut[] } => {
    const map = new Map<string, ShortcutDef>();
    for (const d of defaultsRef.current) map.set(d.id, d);
    for (const list of registered.current.values()) for (const d of list) map.set(d.id, d);
    const defs = [...map.values()];
    return { defs, effective: computeEffectiveKeys(defs, overridesRef.current ?? {}, platform) };
  }, [platform]);

  const getEffectiveKeys = useCallback(() => collect().effective, [collect]);
  const register = useCallback((owner: string, defs: readonly ShortcutDef[]) => {
    registered.current.set(owner, defs);
    setVersion((v) => v + 1);
    return () => {
      registered.current.delete(owner);
      setVersion((v) => v + 1);
    };
  }, []);

  // 중복 키 경고: 표가 바뀔 때만.
  const signature = useMemo(
    () => JSON.stringify([defaults.map((d) => [d.id, d.scope, d.keys]), overrides ?? {}, version]),
    [defaults, overrides, version],
  );
  useEffect(() => {
    if (onWarn === null) return;
    const warn = onWarn ?? ((m: string) => console.warn(m));
    const seen = new Set<string>();
    for (const e of collect().effective) {
      if (e.conflict === undefined) continue;
      const key = [e.id, e.conflict].sort().join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      warn(`단축키 중복: "${e.keys}" — ${e.id} / ${e.conflict}`, e);
    }
  }, [signature, collect, onWarn]);

  // keydown 처리
  const pending = useRef<{ first: string; fallback?: () => void; timer: ReturnType<typeof setTimeout> } | null>(null);
  useEffect(() => {
    if (!enabled) return;
    const el = target ?? window;
    // 취소: 대기 중이던 단일 키 동작(fallback)이 있으면 `flush`일 때 실행한다.
    const cancel = (flush = false) => {
      const p = pending.current;
      if (p !== null) clearTimeout(p.timer);
      pending.current = null;
      if (flush) p?.fallback?.();
    };
    const listener = (event: Event) => {
      const e = event as KeyboardEvent;
      if (e.isComposing || e.keyCode === 229) return;
      // 키를 누르고 있어서 반복되는 입력은 단축키로 치지 않는다(시퀀스 대기도 건드리지 않는다).
      if (e.repeat) return;
      if (MODIFIER_KEYS.has(e.key)) return;
      const inEditable = isEditableTarget(e.target);
      const { defs, effective } = collect();
      const active = effective
        .filter((x) => x.keys !== "")
        .map((x) => ({ x, tokens: splitKeySequence(x.keys), def: defs.find((d) => d.id === x.id) }))
        .filter((a): a is typeof a & { def: ShortcutDef } => a.def !== undefined);
      const allowed = (combo: string) => !(inEditable && (isPlainCharCombo(combo, platform) || isPlainEditKeyCombo(combo, platform)));

      if (pending.current !== null) {
        const { first, fallback } = pending.current;
        const hit = active.find((a) => a.tokens.length === 2 && a.tokens[0] === first && matchKeyCombo(e, a.tokens[1] as string, platform));
        if (hit !== undefined && allowed(hit.tokens[1] as string)) {
          cancel();
          e.preventDefault();
          hit.def.run();
        } else {
          // 잘못된 두 번째 키는 시퀀스를 취소한다. 같은 키의 단일 동작이 있었다면 그것을 실행한다.
          cancel();
          fallback?.();
        }
        return;
      }
      const hits = active.filter((a) => matchKeyCombo(e, a.tokens[0] as string, platform) && allowed(a.tokens[0] as string));
      const single = hits.find((a) => a.tokens.length === 1);
      const startsSequence = hits.some((a) => a.tokens.length === 2);
      if (single === undefined && !startsSequence) return;
      if (!startsSequence) {
        e.preventDefault();
        single?.def.run();
        return;
      }
      // 같은 키가 시퀀스의 첫 키이기도 하면(`g`와 `g c`) 시퀀스가 우선이고, 두 번째 키가 안 오면 단일 동작을 실행한다.
      const first = (hits.find((a) => a.tokens.length === 2) as (typeof hits)[number]).tokens[0] as string;
      const fallback = single === undefined ? undefined : () => single.def.run();
      pending.current = { first, ...(fallback === undefined ? {} : { fallback }), timer: setTimeout(() => cancel(true), SEQUENCE_TIMEOUT_MS) };
    };
    el.addEventListener("keydown", listener);
    return () => {
      el.removeEventListener("keydown", listener);
      cancel();
    };
  }, [enabled, target, platform, collect]);

  const value = useMemo<Registry>(() => ({ getEffectiveKeys, register, version }), [getEffectiveKeys, register, version]);
  return <ShortcutContext.Provider value={value}>{children}</ShortcutContext.Provider>;
}

function useRegistry(): Registry {
  const r = useContext(ShortcutContext);
  if (r === null) throw new Error("ShortcutProvider 안에서만 쓸 수 있습니다.");
  return r;
}

/**
 * 화면이 자기 단축키를 등록(마운트)·해제(언마운트)한다. 같은 id가 기본 표에 있으면 이 정의가 이긴다.
 * 핸들러는 매 렌더의 최신 함수가 불린다(정의 배열을 매번 새로 만들어도 재등록되지 않음).
 */
export function useShortcuts(defs: readonly ShortcutDef[]): void {
  const { register } = useRegistry();
  const owner = useId();
  const ref = useRef(defs);
  useEffect(() => {
    ref.current = defs;
  });
  const signature = JSON.stringify(defs.map((d) => [d.id, d.scope, d.keys, d.titleKey, d.modifierRequired ?? null]));
  useEffect(() => {
    const wrapped: ShortcutDef[] = (JSON.parse(signature) as [string, string, string, string, boolean | null][]).map(([id, scope, keys, titleKey, mr]) => ({
      id,
      scope,
      keys,
      titleKey,
      ...(mr === null ? {} : { modifierRequired: mr }),
      run: () => ref.current.find((d) => d.id === id)?.run(),
    }));
    return register(owner, wrapped);
  }, [signature, register, owner]);
}

/** 도움말·설정 화면의 표 원천. 등록·설정이 바뀌면 다시 계산한다. */
export function useEffectiveShortcuts(): EffectiveShortcut[] {
  const r = useRegistry();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => r.getEffectiveKeys(), [r, r.version]);
}

/** `getEffectiveKeys()`를 직접 부르고 싶을 때(이벤트 핸들러 등). */
export function useShortcutRegistry(): Pick<Registry, "getEffectiveKeys"> {
  return useRegistry();
}
