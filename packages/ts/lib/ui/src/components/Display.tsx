import type { HTMLAttributes, ReactNode } from "react";
import { joinClass } from "./Status";

export type Tone = "info" | "warning" | "danger" | "success";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

/** 숫자·짧은 값 배지. */
export function Badge({ tone, className, ...rest }: BadgeProps) {
  return <span {...rest} className={joinClass("ac-badge", className)} data-tone={tone} />;
}

/** 텍스트 태그. 한 줄 말줄임, 전체 값은 title. */
export function Tag({ children, title, className, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span title={title ?? (typeof children === "string" ? children : undefined)} {...rest} className={joinClass("ac-tag", "ac-ellipsis", className)}>
      {children}
    </span>
  );
}

export interface BannerProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  tone?: Tone;
  title?: ReactNode;
  /** 오른쪽 액션(버튼 등). */
  actions?: ReactNode;
}

/** 배너 = 아이콘 + 왼쪽 막대 + tint + 텍스트 (색만으로 구분하지 않는다). 오류는 role=alert. */
export function Banner({ tone = "info", title, actions, children, className, ...rest }: BannerProps) {
  return (
    <div role={tone === "danger" ? "alert" : "status"} {...rest} className={joinClass("ac-banner", className)} data-tone={tone}>
      <span className="ac-banner-mark" aria-hidden="true" />
      <div className="ac-banner-body">
        {title === undefined ? null : <div className="ac-banner-title">{title}</div>}
        <div className="ac-text">{children}</div>
      </div>
      {actions === undefined ? null : <div className="ac-banner-actions">{actions}</div>}
    </div>
  );
}
