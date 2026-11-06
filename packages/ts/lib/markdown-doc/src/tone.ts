/**
 * 상태·톤 표시 순수 함수. 상태 id·톤 이름은 서버 데이터이고, 여기에는 고정 목록이 없다.
 * 모르는 값은 id 원문 + 중립 톤으로 떨어진다(R0.1).
 */

/** 라벨·톤을 가진 상태 정의(작업 상태·문서 상태 공통 모양). */
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
