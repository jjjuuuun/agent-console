import { useLibMessages, type MessageTree } from "@agent-console/i18n";
import type { ChatLocale } from "@agent-console/chat";
import { ko } from "@agent-console/chat/locales/ko";

const DEFAULTS = ko as unknown as MessageTree;

/**
 * 현재 언어의 `@agent-console/chat` 문구 묶음(`chat`·`interaction`·`composer`·`markdown`).
 * 각 부분을 해당 컴포넌트의 `messages` prop에 넘긴다(예: `<InteractionCard messages={locale.interaction} />`).
 */
export function useChatLocale(): ChatLocale {
  return useLibMessages("chat", DEFAULTS) as unknown as ChatLocale;
}
