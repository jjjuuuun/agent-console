import type { InputHTMLAttributes, ReactNode } from "react";
import { joinClass } from "./Status";

export interface ChoiceProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "children"> {
  /** 체크박스(기본) 또는 라디오. */
  kind?: "checkbox" | "radio";
  /** 라벨(필수: 컨트롤 이름이 된다). */
  children: ReactNode;
  className?: string;
}

/** 체크박스·라디오 한 줄. 컨트롤 모양은 tokens.css 10b가 정하고, 정렬은 `.ac-choice` 하나가 맡는다. */
export function Choice({ kind = "checkbox", children, className, ...rest }: ChoiceProps) {
  return (
    <label className={joinClass("ac-choice", className)}>
      <input {...rest} type={kind} />
      <span>{children}</span>
    </label>
  );
}
