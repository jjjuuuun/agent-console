import type { ButtonHTMLAttributes, Ref } from "react";
import type { ButtonSize, ButtonVariant } from "./Button";
import { Spinner } from "./Button";
import { Icon } from "./Icon";
import { formatKeyCombo, type KeyPlatform } from "./keyCombo";
import { joinClass } from "./Status";
import { Tooltip } from "./Tooltip";

/** 버튼 정의 표의 한 줄: 화면 설정이 이 모양의 데이터를 갖고 `ActionButton`이 그린다. */
export interface ActionDef {
  id: string;
  /** 아이콘 레지스트리 이름(데이터). */
  icon?: string;
  /** 사용자에게 보이는 이름(메시지 표에서 해석한 문자열). */
  label: string;
  /** 단축키 조합(`"Mod+S"`). 툴팁에 덧붙는다. */
  shortcut?: string;
}

export interface ActionButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "aria-label" | "title" | "aria-pressed">, Omit<ActionDef, "id"> {
  /**
   * 표시 방식. `icon` = 아이콘만(라벨은 aria-label+툴팁), `icon-label` = 아이콘 + 글자, `label` = 글자만.
   * 기본: 아이콘이 있으면 `icon`, 없으면 `label`.
   */
  display?: "icon" | "icon-label" | "label";
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** true면 아이콘(없으면 글자 앞)이 스피너로 바뀌고 `aria-busy`, 클릭 불가. */
  loading?: boolean;
  /** 상태를 가진 토글이면 눌림 여부(`aria-pressed`). */
  pressed?: boolean;
  /** 단축키 표기 플랫폼. */
  platform?: KeyPlatform;
  /** 툴팁 위치. */
  tooltipPlacement?: "bottom" | "top";
  tooltipAlign?: "center" | "start" | "end";
  ref?: Ref<HTMLButtonElement>;
}

/**
 * 아이콘 버튼 규칙(ux-overhaul §3.1)을 한 곳에서 지키는 버튼: `label`은 `aria-label`이면서 툴팁(400ms, 포커스 즉시),
 * 단축키가 있으면 툴팁에 `Ctrl+…`를 덧붙인다. 아이콘 이름·라벨·단축키는 모두 호출자가 준 데이터다.
 */
export function ActionButton({
  icon,
  label,
  shortcut,
  display,
  variant = "ghost",
  size = "md",
  loading = false,
  pressed,
  platform,
  tooltipPlacement,
  tooltipAlign,
  disabled,
  className,
  type = "button",
  ref,
  ...rest
}: ActionButtonProps) {
  const mode = display ?? (icon === undefined ? "label" : "icon");
  const combo = shortcut === undefined ? undefined : formatKeyCombo(shortcut, platform);
  const iconNode = loading ? <Spinner /> : icon === undefined ? null : <Icon name={icon} fallbackText={label} />;
  const button = (
    <button
      {...rest}
      ref={ref}
      type={type}
      aria-label={mode === "icon" ? label : undefined}
      aria-keyshortcuts={shortcut === undefined ? undefined : shortcut.replace(/Mod/g, "Control")}
      aria-pressed={pressed}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={joinClass("ac-btn", mode === "icon" && "ac-icon-btn", "ac-action", className)}
      data-variant={variant}
      data-size={size}
      data-display={mode}
      data-loading={loading ? "true" : undefined}
    >
      {mode === "label" ? null : <span className="ac-btn-icon" aria-hidden="true">{iconNode}</span>}
      {mode === "icon" ? null : <span className="ac-btn-label ac-ellipsis">{label}</span>}
    </button>
  );
  // 글자가 보이는 버튼은 단축키가 있을 때만 툴팁을 둔다(라벨 반복 방지).
  if (mode !== "icon" && combo === undefined) return button;
  return (
    <Tooltip placement={tooltipPlacement} align={tooltipAlign} content={combo === undefined ? label : mode === "icon" ? `${label} (${combo})` : combo}>
      {button}
    </Tooltip>
  );
}
