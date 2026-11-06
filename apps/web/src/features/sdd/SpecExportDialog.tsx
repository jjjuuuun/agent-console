/**
 * 폴더로 내보내기(screen-sdd §4.4): 프로젝트 폴더 안(상대 경로) 대상에 문서를 복사한다. 제출은 props이고 결과를 이 대화상자가 보인다.
 * 대상 폴더는 `loadDirs`가 있으면 트리(한 단계씩, 프로젝트 폴더 밖으로 못 나감)로 고르고 경로 입력은 대안으로 남는다.
 */
import { useId, useRef, useState } from "react";
import { Banner, Button, Choice, Dialog, Disclosure } from "@agent-console/ui";
import type { ImportFileListing, SpecExportRequest, SpecExportResult } from "@agent-console/contracts/sdd";
import { describeError } from "../../app/errors";
import { sddMessages as m } from "./messages";
import { SpecFolderBrowser } from "./SpecFolderBrowser";

export interface SpecExportDialogProps {
  open: boolean;
  onClose: () => void;
  blockedReason?: string | undefined;
  /** 폴더 하나의 하위 폴더 목록(프로젝트 폴더 기준 상대 경로). 없으면 트리 없이 입력만 쓴다 */
  loadDirs?: ((path: string) => Promise<ImportFileListing>) | undefined;
  onSubmit: (body: SpecExportRequest) => Promise<SpecExportResult>;
}

export function SpecExportDialog({ open, onClose, blockedReason, loadDirs, onSubmit }: SpecExportDialogProps) {
  const [dir, setDir] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SpecExportResult | null>(null);
  const ref = useRef<HTMLInputElement>(null);
  const uid = useId();
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const submit = async () => {
    if (busy || blocked || dir.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      setResult(await onSubmit({ to_dir: dir.trim(), overwrite }));
    } catch (e) {
      setError(describeError(e, m.problem.generic).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      title={m.export.title}
      onClose={() => { if (!busy) onClose(); }}
      initialFocus={ref}
      actions={
        result === null ? (
          <>
            <Button onClick={onClose} disabled={busy}>{m.cancel}</Button>
            <Button variant="primary" loading={busy} aria-disabled={blocked || dir.trim() === "" || undefined} title={blocked ? blockedReason : undefined} onClick={() => void submit()}>
              {busy ? m.export.submitting : m.export.submit}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={() => void navigator.clipboard?.writeText(result.to_dir)}>{m.copy}</Button>
            <Button variant="primary" onClick={onClose}>{m.close}</Button>
          </>
        )
      }
    >
      <div className="sdd-form">
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        {result === null ? (
          <>
            {loadDirs === undefined ? null : (
              <div className="sdd-field">
                <span className="sdd-label">{m.import.browse}</span>
                <SpecFolderBrowser id={`${uid}-tree`} load={loadDirs} rootLabel={m.import.root} onNavigate={setDir} onSelect={setDir} />
                <span className="app-muted" role="status">{m.export.chosen(dir)}</span>
              </div>
            )}
            <label className="sdd-field" htmlFor={`${uid}-dir`}>
              <span className="sdd-label">{loadDirs === undefined ? m.export.folder : m.export.manual}</span>
              <input id={`${uid}-dir`} ref={ref} className="sdd-input sdd-mono" value={dir} onChange={(e) => setDir(e.target.value)} />
            </label>
            <Choice checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)}>{m.export.overwrite}</Choice>
            {overwrite ? <p className="sdd-danger-note" role="note">{m.export.overwriteWarn}</p> : null}
            <p className="app-muted">{m.export.note}</p>
          </>
        ) : (
          <>
            <p role="status">{m.export.done((result.written ?? []).length, result.to_dir)}</p>
            {(result.skipped ?? []).length > 0 ? <Banner tone="warning">{m.export.skipped((result.skipped ?? []).join(", "))}</Banner> : null}
            <Disclosure summary={m.export.files}>
              <ul className="sdd-files">{(result.written ?? []).map((f) => <li key={f} className="sdd-mono">{f}</li>)}</ul>
            </Disclosure>
          </>
        )}
      </div>
    </Dialog>
  );
}
