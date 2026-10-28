/**
 * 가져오기 대화상자: ① zip 파일(고르기·끌어다 놓기) ② 같은 키가 있을 때의 정책 → [미리보기](쓰지 않고 수만 센다, 선택) → [가져오기] → 결과.
 * zip 바이트를 그대로 본문으로 보낸다. 오류 목록에는 파일 경로·코드·서버 메시지만 있고, 비밀 거부는 값·위치 없이 코드와 사유만 보인다.
 */
import { useRef, useState, type DragEvent } from "react";
import { Banner, Button, Choice, Dialog, Icon, StatusIcon } from "@agent-console/ui";
import { ERROR_CODES } from "@agent-console/contracts/constants";
import type { MemoryImportProblem, MemoryImportResult } from "@agent-console/contracts/memory";
import { formatBytes } from "@agent-console/memory-view";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { sizeMessages } from "./format";
import { DEFAULT_IMPORT_POLICY, IMPORT_POLICIES } from "./memoryConfig";
import { memoryMessages as t } from "./messages";

export interface ImportDialogProps {
  onClose: () => void;
  /** 결과 화면에서 [메모리에서 보기] — 쓴 주체가 정리·가져오기인 항목으로 필터 */
  onViewImported: () => void;
  /** 가져오기가 끝났다(결과 화면이 뜰 때) — 표·나무를 다시 읽게 한다 */
  onImported: () => void;
}

interface Preview {
  result: MemoryImportResult;
  policy: string;
  file: File;
}

function ProblemList({ problems }: { problems: readonly MemoryImportProblem[] }) {
  return (
    <ul className="mem-issue-list" aria-label={t.import.errorList}>
      {problems.map((p, i) => (
        <li key={`${p.path}-${i}`}>
          <StatusIcon status="failed" kind="run" size={14} />
          <span className="mem-mono mem-issue-path" title={p.path}>{p.path}</span>
          <span className="mem-mono mem-muted">{p.code}</span>
          <span>{p.code === ERROR_CODES.MEMORY_SECRET_REJECTED ? t.import.secretReason : (p.message ?? "")}</span>
        </li>
      ))}
    </ul>
  );
}

export function ImportDialog({ onClose, onViewImported, onImported }: ImportDialogProps) {
  const { rest } = useApi();
  const [file, setFile] = useState<File | null>(null);
  const [policy, setPolicy] = useState(DEFAULT_IMPORT_POLICY);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MemoryImportResult | null>(null);
  const [dragging, setDragging] = useState(false);
  const token = useRef(0);
  const input = useRef<HTMLInputElement>(null);
  const pickRef = useRef<HTMLButtonElement>(null);

  const pick = (next: File | null) => {
    setError(null);
    if (next !== null && !next.name.toLowerCase().endsWith(".zip")) {
      setError(t.import.notZip);
      return;
    }
    setFile(next);
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0] ?? null);
  };

  const run = async (dryRun: boolean) => {
    if (file === null || busy !== null) return;
    const mine = ++token.current;
    setBusy(dryRun ? "preview" : "import");
    setError(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const out = await rest.importMemory(bytes, { policy, dryRun });
      if (token.current !== mine) return; // 취소한 요청의 응답은 버린다
      if (dryRun) {
        if (out.dry_run !== true) setError(t.import.previewInvalid);
        else setPreview({ result: out, policy, file });
      } else {
        setResult(out);
        onImported();
      }
    } catch (e) {
      if (token.current === mine) setError(describeError(e, t.import.failed).message);
    } finally {
      if (token.current === mine) setBusy(null);
    }
  };
  const cancelRequest = () => {
    token.current += 1;
    setBusy(null);
  };

  if (result !== null) {
    const errors = result.errors ?? [];
    const secrets = errors.filter((x) => x.code === ERROR_CODES.MEMORY_SECRET_REJECTED).length;
    const ok = errors.length === 0;
    return (
      <Dialog
        open
        size="lg"
        title={t.import.resultTitle}
        onClose={onClose}
        actions={
          <>
            <Button onClick={onViewImported}>{t.import.viewImported}</Button>
            <Button variant="primary" onClick={onClose}>{t.close}</Button>
          </>
        }
      >
        <Banner tone={ok ? "success" : "warning"} title={ok ? t.import.allOk : t.import.partial}>
          <span className="mem-counts">
            <span>{t.import.created(result.created ?? 0)}</span>
            <span>{t.import.overwritten(result.overwritten ?? 0)}</span>
            {(result.renamed ?? 0) > 0 ? <span>{t.import.renamed(result.renamed ?? 0)}</span> : null}
            <span>{t.import.skipped(result.skipped ?? 0)}</span>
            <span>{t.import.errors(errors.length)}</span>
            {secrets > 0 ? <span>{t.import.secretCount(secrets)}</span> : null}
          </span>
        </Banner>
        {errors.length > 0 ? <ProblemList problems={errors} /> : null}
      </Dialog>
    );
  }

  const stale = preview !== null && (preview.policy !== policy || preview.file !== file);
  const previewErrors = preview?.result.errors ?? [];
  const overwritten = preview?.result.overwritten ?? 0;
  const policyName = (id: string) => t.import.policies[id]?.label ?? id;
  return (
    <Dialog
      open
      size="lg"
      title={t.import.title}
      onClose={busy === null ? onClose : cancelRequest}
      initialFocus={pickRef}
      actions={
        <>
          {busy !== null ? <span className="mem-help">{t.import.cancelNote}</span> : null}
          <Button onClick={busy === null ? onClose : cancelRequest}>{busy === null ? t.cancel : t.import.cancelRequest}</Button>
          <Button disabled={file === null || busy !== null} loading={busy === "preview"} onClick={() => void run(true)}>{preview === null ? t.import.preview : t.import.previewAgain}</Button>
          <Button variant="primary" disabled={file === null || busy !== null} loading={busy === "import"} onClick={() => void run(false)}>{t.import.submit}</Button>
        </>
      }
    >
      <div className="mem-form">
        <div className="mem-field">
          <span className="mem-label">{t.import.fileLabel}</span>
          <div
            className="mem-drop"
            data-drag={dragging ? "" : undefined}
            onDragOver={(e) => (e.preventDefault(), setDragging(true))}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input ref={input} type="file" accept=".zip,application/zip" hidden aria-label={t.import.pickFile} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            <Button ref={pickRef} onClick={() => input.current?.click()}>{t.import.pickFile}</Button>
            <span className="mem-muted">{t.import.drop}</span>
            {file !== null ? (
              <span className="mem-file">
                <span className="mem-mono ac-ellipsis" title={file.name}>{file.name}</span> · {formatBytes(file.size, sizeMessages)}
                <button type="button" className="mem-iconbtn" aria-label={t.import.removeFile} title={t.import.removeFile} onClick={() => (pick(null), setPreview(null))}>
                  <Icon name="close" />
                </button>
              </span>
            ) : null}
          </div>
        </div>
        <fieldset className="mem-policy">
          <legend className="mem-label">{t.import.policy}</legend>
          {IMPORT_POLICIES.map((p) => {
            const text = t.import.policies[p.id];
            return (
              <Choice key={p.id} kind="radio" name="mem-import-policy" checked={policy === p.id} onChange={() => setPolicy(p.id)}>
                <strong>{text?.label ?? p.id}</strong>
                <span className="mem-help"> {text?.help ?? ""}</span>
                {p.warns && text?.warn !== undefined ? (
                  <span className="mem-warn mem-warn-line"><span className="mem-mark" aria-hidden="true" /> {text.warn}</span>
                ) : null}
              </Choice>
            );
          })}
          {policy !== "" && IMPORT_POLICIES.find((p) => p.id === policy)?.warns === true ? <span className="mem-help">{t.import.undoHint}</span> : null}
        </fieldset>
        <p className="mem-help">{t.import.note}</p>
        {error !== null ? <Banner tone="danger">{error}</Banner> : null}
        {preview !== null ? (
          <section className="mem-preview" data-stale={stale ? "" : undefined} aria-label={t.import.previewTitle(policyName(preview.policy))}>
            <h3 className="mem-preview-title">{t.import.previewTitle(policyName(preview.policy))}</h3>
            <p className="mem-sr" aria-live="polite">
              {t.import.previewSummary(preview.result.created ?? 0, preview.result.overwritten ?? 0, preview.result.skipped ?? 0, previewErrors.length)}
            </p>
            <span className="mem-counts">
              <span>{t.import.previewCreated(preview.result.created ?? 0)}</span>
              <span>{t.import.previewOverwritten(overwritten)}</span>
              <span>{t.import.previewRenamed(preview.result.renamed ?? 0)}</span>
              <span>{t.import.previewSkipped(preview.result.skipped ?? 0)}</span>
              <span>{t.import.previewErrors(previewErrors.length)}</span>
            </span>
            {overwritten > 0 ? <p className="mem-warn"><span className="mem-mark" aria-hidden="true" /> {t.import.previewOverwriteWarn(overwritten)}</p> : null}
            {stale ? <p className="mem-help" role="status">{t.import.previewStale}</p> : null}
            {previewErrors.length > 0 ? <ProblemList problems={previewErrors} /> : null}
            <p className="mem-help">{t.import.previewNote}</p>
          </section>
        ) : null}
      </div>
    </Dialog>
  );
}
