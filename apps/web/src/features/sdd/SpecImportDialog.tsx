/**
 * 폴더에서 스펙 가져오기(screen-sdd §4.2): 프로젝트 폴더 안(상대 경로) 마크다운 파일을 고르고 순서를 정해 새 스펙으로 복사한다.
 * 목록 읽기·제출은 props다. 경로 검사(프로젝트 밖·구성 폴더 안)는 서버가 하고 오류는 폴더 칸 아래에 보인다.
 */
import { useId, useRef, useState } from "react";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { Banner, Button, Choice, Dialog } from "@agent-console/ui";
import type { ImportFileListing, SpecImportRequest } from "@agent-console/contracts/sdd";
import { describeError } from "../../app/errors";
import { classifySddError } from "./sddErrors";
import { SDD_LIMITS } from "./sddConfig";
import { sddMessages as m } from "./messages";

export interface SpecImportDialogProps {
  open: boolean;
  onClose: () => void;
  initialName?: string;
  /** 폴더 안 마크다운 파일 목록(프로젝트 폴더 기준 상대 경로, 빈 값 = 루트) */
  loadFiles: (path: string) => Promise<ImportFileListing>;
  blockedReason?: string | undefined;
  /** 제출. 성공하면 호출자가 이동·알림·닫기를 한다. 실패는 던진다 */
  onSubmit: (body: SpecImportRequest) => Promise<void>;
}

interface Row {
  path: string;
  name: string;
  size: number;
  checked: boolean;
}

const joinPath = (folder: string, name: string) => (folder === "" ? name : `${folder.replace(/\/+$/, "")}/${name}`);
const kb = (n: number) => (n < 1024 ? `${n}B` : `${Math.max(1, Math.round(n / 1024))}KB`);

export function SpecImportDialog({ open, onClose, initialName = "", loadFiles, blockedReason, onSubmit }: SpecImportDialogProps) {
  const [folder, setFolder] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [name, setName] = useState(initialName);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const folderRef = useRef<HTMLInputElement>(null);
  const uid = useId();
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const selected = (rows ?? []).filter((r) => r.checked);

  const load = async () => {
    setLoading(true);
    setFolderError(null);
    try {
      const listing = await loadFiles(folder.trim());
      setRows((listing.files ?? []).map((f) => ({ path: joinPath(listing.path ?? folder.trim(), f.name), name: f.name, size: f.size, checked: true })));
      setTruncated(listing.truncated === true);
    } catch (e) {
      setRows(null);
      const remote = e instanceof ApiError && e.code === ERROR_CODES.FOLDERS_REMOTE_DISABLED;
      const failure = classifySddError(e, m.problem.generic);
      setFolderError(remote ? m.import.remote : failure.kind === "generic" || failure.kind === "problem" ? failure.message : m.problem.generic);
    } finally {
      setLoading(false);
    }
  };

  const move = (index: number, delta: number) =>
    setRows((prev) => {
      if (prev === null) return prev;
      const to = index + delta;
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [item] = next.splice(index, 1);
      next.splice(to, 0, item as Row);
      return next;
    });

  const submit = async () => {
    if (busy || blocked || selected.length === 0 || name.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), files: selected.map((r) => r.path) as [string, ...string[]] });
    } catch (e) {
      setError(describeError(e, m.problem.generic).message);
      setBusy(false);
    }
  };
  const guardedClose = () => {
    if (!busy) onClose();
  };

  return (
    <Dialog
      open={open}
      title={m.import.title}
      onClose={guardedClose}
      size="lg"
      initialFocus={folderRef}
      actions={
        <>
          <span className="sdd-dialog-note app-muted">{m.import.summary(selected.length)}</span>
          <Button onClick={guardedClose} disabled={busy}>{m.cancel}</Button>
          <Button variant="primary" loading={busy} aria-disabled={blocked || selected.length === 0 || name.trim() === "" || undefined} title={blocked ? blockedReason : undefined} onClick={() => void submit()}>
            {busy ? m.import.submitting : m.import.submit}
          </Button>
        </>
      }
    >
      <div className="sdd-form">
        <p className="app-muted">{m.import.intro}</p>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <div className="sdd-field">
          <label className="sdd-label" htmlFor={`${uid}-folder`}>{m.import.folder}</label>
          <div className="sdd-inline">
            <input id={`${uid}-folder`} ref={folderRef} className="sdd-input sdd-mono" value={folder} placeholder={m.import.folderHint} onChange={(e) => setFolder(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) void load(); }} />
            <Button size="sm" loading={loading} onClick={() => void load()}>{m.import.load}</Button>
          </div>
          {folderError === null ? null : <span className="app-field-error" role="alert">{folderError}</span>}
        </div>
        {rows === null ? null : rows.length === 0 ? (
          <p className="app-muted" role="status">{m.import.noFiles}</p>
        ) : (
          <div className="sdd-field">
            <div className="sdd-inline">
              <Choice checked={selected.length === rows.length} onChange={(e) => setRows(rows.map((r) => ({ ...r, checked: e.target.checked })))}>{m.import.selectAll}</Choice>
              <span className="app-muted">{m.import.selected(rows.length, selected.length)}</span>
            </div>
            <ul className="sdd-files" aria-label={m.import.docs}>
              {rows.map((r, i) => (
                <li key={r.path} className="sdd-file">
                  <Choice checked={r.checked} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, checked: e.target.checked } : x)))}>
                    <span className="sdd-mono ac-ellipsis">{r.name}</span>
                  </Choice>
                  <span className="app-muted">{kb(r.size)}</span>
                  <Button size="sm" aria-label={`${r.name} ${m.import.moveUp}`} disabled={i === 0} onClick={() => move(i, -1)}>↑</Button>
                  <Button size="sm" aria-label={`${r.name} ${m.import.moveDown}`} disabled={i === rows.length - 1} onClick={() => move(i, 1)}>↓</Button>
                </li>
              ))}
            </ul>
            {truncated ? <p className="app-muted">{m.import.truncated}</p> : null}
          </div>
        )}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{m.import.name} *</span>
          <input id={`${uid}-name`} className="sdd-input" maxLength={SDD_LIMITS.nameMax} value={name} aria-required="true" onChange={(e) => setName(e.target.value)} />
        </label>
      </div>
    </Dialog>
  );
}
