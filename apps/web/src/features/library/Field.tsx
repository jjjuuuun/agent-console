import { useId, type ReactNode } from "react";

export interface FieldProps {
  label: string;
  /** 입력 아래 12px 보조 설명(입력의 `aria-describedby`로 이어진다) */
  hint?: string | undefined;
  /** 있으면 오류 문구(입력에 `aria-invalid`) */
  error?: string | undefined;
  /** 입력 요소에 그대로 펼칠 속성(`id`, `aria-describedby`, `aria-invalid`) */
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}

/**
 * 라벨 + 입력 + 보조 설명 한 묶음. 라벨은 `htmlFor`로만 이어져 접근성 이름이 라벨 글자만 된다
 * (설명 문장이 이름에 섞이지 않는다).
 */
export function Field({ label, hint, error, children }: FieldProps) {
  const uid = useId();
  const noteId = `${uid}-note`;
  const describedBy = hint !== undefined || error !== undefined ? noteId : undefined;
  return (
    <div className="lib-field">
      <label htmlFor={`${uid}-input`}>{label}</label>
      {children({ id: `${uid}-input`, ...(describedBy === undefined ? {} : { "aria-describedby": describedBy }), ...(error === undefined ? {} : { "aria-invalid": true }) })}
      {error !== undefined ? (
        <span id={noteId} className="lib-field-error" role="alert">{error}</span>
      ) : hint !== undefined ? (
        <span id={noteId} className="app-muted lib-field-note">{hint}</span>
      ) : null}
    </div>
  );
}
