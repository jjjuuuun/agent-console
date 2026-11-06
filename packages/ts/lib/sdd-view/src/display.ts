/**
 * 상태·톤 표시 순수 함수. 상태 id·톤 이름·빈 곳 코드는 서버 데이터이고, 여기에는 고정 목록이 없다.
 * 모르는 값은 id 원문 + 중립 톤으로 떨어진다(R0.1).
 */

/** 라벨·톤을 가진 상태 정의(작업 상태·문서 상태 공통 모양). `TaskStatusInfo`·`DocumentStateInfo`가 이 모양이다. */
export interface StatusLike {
  id: string;
  label?: string | null;
  tone?: string | null;
  done?: boolean;
}

/** 칩에 그릴 값. */
export interface ToneDisplay {
  id: string;
  label: string;
  tone: string;
  done: boolean;
}

/** 톤을 정하지 않았을 때 쓰는 이름(CSS가 이 이름의 스타일을 기본값으로 쓴다). */
export const NEUTRAL_TONE = "neutral";

/** `data-tone`에 안전하게 달 수 있는 값으로 바꾼다. 비었거나 이상한 값은 중립. */
export function toneAttr(tone: string | null | undefined): string {
  return tone && /^[a-z][a-z0-9-]*$/.test(tone) ? tone : NEUTRAL_TONE;
}

/**
 * 상태 id → 칩 값. 정의가 있으면 `label`·`tone`, 없으면 id 원문과 중립.
 * 톤이 없고 `done`이면 `success`로 보여 준다("success"는 서버 톤 어휘의 일반 값이고 상태 이름이 아니다).
 */
export function statusTone(status: string, statuses: readonly StatusLike[] = []): ToneDisplay {
  const found = statuses.find((s) => s.id === status);
  if (!found) return { id: status, label: status, tone: NEUTRAL_TONE, done: false };
  const done = found.done === true;
  const tone = found.tone ? toneAttr(found.tone) : done ? "success" : NEUTRAL_TONE;
  return { id: status, label: found.label && found.label !== "" ? found.label : status, tone, done };
}

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
