/** 표현 컴포넌트의 크기·시각 표기를 앱 층에서 쓰기 위한 얇은 연결(문구 표는 패키지 기본값). */
import { defaultMessages, formatRelativeTime, resolveMessages, type MemoryViewMessages } from "@agent-console/memory-view";

export const viewMessages: MemoryViewMessages = resolveMessages();
export const sizeMessages: Pick<MemoryViewMessages, "size.b" | "size.kib" | "size.mib"> = defaultMessages as unknown as MemoryViewMessages;

/** 상대 시각(`3분 전`). 시각은 Unix epoch 초. */
export function relativeTime(at: number | null | undefined, now: number = Math.floor(Date.now() / 1000)): string {
  return formatRelativeTime(at, now, viewMessages);
}
