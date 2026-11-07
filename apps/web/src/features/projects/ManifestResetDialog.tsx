import { useId, useRef, useState, type ReactNode } from "react";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { folderHomeMessages as m } from "./folderHomeMessages";

export interface ManifestResetDialogProps {
  /** 등록된 이름·설명(기본값) */
  name: string;
  description: string;
  /** 구성 폴더 이름(`{dir}`) */
  configDir?: string | undefined;
  /** 쓸 수 없는 폴더면 이유 문구(버튼 `aria-disabled`) */
  blockedReason?: string | undefined;
  /** 제출. 예외를 던지면 대화상자 안에 오류를 보인다(성공·"이미 정상" 안내 토스트는 호출한 쪽이 낸다). */
  onSubmit: (value: { name: string; description: string | undefined }) => Promise<void>;
  onClose: () => void;
}

function withCode(template: string, dir: string): ReactNode {
  const parts = template.split("{dir}");
  return parts.flatMap((p, i) => (i === 0 ? [p] : [<code key={i}>{dir}</code>, p]));
}

/** 설정 파일 다시 만들기(screen-projects §6.1, 폭 480). 기존 파일은 서버가 백업으로 옮긴다. 기본 포커스는 [취소]. */
export function ManifestResetDialog({ name: initialName, description: initialDesc, configDir, blockedReason, onSubmit, onClose }: ManifestResetDialogProps) {
  const uid = useId();
  const cancel = useRef<HTMLButtonElement>(null);
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDesc);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const can = name.trim() !== "" && blockedReason === undefined && !busy;
  const close = () => {
    if (!busy) onClose();
  };
  const submit = () => {
    if (!can) return;
    setBusy(true);
    setError(null);
    onSubmit({ name: name.trim(), description: description.trim() === "" ? undefined : description.trim() }).then(
      () => onClose(),
      (e: unknown) => {
        setBusy(false);
        setError(e instanceof Error && e.message !== "" ? e.message : m.problem.manifestRecreateFailed);
      },
    );
  };
  return (
    <Dialog
      open
      title={m.problem.manifestRecreateTitle}
      onClose={close}
      initialFocus={cancel}
      actions={
        <>
          <Button ref={cancel} onClick={close} disabled={busy}>{m.dialog.cancel}</Button>
          <Button variant="primary" loading={busy} aria-disabled={!can && !busy ? "true" : undefined} title={blockedReason} onClick={submit}>
            {busy ? m.problem.manifestRecreateBusy : m.problem.manifestRecreateSubmit}
          </Button>
        </>
      }
    >
      <div className="prj-fd">
        <p className="prj-fd-intro">{configDir === undefined ? m.problem.manifestRecreateBodyUnknown : withCode(m.problem.manifestRecreateBody, configDir)}</p>
        <div className="prj-fd-field">
          <label htmlFor={`${uid}-name`}>{m.dialog.name} *</label>
          <input id={`${uid}-name`} className="ac-input" value={name} disabled={busy} aria-required="true" onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="prj-fd-field">
          <label htmlFor={`${uid}-desc`}>{m.dialog.description}</label>
          <textarea id={`${uid}-desc`} className="ac-input" rows={2} value={description} disabled={busy} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {blockedReason === undefined ? null : <Banner tone="warning">{blockedReason}</Banner>}
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
      </div>
    </Dialog>
  );
}
