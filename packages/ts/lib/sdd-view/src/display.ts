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
