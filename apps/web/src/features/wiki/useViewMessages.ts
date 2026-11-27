import { useLibMessages } from "@agent-console/i18n";
import { defaultMessages, type WikiViewMessages } from "@agent-console/wiki-view";

/** 현재 언어의 `@agent-console/wiki-view` 문구(표현 컴포넌트의 `messages` prop). 패키지 기본값 위에 현재 언어 묶음을 덮는다. */
export function useWikiViewMessages(): WikiViewMessages {
  return useLibMessages("wiki-view", defaultMessages as unknown as Parameters<typeof useLibMessages>[1]) as unknown as WikiViewMessages;
}
