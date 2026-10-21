import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ImportCandidate, ImportPreview, ImportResult } from "@agent-console/contracts";
import { Banner, Button, Dialog, Tag } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { formatCount } from "../../lib/format";
import { useResourceTypes, Skeleton } from "../settings";
import { useImportSources, useInvalidateLists, DescriptorIcon, DEFINITION_KINDS, libraryMessages as lm } from "../library";
import { resourceMessages as t } from "./messages";
import { buildImportItems, isSecretWarning } from "./resourceLogic";
import { isImeKeyEvent } from "../../lib/ime";

type Step = "source" | "items" | "result";
const STEPS: readonly Step[] = ["source", "items", "result"];

export interface ImportDialogProps {
  onClose: () => void;
  /** 결과의 [가져온 항목 보기]: 가져온 리소스 id들 */
  onShowImported: (ids: readonly string[]) => void;
}

type PreviewState = { status: "idle" } | { status: "loading" } | { status: "error"; message: string } | { status: "ready"; preview: ImportPreview };

function sizeText(size: number | null | undefined): string {
  if (size == null) return "–";
  return size < 1024 ? `${formatCount(size)} B` : `${formatCount(Math.round(size / 1024))} KB`;
}

/**
 * `.claude` 가져오기 위저드: ① 출처(서버 디스크립터 목록) ② 항목 ③ 결과.
 * 원본은 읽기만 하며 선택한 항목을 workspace로 복사한다. 출처 id·종류 이름은 코드에 없다.
 */
export function ImportDialog({ onClose, onShowImported }: ImportDialogProps) {
  const { rest } = useApi();
  const invalidate = useInvalidateLists();
  const sources = useImportSources();
  const types = useResourceTypes();
  const [step, setStep] = useState<Step>("source");
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState>({ status: "idle" });
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [policies, setPolicies] = useState<Record<string, string>>({});
  const [kindFilter, setKindFilter] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const body = useRef<HTMLDivElement>(null);
  // 단계가 바뀌면 눌렀던 버튼이 사라져 포커스가 대화상자 밖으로 빠진다 -> 본문으로 옮겨 Esc·Tab이 계속 동작하게 한다
  useEffect(() => {
    body.current?.focus();
  }, [step]);

  const source = (sources.data ?? []).find((s) => s.id === sourceId);
  const typeTitle = (id: string | null | undefined) => (types.data ?? []).find((x) => x.id === id);
  const candidates = preview.status === "ready" ? (preview.preview.candidates ?? []) : [];
  const keyOf = (c: ImportCandidate) => c.resource_type ?? c.kind;
  const kinds = [...new Set(candidates.map(keyOf))];
  const shown = candidates.filter((c) => kindFilter === null || keyOf(c) === kindFilter);

  const scan = async (id: string) => {
    setStep("items");
    setPreview({ status: "loading" });
    setSelected(new Set());
    setPolicies({});
    setKindFilter(null);
    try {
      const got = await rest.previewImport({ source: id });
      setPreview({ status: "ready", preview: got });
    } catch (e) {
      setPreview({ status: "error", message: describeError(e, t.import.scanFailed).message });
    }
  };

  const run = async () => {
    if (sourceId === null || selected.size === 0) return;
    setBusy(true);
    setImportError(null);
    try {
      const done = await rest.importResources({ source: sourceId, items: buildImportItems(candidates, selected, policies) });
      setResult(done);
      setStep("result");
      await invalidate();
    } catch (e) {
      setImportError(describeError(e, t.import.importFailed).message);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string, on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const allShownSelected = shown.length > 0 && shown.every((c) => selected.has(c.id));
  const selectAll = (on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur);
      for (const c of shown) {
        if (on) next.add(c.id);
        else next.delete(c.id);
      }
      return next;
    });

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (step !== "items" || isImeKeyEvent(e)) return;
    // 글자 입력 칸 안의 Ctrl+A는 글자 선택 그대로 둔다(체크 상자·표에서만 전체 선택)
    const typing = e.target instanceof HTMLElement && e.target.matches('input:not([type="checkbox"]), textarea, select');
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && !typing) {
      e.preventDefault();
      selectAll(!allShownSelected);
    }
  };

  const applied = result?.items ?? [];
  const importedResources = applied.filter((i) => i.kind !== DEFINITION_KINDS.agent && (i.action === "created" || i.action === "renamed" || i.action === "overwritten"));
  const importedAgents = applied.filter((i) => i.kind === DEFINITION_KINDS.agent && (i.action === "created" || i.action === "renamed" || i.action === "overwritten"));
  const failed = applied.filter((i) => i.action === "failed");
  const skipped = applied.filter((i) => i.action === "skipped");

  const actions =
    step === "source" ? (
      <>
        <Button onClick={onClose}>{lm.cancel}</Button>
        <Button variant="primary" disabled={source === undefined || source.available === false} onClick={() => sourceId !== null && void scan(sourceId)}>
          {t.import.next}
        </Button>
      </>
    ) : step === "items" ? (
      <>
        <Button onClick={() => setStep("source")}>{t.import.back}</Button>
        <Button variant="primary" loading={busy} disabled={selected.size === 0 || preview.status !== "ready"} onClick={() => void run()}>
          {t.import.doImport} {selected.size > 0 ? `(${t.import.selectedCount(selected.size)})` : ""}
        </Button>
      </>
    ) : (
      <>
        {importedResources.length > 0 ? (
          <Button
            onClick={() => {
              onShowImported(importedResources.map((i) => i.target_id ?? i.id));
              onClose();
            }}
          >
            {t.import.viewImported}
          </Button>
        ) : null}
        <Button variant="primary" onClick={onClose}>{t.import.close}</Button>
      </>
    );

  return (
    <Dialog open title={t.import.title} onClose={onClose} wide actions={actions}>
      <div ref={body} tabIndex={-1} className="lib-form res-import-body" onKeyDown={onKeyDown}>
        <ol className="res-import-steps" aria-label={t.import.title}>
          {STEPS.map((s, i) => (
            <li key={s} aria-current={s === step ? "step" : undefined}>
              {i + 1}. {t.import.steps[s]}
            </li>
          ))}
        </ol>
        <Banner tone="info">{t.import.readOnlyNote}</Banner>

        {step === "source" ? (
          sources.isLoading ? (
            <Skeleton rows={2} />
          ) : sources.isError ? (
            <ErrorBlock title={t.import.sourcesFailed} message={sources.error.message} retryLabel={lm.retry} onRetry={() => void sources.refetch()} />
          ) : (sources.data ?? []).length === 0 ? (
            <p className="app-muted">{t.import.noSources}</p>
          ) : (
            <div role="radiogroup" aria-label={t.import.steps.source} className="res-card-grid">
              {(sources.data ?? []).map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={sourceId === s.id}
                  className="res-card"
                  disabled={s.available === false}
                  onClick={() => setSourceId(s.id)}
                >
                  <span className="res-card-title">{s.title}</span>
                  {s.description ? <span className="app-muted lib-field-note">{s.description}</span> : null}
                  {s.path ? <span className="lib-mono app-wrap">{t.import.path}: {s.path}</span> : null}
                  {s.available === false ? <Tag>{t.import.unavailable}</Tag> : null}
                </button>
              ))}
            </div>
          )
        ) : null}

        {step === "items" ? (
          preview.status === "loading" ? (
            <div>
              <p className="app-muted" role="status">{t.import.scanning}</p>
              <Skeleton rows={4} />
            </div>
          ) : preview.status === "error" ? (
            <ErrorBlock title={t.import.scanFailed} message={preview.message} retryLabel={lm.retry} onRetry={() => sourceId !== null && void scan(sourceId)} />
          ) : candidates.length === 0 ? (
            <div>
              <p className="app-muted">{t.import.noItems(preview.status === "ready" ? (preview.preview.root ?? source?.path ?? "") : "")}</p>
              <Button onClick={() => setStep("source")}>{t.import.otherSource}</Button>
            </div>
          ) : (
            <>
              {importError ? <Banner tone="danger">{importError}</Banner> : null}
              <p className="app-muted lib-field-note">{t.import.secretNote}</p>
              <div className="lib-chips" role="group" aria-label={t.import.filterKind}>
                <button type="button" className="lib-chip" aria-pressed={kindFilter === null} onClick={() => setKindFilter(null)}>
                  {t.list.all}
                </button>
                {kinds.map((k) => (
                  <button key={k} type="button" className="lib-chip" aria-pressed={kindFilter === k} onClick={() => setKindFilter(kindFilter === k ? null : k)}>
                    {typeTitle(k)?.title ?? k}
                  </button>
                ))}
              </div>
              <div className="lib-table-wrap">
                <table className="lib-grid" aria-label={t.import.steps.items}>
                  <thead>
                    <tr>
                      <th>
                        <input type="checkbox" aria-label={t.import.selectAll} checked={allShownSelected} onChange={(e) => selectAll(e.target.checked)} />
                      </th>
                      <th>{t.import.itemKind}</th>
                      <th>{t.import.itemName}</th>
                      <th>{t.import.itemPath}</th>
                      <th>{t.import.itemSize}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((c) => {
                      const type = typeTitle(c.resource_type);
                      const isAgent = c.kind === DEFINITION_KINDS.agent;
                      const secret = (c.warnings ?? []).some((w) => isSecretWarning(w.code));
                      const open = expanded.has(c.id);
                      return (
                        <tr key={c.id}>
                          <td>
                            <input type="checkbox" aria-label={t.import.rowSelect(c.name)} checked={selected.has(c.id)} onChange={(e) => toggle(c.id, e.target.checked)} />
                          </td>
                          <td>
                            <span className="lib-row-main">
                              {isAgent ? null : <DescriptorIcon hint={type?.ui_hints?.icon} title={type?.title ?? c.kind} size={16} />}
                              {isAgent ? <Tag>{t.import.agentChip}</Tag> : <span>{type?.title ?? c.resource_type ?? c.kind}</span>}
                            </span>
                          </td>
                          <td>
                            <div>{c.name}</div>
                            <div className="lib-row-main">
                              {c.conflict ? (
                                <>
                                  <Tag>{t.import.conflictChip}</Tag>
                                  <select
                                    aria-label={`${c.name} ${t.import.conflictPolicy}`}
                                    value={policies[c.id] ?? "rename"}
                                    onChange={(e) => setPolicies((cur) => ({ ...cur, [c.id]: e.target.value }))}
                                  >
                                    {(["rename", "skip"] as const).map((p) => (
                                      <option key={p} value={p}>
                                        {t.import.policies[p]}
                                      </option>
                                    ))}
                                  </select>
                                </>
                              ) : null}
                              {secret ? <Tag data-tone="warning">▲ {t.import.secretChip}</Tag> : null}
                              {(c.warnings ?? []).length > 0 ? (
                                <button type="button" className="app-link-btn" aria-expanded={open} onClick={() => setExpanded((cur) => { const n = new Set(cur); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); return n; })}>
                                  {open ? "▾" : "▸"} {(c.warnings ?? []).length}
                                </button>
                              ) : null}
                            </div>
                            {open
                              ? (c.warnings ?? []).map((w, i) => (
                                  <p key={`${w.code}:${i}`} className="app-muted lib-field-note">
                                    {w.message} {w.keys && w.keys.length > 0 ? t.import.warningKeys(w.keys) : ""}
                                  </p>
                                ))
                              : null}
                          </td>
                          <td className="lib-mono lib-cell-clip" title={c.path}>{c.path}</td>
                          <td className="ac-num">{sizeText(c.size)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )
        ) : null}

        {step === "result" ? (
          <div className="lib-form" role="status">
            <p className="ac-text">{t.import.summary(importedResources.length, importedAgents.length)}</p>
            {skipped.length > 0 ? <p className="app-muted">{t.import.skipped(skipped.length)}</p> : null}
            {failed.length > 0 ? (
              <>
                <h3 className="app-block-subtitle">{t.import.failedItems}</h3>
                <ul className="lib-ref-list">
                  {failed.map((f, i) => (
                    <li key={`${i}:${f.id}`}>
                      {f.id}: {f.error ?? ""}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
