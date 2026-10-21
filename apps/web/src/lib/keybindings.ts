import { isPlainCharCombo, parseKeyCombo, splitKeySequence, type EffectiveShortcut, type KeyComboEvent, type KeyPlatform } from "@agent-console/ui";

/** 키 조합 문제 종류. 저장을 막지 않고 행에 경고로만 보인다. */
export type KeybindingIssue = "invalid" | "conflict" | "reserved" | "modifier_required";

/**
 * 브라우저가 먼저 쓰는 키 조합(데이터). 겹쳐도 저장은 되며 경고만 한다.
 * 형식은 `parseKeyCombo`가 읽는 조합 문자열(`Mod`는 Mac이면 ⌘, 아니면 Ctrl).
 */
export const BROWSER_RESERVED_COMBOS: readonly string[] = [
  "Mod+T", "Mod+W", "Mod+N", "Mod+Shift+N", "Mod+Tab", "Mod+L", "Mod+D", "Mod+Shift+O", "F5", "Alt+ArrowLeft", "Alt+ArrowRight",
  ...Array.from({ length: 9 }, (_, i) => `Mod+${i + 1}`),
];

/** 실행 환경에서 Mac 여부를 판별한다(`navigator.platform`/`userAgent` 문자열을 받는다). */
export function detectPlatform(platformText: string | undefined): KeyPlatform {
  return platformText !== undefined && /mac|iphone|ipad/i.test(platformText) ? "mac" : "other";
}

function signature(combo: string, platform: KeyPlatform): string | undefined {
  const p = parseKeyCombo(combo, platform);
  return p === undefined ? undefined : `${p.ctrl ? "c" : ""}${p.meta ? "m" : ""}${p.alt ? "a" : ""}${p.shift ? "s" : ""}:${p.key}`;
}

/** 키 조합 하나(또는 `g c` 같은 시퀀스)에 대한 문제 목록. 빈 키(비활성)는 문제 없음. */
export function checkKeybinding(entry: Pick<EffectiveShortcut, "keys" | "conflict" | "modifierRequired">, platform: KeyPlatform): KeybindingIssue[] {
  const issues: KeybindingIssue[] = [];
  const tokens = splitKeySequence(entry.keys);
  if (tokens.length === 0) return issues;
  if (tokens.length > 2 || tokens.some((t) => parseKeyCombo(t, platform) === undefined)) return ["invalid"];
  if (entry.conflict !== undefined) issues.push("conflict");
  const reserved = new Set(BROWSER_RESERVED_COMBOS.map((c) => signature(c, platform)));
  if (tokens.length === 1 && reserved.has(signature(tokens[0]!, platform))) issues.push("reserved");
  if (entry.modifierRequired === true && tokens.some((t) => isPlainCharCombo(t, platform))) issues.push("modifier_required");
  return issues;
}

/** 첫 토큰이 단일 문자 키인가(입력창 안에서는 동작하지 않는 종류). */
export function isPlainKeys(keys: string, platform: KeyPlatform): boolean {
  const first = splitKeySequence(keys)[0];
  return first !== undefined && isPlainCharCombo(first, platform);
}

const MODIFIER_ONLY = new Set(["Shift", "Control", "Alt", "Meta", "AltGraph", "CapsLock", "OS"]);

/**
 * 눌린 키 이벤트를 저장용 조합 문자열로 바꾼다. 수식키만 눌렀으면 undefined.
 * 주 수식키는 `Mod`(Mac이면 ⌘, 그 외 Ctrl)로 적어 플랫폼이 달라도 같은 설정이 통한다.
 */
export function comboFromEvent(event: KeyComboEvent, platform: KeyPlatform): string | undefined {
  if (MODIFIER_ONLY.has(event.key)) return undefined;
  const parts: string[] = [];
  const modCtrl = platform === "mac" ? event.ctrlKey : false;
  const mod = platform === "mac" ? event.metaKey : event.ctrlKey;
  if (mod) parts.push("Mod");
  if (modCtrl) parts.push("Ctrl");
  if (platform !== "mac" && event.metaKey) parts.push("Meta");
  if (event.altKey) parts.push("Alt");
  const named = event.key.length > 1;
  const alnum = /^[a-z0-9]$/i.test(event.key);
  // 기호 키(?, / 등)는 Shift 여부가 배열마다 달라 적지 않는다.
  if (event.shiftKey && (named || alnum)) parts.push("Shift");
  parts.push(event.key === " " ? "Space" : alnum ? event.key.toUpperCase() : event.key);
  return parts.join("+");
}
