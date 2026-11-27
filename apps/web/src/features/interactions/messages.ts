import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/** 상호작용 응답 공용 문구(채팅·실행 상세가 공유). 화면별로 다른 문구가 필요하면 훅/컴포넌트에 덮어 넘긴다. */
export const createInteractionMessages = (t: Translate) => ({
  closed: t("closed"),
  notFound: t("notFound"),
  offline: t("offline"),
  failed: t("failed"),
  payload: t("payload"),
  send: t("send"),
} as const);

export type InteractionMessages = { -readonly [K in keyof ReturnType<typeof createInteractionMessages>]: string };

/** 상호작용 응답 문구 표(현재 화면 언어). */
export function useInteractionMessages(): InteractionMessages {
  return useMessageTable("interactions", createInteractionMessages);
}
