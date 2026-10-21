import type { ReactNode } from "react";

/**
 * 이 패키지가 쓰는 작은 아이콘 표(16px 선 아이콘). `@agent-console/ui`에 의존하지 않으려고 같은 모양을 따로 둔다.
 * 아이콘은 장식이고(`aria-hidden`), 이름은 단추의 `aria-label`이 맡는다.
 */
const PATHS: Record<string, ReactNode> = {
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 5.5V4a1.5 1.5 0 0 0-1.5-1.5H4A1.5 1.5 0 0 0 2.5 4v5A1.5 1.5 0 0 0 4 10.5h1.5" />
    </>
  ),
  undo: <path d="M3 6.5h6.5a3.5 3.5 0 0 1 0 7H6M5.5 3.5 3 6.5l2.5 3" />,
  check: <path d="M3 8.5l3.2 3.2L13 4.5" />,
  "external-link": <path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5M12 9.5v3a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3" />,
  expand: <path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" />,
  "chevron-right": <path d="M6 3.5 10.5 8 6 12.5" />,
  "chevron-down": <path d="M3.5 6 8 10.5 12.5 6" />,
  stop: <rect x="3.5" y="3.5" width="9" height="9" rx="1.5" />,
};

export type ChatIconName = "copy" | "undo" | "check" | "external-link" | "expand" | "chevron-right" | "chevron-down" | "stop";

export function ChatIcon({ name, size = 14 }: { name: ChatIconName; size?: number }) {
  return (
    <svg className="ac-chat-icon" width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}
