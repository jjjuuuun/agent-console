import type { ReactElement } from "react";

export type IconName = "folder" | "folder-lock" | "chevron-right" | "more";

const PATHS: Record<IconName, ReactElement> = {
  folder: <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.6l1.4 1.5h5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z" />,
  "folder-lock": (
    <>
      <path d="M8 13H3.5A1.5 1.5 0 0 1 2 11.5v-7A1.5 1.5 0 0 1 3.5 3h2.6l1.4 1.5h5A1.5 1.5 0 0 1 14 6v1" />
      <rect x="9" y="9.5" width="5" height="4" rx=".8" />
      <path d="M10 9.5V8.6a1.5 1.5 0 0 1 3 0v.9" />
    </>
  ),
  "chevron-right": <path d="M6 3.5L10.5 8 6 12.5" />,
  more: <path d="M4 8h.01M8 8h.01M12 8h.01" />,
};

/** 16x16 선 아이콘. 색은 currentColor, 장식이라 스크린 리더에서 숨긴다(이름은 주변 텍스트가 가진다). */
export function Icon({ name, className }: { name: IconName; className?: string }): ReactElement {
  return (
    <svg className={`ac-fp-icon${className ? ` ${className}` : ""}`} viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}
