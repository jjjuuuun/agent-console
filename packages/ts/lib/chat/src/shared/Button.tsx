import type { ButtonHTMLAttributes } from "react";

export type BtnVariant = "default" | "primary" | "ghost" | "danger";

/**
 * 토큰 클래스(`.ac-btn`)를 쓰는 작은 버튼. `@agent-console/ui`를 import하지 않고
 * 클래스 이름 약속만 쓴다(패키지 간 의존 금지).
 */
export function Btn({
  variant = "default",
  size,
  loading,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "lg"; loading?: boolean }) {
  return (
    <button
      type={type}
      className="ac-btn"
      data-variant={variant === "default" ? undefined : variant}
      data-size={size}
      data-loading={loading ? "true" : undefined}
      aria-busy={loading || undefined}
      {...rest}
    />
  );
}
