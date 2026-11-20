/**
 * 상태·톤 표시 순수 함수. 상태 id·톤 이름·빈 곳 코드는 서버 데이터이고, 여기에는 고정 목록이 없다.
 * 모르는 값은 id 원문 + 중립 톤으로 떨어진다(R0.1).
 * 상태·톤 변환(`toneAttr`·`statusTone`)은 칩과 함께 `@agent-console/markdown-doc`에 있고 여기서 다시 내보낸다.
 */
import { NEUTRAL_TONE, toneAttr } from "@agent-console/markdown-doc";


export { NEUTRAL_TONE, statusTone, toneAttr } from "@agent-console/markdown-doc";
export type { StatusLike, ToneDisplay } from "@agent-console/markdown-doc";

/** 열린 문자열 코드(빈 곳·검증 결과)를 보일 값 표. 키 = 코드. 앱 데이터다. */
export type CodeDisplayTable = Readonly<Record<string, { tone?: string; label?: string; hint?: string }>>;

/** 코드 → 라벨·톤. 표에 없으면 `fallbackTone`과 코드 원문. */
export function codeDisplay(
  code: string,
  table: CodeDisplayTable | undefined,
  fallbackTone: string = NEUTRAL_TONE,
  messageLabel?: string,
): { label: string; tone: string; hint?: string } {
  const entry = table?.[code];
  const hint = entry?.hint;
  return {
    label: entry?.label ?? messageLabel ?? code,
    tone: toneAttr(entry?.tone ?? fallbackTone),
    ...(hint !== undefined ? { hint } : {}),
  };
}

/** `a, b, c` 처럼 이어 붙인다(접근성 이름용). */
export function joinList(items: readonly string[], separator = ", "): string {
  return items.join(separator);
}

/** 작업 줄에서 보일 짧은 이름: 제목이 없으면 id, 그것도 없으면 키. */
export function taskTitle(task: { key: string; id?: string | null; title?: string }): string {
  return task.title && task.title !== "" ? task.title : task.id && task.id !== "" ? task.id : task.key;
}

/** 시각(Unix epoch 초) → "3분 전" 같은 상대 시각. 해석할 수 없으면 빈 문자열. `now`는 주입(테스트·시계). */
export function relativeTime(at: number | null | undefined, now: number = Date.now(), locale?: string): string {
  if (at === null || at === undefined || !Number.isFinite(at)) return "";
  const t = at * 1000;
  const sec = Math.round((t - now) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86400], ["hour", 3600], ["minute", 60]];
  const fmt = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, size] of units) if (Math.abs(sec) >= size) return fmt.format(Math.round(sec / size), unit);
  return fmt.format(sec, "second");
}
