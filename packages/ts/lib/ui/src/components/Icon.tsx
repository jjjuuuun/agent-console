import { createContext, createElement, useContext, useMemo, type ComponentType, type ReactNode } from "react";
import { joinClass } from "./Status";

/** 아이콘 컴포넌트 계약. 레지스트리에 넣는 컴포넌트는 크기와 className만 받으면 된다. */
export type IconComponent = ComponentType<{ size?: number; className?: string }>;

/** 이름 → 아이콘 컴포넌트 표. 불변: `register`는 새 레지스트리를 돌려준다(전역 상태 없음). */
export interface IconRegistry {
  get(name: string): IconComponent | undefined;
  has(name: string): boolean;
  names(): string[];
  /** 이름을 더하거나 덮어쓴 새 레지스트리. */
  register(icons: Readonly<Record<string, IconComponent>>): IconRegistry;
}

/** 레지스트리를 만든다. */
export function createIconRegistry(icons: Readonly<Record<string, IconComponent>> = {}): IconRegistry {
  const table = new Map(Object.entries(icons));
  return {
    get: (name) => table.get(name),
    has: (name) => table.has(name),
    names: () => Array.from(table.keys()),
    register: (more) => createIconRegistry({ ...Object.fromEntries(table), ...more }),
  };
}

function svgIcon(paths: ReactNode): IconComponent {
  return function SvgIcon({ size = 16, className }) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden="true"
        focusable="false"
      >
        {paths}
      </svg>
    );
  };
}

/** 앱 구조에 속하는 고정 아이콘(tokens.md 5.7). 노드 타입·리소스 종류 등 데이터가 주는 아이콘은 여기 없다. */
export const defaultIcons: Readonly<Record<string, IconComponent>> = {
  entry: svgIcon(<path d="M2 8h8M7 4.5 10.5 8 7 11.5M13 2.5v11" />),
  exit: svgIcon(<path d="M14 8H6M9 4.5 5.5 8 9 11.5M3 2.5v11" />),
  ask: svgIcon(
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M6.3 6.4a1.8 1.8 0 1 1 2.6 1.6c-.6.3-.9.7-.9 1.3M8 11.4h.01" />
    </>,
  ),
  override: svgIcon(<path d="M2.5 13.5l.7-3L10.5 3.2a1.4 1.4 0 0 1 2 2L5.2 12.8zM9.3 4.4l2.3 2.3" />),
  inherit: svgIcon(<path d="M3 8a5 5 0 1 0 1.8-3.8M3 2.5v3h3" />),
  lock: svgIcon(
    <>
      <rect x="3" y="7" width="10" height="6.5" rx="1.5" />
      <path d="M5.2 7V5a2.8 2.8 0 0 1 5.6 0v2" />
    </>,
  ),
  "external-link": svgIcon(<path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5M12 9.5v3a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3" />),
  copy: svgIcon(
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 5.5V4a1.5 1.5 0 0 0-1.5-1.5H4A1.5 1.5 0 0 0 2.5 4v5A1.5 1.5 0 0 0 4 10.5h1.5" />
    </>,
  ),
  eye: svgIcon(
    <>
      <path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
    </>,
  ),
  refresh: svgIcon(<path d="M13.5 8a5.5 5.5 0 1 1-1.7-4M13.5 2.5v3h-3" />),
  close: svgIcon(<path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />),
  more: svgIcon(
    <>
      <circle cx="3.5" cy="8" r=".6" fill="currentColor" />
      <circle cx="8" cy="8" r=".6" fill="currentColor" />
      <circle cx="12.5" cy="8" r=".6" fill="currentColor" />
    </>,
  ),
  plus: svgIcon(<path d="M8 3v10M3 8h10" />),
  undo: svgIcon(<path d="M3 6.5h6.5a3.5 3.5 0 0 1 0 7H6M5.5 3.5 3 6.5l2.5 3" />),
  check: svgIcon(<path d="M3 8.5l3.2 3.2L13 4.5" />),
  trash: svgIcon(<path d="M2.5 4.5h11M6 4.5V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5M4 4.5l.6 8.3a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9l.6-8.3M6.7 7v4M9.3 7v4" />),
  send: svgIcon(<path d="M2 8 14 2.5 10 14 7.8 9.2zM7.8 9.2 14 2.5" />),
  stop: svgIcon(<rect x="3.5" y="3.5" width="9" height="9" rx="1.5" />),
  "panel-left-close": svgIcon(
    <>
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M6 2.5v11M11.5 6.2 9.7 8l1.8 1.8" />
    </>,
  ),
  "panel-left-open": svgIcon(
    <>
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M6 2.5v11M9.7 6.2 11.5 8 9.7 9.8" />
    </>,
  ),
  filter: svgIcon(<path d="M2 3.5h12L9.5 9v4l-3 1.5V9z" />),
  columns: svgIcon(
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <path d="M6 3v10M10 3v10" />
    </>,
  ),
  table: svgIcon(
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <path d="M2 6.5h12M2 9.8h12M6.5 6.5V13" />
    </>,
  ),
  "chevron-right": svgIcon(<path d="M6 3.5 10.5 8 6 12.5" />),
  "chevron-left": svgIcon(<path d="M10 3.5 5.5 8 10 12.5" />),
  "chevron-down": svgIcon(<path d="M3.5 6 8 10.5 12.5 6" />),
  expand: svgIcon(<path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" />),
  play: svgIcon(<path d="M4.5 2.8v10.4L13 8z" />),
  pencil: svgIcon(<path d="M2.5 13.5l.7-3L10.5 3.2a1.4 1.4 0 0 1 2 2L5.2 12.8zM9.3 4.4l2.3 2.3" />),
  pin: svgIcon(<path d="M9.5 2.5l4 4-2 .8-2.2 2.2.4 2.3-1 1-2.2-2.2-3.7 3.7M6.6 5.2l-.8 2.2" />),
  architecture: svgIcon(<path d="M2.75 2.75h2.5v2.5h-2.5zM6.75 2.75h2.5v2.5h-2.5zM10.75 2.75h2.5v2.5h-2.5zM2.75 6.75h2.5v2.5h-2.5zM6.75 6.75h2.5v2.5h-2.5zM10.75 6.75h2.5v2.5h-2.5zM2.75 10.75h2.5v2.5h-2.5zM6.75 10.75h2.5v2.5h-2.5zM10.75 10.75h2.5v2.5h-2.5z" />),
  "eye-off": svgIcon(<path d="M2 2l12 12M6.4 4a6.6 6.6 0 0 1 1.6-.5c4 0 6.5 4.5 6.5 4.5a11 11 0 0 1-2 2.5M9.6 12a6.6 6.6 0 0 1-1.6.5C4 12.5 1.5 8 1.5 8a11 11 0 0 1 2.6-3" />),
};

/** 기본 레지스트리(앱 고정 이름만). 앱은 `registerIcons`로 확장한 것을 `IconRegistryProvider`에 넣는다. */
export const iconRegistry: IconRegistry = createIconRegistry(defaultIcons);

/** `base`(기본: `iconRegistry`)에 아이콘을 더한 새 레지스트리. */
export function registerIcons(icons: Readonly<Record<string, IconComponent>>, base: IconRegistry = iconRegistry): IconRegistry {
  return base.register(icons);
}

const IconRegistryContext = createContext<IconRegistry>(iconRegistry);

export interface IconRegistryProviderProps {
  /** 통째로 바꿀 레지스트리. 없으면 상위 레지스트리를 쓴다. */
  registry?: IconRegistry;
  /** 위 레지스트리(또는 상위)에 더할 아이콘. */
  icons?: Readonly<Record<string, IconComponent>>;
  children?: ReactNode;
}

/** 아이콘 레지스트리 주입. 중첩하면 안쪽이 이긴다. */
export function IconRegistryProvider({ registry, icons, children }: IconRegistryProviderProps) {
  const parent = useContext(IconRegistryContext);
  const value = useMemo(() => {
    const base = registry ?? parent;
    return icons === undefined ? base : base.register(icons);
  }, [registry, parent, icons]);
  return <IconRegistryContext.Provider value={value}>{children}</IconRegistryContext.Provider>;
}

/** 현재 레지스트리. */
export function useIconRegistry(): IconRegistry {
  return useContext(IconRegistryContext);
}

export interface IconProps {
  /** 레지스트리 이름(예: 디스크립터 `ui_hints.icon`). */
  name?: string;
  size?: number;
  /** 있으면 의미 있는 이미지(`role=img`), 없으면 장식(`aria-hidden`). */
  label?: string;
  /** 이름이 없거나 레지스트리에 없을 때 첫 글자 아바타로 쓸 텍스트(보통 제목). 없으면 아무것도 그리지 않는다. */
  fallbackText?: string;
  className?: string;
}

/** 이름으로 아이콘을 그린다. 모르는 이름은 `fallbackText`의 첫 글자 아바타. */
export function Icon({ name, size = 16, label, fallbackText, className }: IconProps) {
  const registry = useIconRegistry();
  const Component = name === undefined ? undefined : registry.get(name);
  const a11y = label === undefined ? { "aria-hidden": true as const } : { role: "img" as const, "aria-label": label };
  if (Component !== undefined) {
    return (
      <span className={joinClass("ac-icon", className)} style={{ width: size, height: size }} {...a11y}>
        {createElement(Component, { size })}
      </span>
    );
  }
  const initial = fallbackText === undefined ? undefined : Array.from(fallbackText.trim())[0];
  if (initial === undefined) return null;
  return (
    <span
      className={joinClass("ac-icon", "ac-icon-avatar", className)}
      data-fallback="true"
      style={{ width: size, height: size, fontSize: Math.max(12, Math.round(size * 0.7)) }}
      {...a11y}
    >
      <span aria-hidden="true">{initial.toUpperCase()}</span>
    </span>
  );
}
