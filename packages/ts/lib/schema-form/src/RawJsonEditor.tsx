import { useId, useState } from "react";

export interface RawJsonEditorProps {
  value: unknown;
  onChange?: (value: unknown) => void;
  label: string;
  invalidMessage: string;
  disabled?: boolean;
  readonly?: boolean;
  id?: string;
  /** 이 값에 붙은 외부(서버·검증) 오류 */
  errors?: string[];
}

/** 원시 JSON 편집기. 파싱 오류는 인라인으로 보이고, 유효한 JSON일 때만 onChange를 호출한다. */
export function RawJsonEditor({ value, onChange, label, invalidMessage, disabled, readonly, id, errors }: RawJsonEditorProps) {
  const autoId = useId();
  const baseId = id ?? autoId;
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [invalid, setInvalid] = useState(false);
  return (
    <div className="ac-sf-raw">
      <label className="ac-sf-label" htmlFor={baseId}>
        {label}
      </label>
      <textarea
        id={baseId}
        className="ac-sf-raw-input"
        value={text}
        rows={8}
        spellCheck={false}
        disabled={disabled}
        readOnly={readonly}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${baseId}-err` : undefined}
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          try {
            const parsed: unknown = JSON.parse(next);
            setInvalid(false);
            onChange?.(parsed);
          } catch {
            setInvalid(true);
          }
        }}
      />
      {(errors ?? []).map((e) => (
        <p key={e} className="ac-sf-error" role="alert">
          ⚠ {e}
        </p>
      ))}
      {invalid ? (
        <p id={`${baseId}-err`} className="ac-sf-error" role="alert">
          ⚠ {invalidMessage}
        </p>
      ) : null}
    </div>
  );
}
