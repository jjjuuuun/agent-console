import { useRef, useState } from "react";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { folderHomeMessages as m } from "./folderHomeMessages";

export interface UnregisterDialogProps {
  name: string;
  /** 전체 경로(줄임 없음). 미지정이면 null */
  folder: string | null;
  /** 구성 폴더 이름(`{dir}`) */
  configDir: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

const BODY_AFTER = "의 파일은 지우지 않습니다.";

/** 등록 해제 확인(screen-projects §6.2, 폭 480). 폴더 안 파일·구성·기록은 지우지 않는다. 기본 포커스는 [취소]. */
export function UnregisterDialog({ name, folder, configDir, onConfirm, onClose }: UnregisterDialogProps) {
  const cancel = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const close = () => {
    if (!busy) onClose();
  };
  return (
    <Dialog
      open
      title={m.unregister.title(name)}
      onClose={close}
      initialFocus={cancel}
      actions={
        <>
          <Button ref={cancel} onClick={close} disabled={busy}>{m.dialog.cancel}</Button>
          <Button
            variant="danger"
            loading={busy}
            onClick={() => {
              setBusy(true);
              setError(null);
              onConfirm().then(
                () => onClose(),
                (e: unknown) => {
                  setBusy(false);
                  setError(e instanceof Error && e.message !== "" ? e.message : m.unregister.failed);
                },
              );
            }}
          >
            {m.unregister.submit}
          </Button>
        </>
      }
    >
      <p>
        {m.unregister.bodyBefore}
        {folder === null ? null : <> (<span className="ac-mono-wrap">{folder}</span>)</>}
        {BODY_AFTER} {m.unregister.bodyAfter(configDir)}
      </p>
      {error === null ? null : <Banner tone="danger">{error}</Banner>}
    </Dialog>
  );
}
