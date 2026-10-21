import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { joinClass } from "./Status";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** true면 스피너를 겹쳐 보이고 폭은 유지, `aria-busy`, 클릭 불가. */
  loading?: boolean;
  /** 라벨 앞 아이콘(장식). */
  icon?: ReactNode;
  ref?: Ref<HTMLButtonElement>;
}

/** 기본 버튼. 라벨은 children으로 받는다(문구는 호출자가 messages로 전달). */
export function Button({ variant = "secondary", size = "md", loading = false, icon, disabled, children, className, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={joinClass("ac-btn", className)}
      data-variant={variant}
      data-size={size}
      data-loading={loading ? "true" : undefined}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
    >
      {icon === undefined ? null : <span className="ac-btn-icon" aria-hidden="true">{icon}</span>}
      <span className="ac-btn-label ac-ellipsis">{children}</span>
      {loading ? <Spinner /> : null}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "aria-label"> {
  /** 필수: aria-label과 title(툴팁)로 쓴다. */
  label: string;
  icon: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/** 아이콘 버튼. 히트 영역은 최소 24x24(`--ac-control-sm`). */
export function IconButton({ label, icon, variant = "ghost", size = "md", className, type = "button", ...rest }: IconButtonProps) {
  return (
    <button
      title={label}
      {...rest}
      type={type}
      aria-label={label}
      className={joinClass("ac-btn", "ac-icon-btn", className)}
      data-variant={variant}
      data-size={size}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  );
}

/** 회전 스피너. reduced-motion이면 정지. */
export function Spinner({ label }: { label?: string }) {
  return <span className="ac-spinner" {...(label === undefined ? { "aria-hidden": true } : { role: "status", "aria-label": label })} />;
}
