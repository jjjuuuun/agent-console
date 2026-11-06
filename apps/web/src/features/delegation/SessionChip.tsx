import type { ReactNode } from "react";
import { Icon, useIconRegistry } from "@agent-console/ui";
import type { ChipView } from "@agent-console/graph-editor";
import { KNOWN_DELEGATION_SESSIONS as SESSIONS } from "@agent-console/contracts/constants";
import { sessionText, sessionTip } from "./delegationAttributes";

/** 세션 값 → 아이콘 이름(앱 데이터). 표에 없는 값은 `FALLBACK_ICON`. */
export const SESSION_ICONS: Readonly<Record<string, string>> = { [SESSIONS.SEPARATE]: "git-fork", [SESSIONS.SAME]: "corner-down-right" };
const FALLBACK_ICON = "circle";

export interface SessionChipProps {
  /** 세션 값(서버의 열린 문자열). null·undefined면 아무것도 그리지 않는다 */
  value: string | null | undefined;
  /** 같은 세션의 안내 문구에 들어갈 위임자 이름 */
  delegatorLabel?: string;
  /** `icon`은 아이콘만(접근성 이름·툴팁은 full 문구) */
  variant?: "full" | "icon";
  /** 있으면 단추가 된다 */
  onClick?: () => void;
  className?: string;
  /** 칩 안에 더 넣을 것(드물게) */
  children?: ReactNode;
}

/**
 * 세션 칩: 편집기 연결선·연결 패널·노드 패널·실행 상세·위임 흐름·채팅 진행 줄이 같은 부품·같은 문구를 쓴다
 * (screen-delegation.md §14.3). 색을 쓰지 않고 아이콘 모양·글자·테두리 모양(실선/점선)으로 구분한다.
 */
export function SessionChip({ value, delegatorLabel, variant = "full", onClick, className, children }: SessionChipProps) {
  const registry = useIconRegistry();
  if (value === null || value === undefined || value === "") return null;
  const text = sessionText(value);
  const tip = sessionTip(value, delegatorLabel);
  const iconName = SESSION_ICONS[value] ?? FALLBACK_ICON;
  const common = {
    className: ["ses-chip", className].filter(Boolean).join(" "),
    "data-session": value === SESSIONS.SAME || value === SESSIONS.SEPARATE ? value : "other",
    "data-variant": variant,
    title: `${text} — ${tip}`,
  };
  const body = (
    <>
      {registry.has(iconName) ? <Icon name={iconName} size={variant === "icon" ? 14 : 12} /> : null}
      {variant === "icon" ? <span className="ac-sr-only">{text}</span> : <span className="ses-chip-text">{text}</span>}
      {children}
    </>
  );
  if (onClick !== undefined) {
    return (
      <button type="button" {...common} aria-label={variant === "icon" ? `${text}, ${tip}` : undefined} onClick={onClick}>
        {body}
      </button>
    );
  }
  return variant === "icon" ? (
    <span {...common} role="img" aria-label={`${text}, ${tip}`}>
      {registry.has(iconName) ? <Icon name={iconName} size={14} /> : null}
    </span>
  ) : (
    <span {...common}>{body}</span>
  );
}

/** 편집기 칩 데이터(`edgeLeadChips`·`nodeAnnotations.foot`)를 만든다. 세션 값이 없으면 undefined. */
export function sessionChipView(value: string | null | undefined, opts: { key?: string; delegatorLabel?: string; iconOnly?: boolean } = {}): ChipView | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const text = sessionText(value);
  const tip = sessionTip(value, opts.delegatorLabel);
  return {
    key: opts.key ?? "session",
    title: text,
    fullTitle: `${text} — ${tip}`,
    iconName: SESSION_ICONS[value] ?? FALLBACK_ICON,
    tone: "neutral",
    ...(value === SESSIONS.SAME ? { dashed: true } : {}),
    ...(opts.iconOnly === true ? { iconOnly: true } : {}),
  };
}
