import type { ReactNode } from "react";
import { joinClass } from "./Status";

export interface EmptyStep {
  label: string;
  done: boolean;
  action?: ReactNode;
}

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  secondaryAction?: ReactNode;
  /** 시작하기 체크리스트. 완료 여부는 체크 글리프와 텍스트(`doneLabel`)로 함께 전달한다. */
  steps?: readonly EmptyStep[];
  /** 완료된 단계의 보조 텍스트(스크린리더용, 예: "완료"). */
  doneLabel?: string;
  className?: string;
}

/** 빈 상태 안내. 문구·동작은 호출자가 넘긴다. */
export function EmptyState({ icon, title, description, action, secondaryAction, steps, doneLabel, className }: EmptyStateProps) {
  return (
    <div className={joinClass("ac-empty", className)}>
      {icon === undefined || icon === null ? null : (
        <div className="ac-empty-spot" aria-hidden="true">
          {icon}
          <span className="ac-empty-dot ac-empty-dot-a" />
          <span className="ac-empty-dot ac-empty-dot-b" />
        </div>
      )}
      <h3 className="ac-empty-title">{title}</h3>
      {description === undefined ? null : <div className="ac-text">{description}</div>}
      {steps === undefined || steps.length === 0 ? null : (
        <ol className="ac-empty-steps">
          {steps.map((step, i) => (
            <li key={i} className="ac-empty-step" data-done={step.done ? "true" : "false"}>
              <span aria-hidden="true">{step.done ? "✓" : "○"}</span>
              <span>{step.label}</span>
              {step.done && doneLabel !== undefined ? <span className="ac-sr-only">{doneLabel}</span> : null}
              {step.action}
            </li>
          ))}
        </ol>
      )}
      {action === undefined && secondaryAction === undefined ? null : (
        <div className="ac-empty-actions">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}
