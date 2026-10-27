import { useId, type ReactNode } from "react";
import { joinClass } from "./Status";

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** 옆에 보이는 라벨. 없으면 `ariaLabel`이 필요하다. */
  label?: ReactNode;
  ariaLabel?: string;
  /** 켜짐/꺼짐 글자 단서(색에만 의존하지 않기 위해). 문구는 호출자가 messages로 전달. */
  onText: string;
  offText: string;
  disabled?: boolean;
  className?: string;
}

/** 켜고 끄는 스위치(`role="switch"`, `aria-checked`). 스페이스·엔터로 토글한다(button 기본 동작). */
export function Switch({ checked, onChange, label, ariaLabel, onText, offText, disabled = false, className }: SwitchProps) {
  const labelId = useId();
  return (
    <span className={joinClass("ac-switch", className)} data-disabled={disabled ? "true" : undefined}>
      <button
        type="button"
        role="switch"
        className="ac-switch-track"
        aria-checked={checked}
        aria-label={label === undefined ? ariaLabel : undefined}
        aria-labelledby={label === undefined ? undefined : labelId}
        disabled={disabled}
        onClick={() => onChange(!checked)}
      />
      {label === undefined ? null : <span id={labelId}>{label}</span>}
      <span className="ac-switch-state" aria-hidden="true">{checked ? onText : offText}</span>
    </span>
  );
}
