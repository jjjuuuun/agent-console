/** 표현 컴포넌트의 크기·시각 표기를 앱 층에서 쓰기 위한 얇은 연결(문구 표는 패키지 문구 묶음 `memory-view`). */
import { useCallback, useMemo } from "react";
import { useLibMessages } from "@agent-console/i18n";
import { defaultMessages, formatRelativeTime, resolveMessages, type MemoryViewMessages } from "@agent-console/memory-view";

/** 현재 언어의 표현 컴포넌트 문구 표(패키지 기본값 위에 현재 언어 묶음을 덮는다). */
export function useViewMessages(): MemoryViewMessages {
  const overlaid = useLibMessages("memory-view", defaultMessages);
  return useMemo(() => resolveMessages(overlaid), [overlaid]);
}

/** 상대 시각 함수(`3분 전`). 시각은 Unix epoch 초. 언어가 바뀌면 새 함수가 된다. */
export function useRelativeTime(): (at: number | null | undefined, now?: number) => string {
  const messages = useViewMessages();
  return useCallback((at, now = Math.floor(Date.now() / 1000)) => formatRelativeTime(at, now, messages), [messages]);
}
