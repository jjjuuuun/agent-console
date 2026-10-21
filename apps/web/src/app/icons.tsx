import type { ReactNode } from "react";
import type { IconComponent } from "@agent-console/ui";

function svg(paths: ReactNode): IconComponent {
  return function AppIcon({ size = 16, className }) {
    return (
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true" focusable="false">
        {paths}
      </svg>
    );
  };
}

/**
 * 앱 구조(사이드바 항목·도구 줄)에 쓰는 아이콘. 라우트 설정 데이터의 `icon` 이름이 여기를 가리킨다.
 * 노드 타입·리소스 종류 아이콘은 서버 디스크립터가 주므로 여기에 없다.
 */
export const appIcons: Readonly<Record<string, IconComponent>> = {
  chat: svg(<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z" />),
  teams: svg(
    <>
      <circle cx="4" cy="4" r="1.6" />
      <circle cx="12" cy="4" r="1.6" />
      <circle cx="8" cy="12" r="1.6" />
      <path d="M5.4 4.8 7 10.5M10.6 4.8 9 10.5M5.6 4h4.8" />
    </>,
  ),
  agents: svg(
    <>
      <circle cx="8" cy="5.5" r="2.5" />
      <path d="M3 13.5c.6-2.6 2.5-4 5-4s4.4 1.4 5 4" />
    </>,
  ),
  resources: svg(<path d="M3 3.5h4l1.5 1.5H13v7.5H3z" />),
  projects: svg(
    <>
      <rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1" />
      <rect x="9" y="2.5" width="4.5" height="4.5" rx="1" />
      <rect x="2.5" y="9" width="4.5" height="4.5" rx="1" />
      <rect x="9" y="9" width="4.5" height="4.5" rx="1" />
    </>,
  ),
  runs: svg(
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 4.8V8l2.2 1.4" />
    </>,
  ),
  usage: svg(<path d="M3 13V8M7 13V4M11 13V6.5M14 13.5H2" />),
  logs: svg(
    <>
      <path d="M3 2.5h8l2 2v9H3z" />
      <path d="M5.5 6.5h5M5.5 9h5M5.5 11.5h3" />
    </>,
  ),
  // 톱니: 닫힌 외곽선(이빨 8개) + 가운데 원. 해(방사형 선)와 실루엣이 달라야 한다.
  settings: svg(
    <>
      <path d="M6.90 3.23 L7.08 1.46 L8.92 1.46 L9.10 3.23 L10.60 3.84 L11.97 2.73 L13.27 4.03 L12.16 5.40 L12.77 6.90 L14.54 7.08 L14.54 8.92 L12.77 9.10 L12.16 10.60 L13.27 11.97 L11.97 13.27 L10.60 12.16 L9.10 12.77 L8.92 14.54 L7.08 14.54 L6.90 12.77 L5.40 12.16 L4.03 13.27 L2.73 11.97 L3.84 10.60 L3.23 9.10 L1.46 8.92 L1.46 7.08 L3.23 6.90 L3.84 5.40 L2.73 4.03 L4.03 2.73 L5.40 3.84z" />
      <circle cx="8" cy="8" r="2" />
    </>,
  ),
  help: svg(
    <>
      <circle cx="8" cy="8" r="5.8" />
      <path d="M6.4 6.4a1.7 1.7 0 1 1 2.5 1.5c-.5.3-.9.6-.9 1.2M8 11.4h.01" />
    </>,
  ),
  // 테마 도구줄용 고정 아이콘(◐). 현재 테마는 툴팁·aria-label이 알린다.
  theme: svg(
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" />
    </>,
  ),
  "theme-dark": svg(<path d="M12.5 9.5A5 5 0 0 1 6.5 3.5a5 5 0 1 0 6 6z" />),
  "theme-light": svg(
    <>
      <circle cx="8" cy="8" r="2.6" />
      <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" />
    </>,
  ),
  "theme-system": svg(
    <>
      <rect x="2" y="2.5" width="12" height="8" rx="1" />
      <path d="M6 13.5h4M8 10.5v3" />
    </>,
  ),
  install: svg(<path d="M8 2.5v7M5 7l3 3 3-3M3 12.5h10" />),
  search: svg(
    <>
      <circle cx="7" cy="7" r="4" />
      <path d="M10 10l3.5 3.5" />
    </>,
  ),
  "module-active": svg(
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M5.6 8.2l1.7 1.7 3.2-3.4" />
    </>,
  ),
  "module-disabled": svg(
    <>
      <path d="M8 2.2v5" />
      <path d="M4.6 4.4a5.2 5.2 0 1 0 6.8 0" />
    </>,
  ),
  "module-unsatisfied": svg(<path d="M6.5 9.5l-1.8 1.8a2 2 0 0 1-2.8-2.8L3.7 6.7M9.5 6.5l1.8-1.8a2 2 0 0 1 2.8 2.8l-1.8 1.8M5.6 5.6l.9.9M9.5 9.5l.9.9" />),
  "module-failed": svg(
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M6 6l4 4M10 6l-4 4" />
    </>,
  ),
  "module-conflict": svg(<path d="M2.5 5.5h10M10 3l2.5 2.5L10 8M13.5 10.5h-10M6 8l-2.5 2.5L6 13" />),
  check: svg(<path d="M3.5 8.5l3 3 6-6.5" />),
  // 독립 위임·반복·조건·중첩 팀 (tokens.md 5.10). 연결 종류가 이름으로 고른다(`ui_hints.icon`·속성 기본 아이콘).
  repeat: svg(<path d="M3 7V6a2 2 0 0 1 2-2h8M11 1.8 13.2 4 11 6.2M13 9v1a2 2 0 0 1-2 2H3M5 14.2 2.8 12 5 9.8" />),
  "triangle-alert": svg(<path d="M8 2.2l6 10.6H2zM8 6.4v3M8 11.2h.01" />),
  filter: svg(<path d="M2.5 3.5h11L9.5 8.4v4.1l-3 1.5V8.4z" />),
  "corner-down-right": svg(<path d="M3 3v4.5a2 2 0 0 0 2 2h7M9.5 6.5 12.5 9.5 9.5 12.5" />),
  chevronRight: svg(<path d="M6 4l4 4-4 4" />),
  chevronUp: svg(<path d="M4 10l4-4 4 4" />),
  chevronDown: svg(<path d="M4 6l4 4 4-4" />),
};
