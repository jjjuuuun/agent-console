import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/** 첫 단계 안내의 문구(세 곳 — 채팅 시작하기 카드·채팅 빈 상태·팀 구성 목록 빈 상태 — 이 같은 표를 쓴다). */
export const createStartMessages = (t: Translate) => ({
  title: t("title"),
  close: t("close"),
  description: t("description"),
  stepsLabel: t("stepsLabel"),
  go: t("go"),
  done: t("done"),
  /** 단계 문구. 키는 `startSteps.ts`의 단계 id */
  steps: {
    create: { label: t("steps.create.label"), hint: t("steps.create.hint"), action: t("steps.create.action") },
    talk: { label: t("steps.talk.label"), hint: t("steps.talk.hint"), action: t("steps.talk.action") },
    review: { label: t("steps.review.label"), hint: t("steps.review.hint"), action: t("steps.review.action") },
  } as Record<string, { label: string; hint: string; action: string }>,
} as const);

/** 첫 단계 안내 문구 표(현재 화면 언어). */
export type StartMessages = ReturnType<typeof createStartMessages>;

export function useStartMessages(): StartMessages {
  return useMessageTable("start", createStartMessages);
}

