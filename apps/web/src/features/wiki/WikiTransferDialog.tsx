/**
 * 폴더 압축 파일(zip) 내보내기·가져오기 대화상자(screen-wiki §4.6). 데이터와 동작은 props다.
 * 가져오기는 파일을 고르면 자동으로 `dry_run`을 돌려 결과 표(경로·상태 칩·사유)를 보이고 [가져오기]로 확정한다.
 * 상태(`status`)는 열린 문자열이라 표에 없으면 원문 + 중립 톤이다. 사유는 서버 이슈 메시지 그대로다.
 */
import { useEffect, useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { KNOWN_WIKI_IMPORT_STATUSES } from "@agent-console/contracts/constants";
import { ToneChip } from "@agent-console/markdown-doc";
import { VirtualList } from "@agent-console/wiki-view";
import type { WikiImportItem, WikiImportResult, WikiSummary } from "@agent-console/contracts/wiki";
import { describeError } from "../../app/errors";
import { IMPORT_POLICIES, importStatusDisplay } from "./wikiConfig";
import { wikiMessages as m } from "./messages";

export interface ExportDialogProps {
  open: boolean;
  onClose: () => void;
  name: string;
  /** 페이지 수(모르면 null) */
  pages: number | null;
  onDownload: () => Promise<void>;
}

export function WikiExportDialog({ open, onClose, name, pages, onDownload }: ExportDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await onDownload();
      onClose();
    } catch (e) {
      setError(describeError(e, m.transfer.exportFailed).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} title={m.transfer.exportTitle} onClose={onClose} actions={<><Button onClick={onClose}>{m.cancel}</Button><Button variant="primary" aria-disabled={busy || undefined} onClick={() => void go()}>{m.transfer.download}</Button></>}>
      <p>{m.transfer.exportBody(name, pages)}</p>
      {error === null ? null : <p className="app-field-error" role="alert">{error}</p>}
    </Dialog>
  );
}

export interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
  /** 대상 위키 후보. 하나면 읽기 전용으로 보인다 */
  wikis: readonly WikiSummary[];
  initialWiki?: string | undefined;
  /** 쓰기를 막는 이유(읽기 전용·폴더 문제). 있으면 확정이 막힌다 */
  blockedReason?: string | undefined;
  /** zip을 서버에 보내 결과를 받는다(`dryRun`이면 쓰지 않는다) */
  run: (wiki: string, zip: Uint8Array, policy: string, dryRun: boolean) => Promise<WikiImportResult>;
  /** 확정이 끝났을 때(가져온 페이지 수) */
  onDone: (wiki: string, imported: number) => void;
}

const ok = (i: WikiImportItem) => i.status !== KNOWN_WIKI_IMPORT_STATUSES.REJECTED && i.status !== KNOWN_WIKI_IMPORT_STATUSES.SKIPPED;

export function WikiImportDialog({ open, onClose, wikis, initialWiki, blockedReason, run, onDone }: ImportDialogProps) {
  const [wiki, setWiki] = useState(initialWiki ?? wikis[0]?.id ?? "");
  const [file, setFile] = useState<{ name: string; bytes: Uint8Array } | null>(null);
  const [policy, setPolicy] = useState(IMPORT_POLICIES[0]?.id ?? "");
  const [result, setResult] = useState<WikiImportResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const seq = useRef(0);
  const blocked = blockedReason !== undefined && blockedReason !== "";

  // 파일·정책·대상이 바뀌면 자동으로 dry_run을 돌린다(앞 요청의 결과는 버린다)
  useEffect(() => {
    if (!open || file === null || wiki === "") return;
    const mine = ++seq.current;
    let cancelled = false;
    void (async () => {
      setChecking(true);
      setError(null);
      try {
        const r = await run(wiki, file.bytes, policy, true);
        if (!cancelled && mine === seq.current) setResult(r);
      } catch (e) {
        if (!cancelled && mine === seq.current) {
          setResult(null);
          setError(describeError(e, m.transfer.failed).message);
        }
      } finally {
        if (mine === seq.current) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, file, wiki, policy, run]);

  const items = result?.items ?? [];
  const counts = { ok: items.filter(ok).length, skip: items.filter((i) => i.status === KNOWN_WIKI_IMPORT_STATUSES.SKIPPED).length, reject: items.filter((i) => i.status === KNOWN_WIKI_IMPORT_STATUSES.REJECTED).length };
  const pick = async (f: File | undefined) => {
    if (f === undefined) return;
    setFile({ name: f.name, bytes: new Uint8Array(await f.arrayBuffer()) });
    setResult(null);
  };
  const confirm = async () => {
    if (file === null || busy || blocked) return;
    setBusy(true);
    setError(null);
    try {
      const r = await run(wiki, file.bytes, policy, false);
      onDone(wiki, (r.items ?? []).filter(ok).length);
    } catch (e) {
      setError(describeError(e, m.transfer.failed).message);
    } finally {
      setBusy(false);
    }
  };
  const reasonOf = (i: WikiImportItem): string => {
    const msgs = (i.issues ?? []).map((x) => x.message).filter((s) => s !== "");
    return [i.to ? `→ ${i.to}` : "", ...msgs].filter((s) => s !== "").join(" · ");
  };
  return (
    <Dialog
      open={open}
      title={m.transfer.importTitle}
      size="lg"
      onClose={() => {
        if (!busy) onClose();
      }}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>{m.cancel}</Button>
          <Button variant="primary" aria-disabled={file === null || checking || busy || blocked || counts.ok === 0 || undefined} title={blocked ? blockedReason : undefined} onClick={() => void confirm()}>
            {m.transfer.submit}
          </Button>
        </>
      }
    >
      <div className="wiki-form">
        {wikis.length === 0 ? <p className="app-muted">{m.transfer.noWiki}</p> : (
          <label className="wiki-field">
            <span className="wiki-label">{m.transfer.importWiki}</span>
            <select className="wiki-input" value={wiki} disabled={wikis.length === 1} onChange={(e) => setWiki(e.target.value)}>
              {wikis.map((w) => <option key={w.id} value={w.id}>{w.name && w.name !== "" ? w.name : w.id}</option>)}
            </select>
          </label>
        )}
        <div className="wiki-drop">
          <span>{file === null ? m.transfer.drop : m.transfer.chosen(file.name)}</span>
          <input ref={input} type="file" accept=".zip,application/zip" className="ac-sr-only" tabIndex={-1} aria-label={m.transfer.pick} onChange={(e) => void pick(e.target.files?.[0])} />
          <Button size="sm" onClick={() => input.current?.click()}>{m.transfer.pick}</Button>
        </div>
        <fieldset className="wiki-field">
          <legend className="wiki-label">{m.transfer.policy}</legend>
          <div className="wiki-radio-row">
            {IMPORT_POLICIES.map((p) => (
              <label key={p.id} className="ac-choice">
                <input type="radio" name="wiki-import-policy" checked={policy === p.id} onChange={() => setPolicy(p.id)} />
                <span>{m.transfer.policies[p.labelKey] ?? p.id}</span>
              </label>
            ))}
          </div>
          {IMPORT_POLICIES.find((p) => p.id === policy)?.destructive === true ? <span className="wiki-hint wiki-danger-text">{m.transfer.overwriteWarn}</span> : null}
        </fieldset>
        {error === null ? null : <p className="app-field-error" role="alert">{error}</p>}
        {checking ? <p className="app-muted" role="status">{m.transfer.checking}</p> : null}
        {result === null ? null : (
          <>
            <p role="status" data-testid="wiki-import-summary">{m.transfer.summary(counts.ok, counts.skip, counts.reject)}</p>
            <div className="wiki-import-head" aria-hidden="true"><span>{m.transfer.colPath}</span><span>{m.transfer.colStatus}</span><span>{m.transfer.colReason}</span></div>
            <VirtualList
              items={items}
              rowHeight={32}
              height={Math.min(240, Math.max(32, items.length * 32))}
              getKey={(i, n) => `${n}:${i.path}`}
              ariaLabel={m.transfer.importTitle}
              renderRow={(i, ctx) => {
                const d = importStatusDisplay(i.status);
                return (
                  <div key={ctx.index} className="wiki-import-row" role="listitem" style={ctx.style}>
                    <span className="ac-mono-wrap ac-ellipsis" title={i.path}>{i.path}</span>
                    <ToneChip label={d.label} tone={d.tone} />
                    <span className="ac-ellipsis app-muted" title={reasonOf(i)}>{reasonOf(i)}</span>
                  </div>
                );
              }}
            />
          </>
        )}
      </div>
    </Dialog>
  );
}
