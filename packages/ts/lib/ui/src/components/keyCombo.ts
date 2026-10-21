import { useEffect, useRef } from "react";

/** 키 조합 문자열("Ctrl+K", "Mod+K", "Alt+J", "Shift+/")을 판정하는 데 필요한 키보드 이벤트 일부. */
export interface KeyComboEvent {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  isComposing?: boolean;
  keyCode?: number;
}

export type KeyPlatform = "mac" | "other";

const ALIASES: Record<string, string> = { esc: "escape", space: " ", spacebar: " ", return: "enter", del: "delete", up: "arrowup", down: "arrowdown", left: "arrowleft", right: "arrowright" };

interface ParsedCombo {
  key: string;
  ctrl: boolean;
  meta: boolean;
  alt: boolean;
  shift: boolean;
}

/** 조합 문자열 해석. `Mod`는 Mac이면 Meta, 아니면 Ctrl. 빈 문자열이면 undefined. */
export function parseKeyCombo(combo: string, platform: KeyPlatform = "other"): ParsedCombo | undefined {
  const parts = combo.split("+").map((p) => p.trim()).filter((p) => p !== "");
  // "Ctrl++" 같은 표기를 위해 마지막이 비면 +를 키로 본다.
  if (combo.trim().endsWith("+") && parts[parts.length - 1] !== "+") parts.push("+");
  const keyPart = parts.pop();
  if (keyPart === undefined) return undefined;
  const parsed: ParsedCombo = { key: (ALIASES[keyPart.toLowerCase()] ?? keyPart).toLowerCase(), ctrl: false, meta: false, alt: false, shift: false };
  for (const mod of parts) {
    const m = mod.toLowerCase();
    if (m === "mod") parsed[platform === "mac" ? "meta" : "ctrl"] = true;
    else if (m === "ctrl" || m === "control") parsed.ctrl = true;
    else if (m === "meta" || m === "cmd" || m === "command" || m === "super") parsed.meta = true;
    else if (m === "alt" || m === "option") parsed.alt = true;
    else if (m === "shift") parsed.shift = true;
    else return undefined;
  }
  return parsed;
}

/** 이벤트가 조합과 정확히 일치하는지(지정하지 않은 수식키가 눌려 있으면 불일치). IME 조합 중에는 항상 false. */
export function matchKeyCombo(event: KeyComboEvent, combo: string, platform: KeyPlatform = "other"): boolean {
  if (event.isComposing === true || event.keyCode === 229) return false;
  const parsed = parseKeyCombo(combo, platform);
  if (parsed === undefined) return false;
  return (
    event.key.toLowerCase() === parsed.key &&
    event.ctrlKey === parsed.ctrl &&
    event.metaKey === parsed.meta &&
    event.altKey === parsed.alt &&
    // 기호 키(?, / 등)는 Shift 여부가 배열마다 달라 Shift를 지정하지 않았을 때만 무시한다.
    (parsed.shift ? event.shiftKey : parsed.key.length > 1 || /[a-z0-9]/.test(parsed.key) ? !event.shiftKey : true)
  );
}

/** 화면 표시용 문자열. Mac은 `Mod`/`Meta`를 ⌘ 등으로, 그 외는 그대로 정리한다. */
export function formatKeyCombo(combo: string, platform: KeyPlatform = "other"): string {
  const parsed = parseKeyCombo(combo, platform);
  if (parsed === undefined) return combo;
  const key = parsed.key === " " ? "Space" : parsed.key.length === 1 ? parsed.key.toUpperCase() : parsed.key.charAt(0).toUpperCase() + parsed.key.slice(1);
  if (platform === "mac") return `${parsed.ctrl ? "⌃" : ""}${parsed.alt ? "⌥" : ""}${parsed.shift ? "⇧" : ""}${parsed.meta ? "⌘" : ""}${key}`;
  return [parsed.ctrl ? "Ctrl" : "", parsed.alt ? "Alt" : "", parsed.shift ? "Shift" : "", parsed.meta ? "Meta" : "", key].filter(Boolean).join("+");
}

export interface UseKeyComboOptions {
  platform?: KeyPlatform;
  /** false면 등록하지 않는다. */
  enabled?: boolean;
  /** 기본 true: 일치하면 브라우저 기본 동작을 막는다(Ctrl+K 주소창 등). */
  preventDefault?: boolean;
  /** 이벤트를 받을 대상. 기본 window. */
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
}

/**
 * 수식키를 포함한 전역 단축키 하나를 등록한다. 조합 문자열은 데이터(예: 사용자 설정 `ui.keybindings`)로 받는다.
 * 단일 문자 키 시퀀스·화면 범위 등록은 앱의 단축키 처리기 몫이다.
 */
export function useKeyCombo(combo: string | undefined, handler: (event: KeyboardEvent) => void, options: UseKeyComboOptions = {}): void {
  const { platform = "other", enabled = true, preventDefault = true, target } = options;
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  });
  useEffect(() => {
    if (!enabled || combo === undefined || combo === "") return;
    const el = target ?? window;
    const listener = (event: Event) => {
      const e = event as KeyboardEvent;
      if (!matchKeyCombo(e, combo, platform)) return;
      if (preventDefault) e.preventDefault();
      handlerRef.current(e);
    };
    el.addEventListener("keydown", listener);
    return () => el.removeEventListener("keydown", listener);
  }, [combo, platform, enabled, preventDefault, target]);
}
