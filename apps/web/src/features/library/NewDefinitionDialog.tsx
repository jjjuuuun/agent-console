import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { DefinitionIdField, useDefinitionId } from "./DefinitionIdField";
import { libraryMessages as t } from "./messages";

export interface NewDefinitionValues {
  name: string;
  id: string;
  description: string;
}

export interface NewDefinitionDialogProps {
  open: boolean;
  title: string;
  submitLabel: string;
  /** 이미 있는 id(중복 즉시 표시) */
  existingIds: ReadonlySet<string>;
  /** 이름이 한글뿐이라 id를 못 만들 때 쓸 기본 id */
  fallbackId: string;
  initialName?: string;
  initialDescription?: string;
  /** true면 id 칸을 숨긴다(이름 바꾸기). 이때 id 검증은 하지 않는다 */
  hideId?: boolean;
  /** false면 설명 칸을 숨긴다 */
  showDescription?: boolean;
  /** 이름과 설명 사이에 끼울 추가 입력(종류별 칸 등) */
  extra?: ReactNode;
  /** 제출을 막을 추가 조건(예: 종류를 안 골랐음) */
  disabled?: boolean;
  busy?: boolean;
  error?: string | null;
  onSubmit: (values: NewDefinitionValues) => void;
  onClose: () => void;
}

/**
 * 이름·id·설명을 받는 만들기/복제 다이얼로그. id는 이름에서 자동 제안하고(직접 고치면 멈춘다) 중복은 입력 즉시 알린다.
 * 열 때마다 내용을 새로 시작하도록 호출자가 `open`일 때만 렌더하거나 `key`를 바꾼다.
 */
export function NewDefinitionDialog(props: NewDefinitionDialogProps) {
  const { open, title, submitLabel, existingIds, fallbackId, showDescription = true, hideId = false, extra, disabled, busy, error, onSubmit, onClose } = props;
  const [name, setName] = useState(props.initialName ?? "");
  const [description, setDescription] = useState(props.initialDescription ?? "");
  const nameRef = useRef<HTMLInputElement>(null);
  const uid = useId();
  const defId = useDefinitionId(name, existingIds, fallbackId);
  const id = defId.id;
  const invalid = name.trim() === "" || (!hideId && defId.invalid);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (invalid || disabled || busy) return;
    onSubmit({ name: name.trim(), id, description: description.trim() });
  };

  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      initialFocus={nameRef}
      actions={
        <>
          <Button onClick={onClose}>{t.cancel}</Button>
          <Button variant="primary" type="submit" form={`${uid}-form`} loading={busy === true} disabled={invalid || disabled === true}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <form id={`${uid}-form`} className="lib-form" onSubmit={submit}>
        {error ? <Banner tone="danger">{error}</Banner> : null}
        <div className="lib-field">
          <label htmlFor={`${uid}-name`}>{t.newDialog.name}</label>
          <input id={`${uid}-name`} ref={nameRef} className="ac-input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
        </div>
        {hideId ? null : <DefinitionIdField id={id} problem={defId.problem} onChange={defId.setId} inputId={`${uid}-id`} />}
        {extra}
        {showDescription ? (
          <div className="lib-field">
            <label htmlFor={`${uid}-desc`}>{t.newDialog.description}</label>
            <textarea id={`${uid}-desc`} className="ac-input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        ) : null}
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}
