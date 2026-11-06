/**
 * 문서 탭(screen-sdd §6): 문서 목록 + 편집기(저장 `If-Match`·외부 변경 충돌·파일 없음) + 상태 전환 메뉴.
 * 문서별 편집 내용은 이 탭이 열려 있는 동안 메모리에 남는다(문서를 오가도 잃지 않음). 본문·이름·상태 라벨은 서버 데이터다.
 */
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { Banner, Button } from "@agent-console/ui";
import { DocumentEditor, DocumentNav, GateNotice } from "@agent-console/sdd-view";
import type { SddGateBlockedDetails, SpecDocumentSummary } from "@agent-console/contracts/sdd";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { SDD_PARAMS, HUMAN_ACTOR, SDD_LIMITS, SECRET_SUSPECT_CODE } from "./sddConfig";
import { sddMessages as m, viewMessages } from "./messages";
import type { SddTabProps } from "./sddTabs";
import { sddKeys, useSddSpace, useSpecDocument } from "./useSddApi";
import { hasCode } from "./sddErrors";
import { FailureBlock, ListSkeleton, MenuButton } from "./parts";

const P = SDD_PARAMS;

type Draft = { text: string; baseHash: string | undefined };

export function DocumentsTab({ specId, view, ctx, params, setParams, goTab, ownHashes, refresh, reportDirty }: SddTabProps) {
  const space = useSddSpace();
  const qc = useQueryClient();
  const docs = useMemo(() => view.spec.documents ?? [], [view.spec.documents]);
  const states = useMemo(() => view.document_states ?? [], [view.document_states]);
  const stateLabel = (id: string) => states.find((s) => s.id === id)?.label ?? id;
  const summaries: SpecDocumentSummary[] = useMemo(
    () =>
      docs.map((d) => {
        const info = d.state === undefined || d.state === null ? undefined : states.find((s) => s.id === d.state);
        return { id: d.id, title: d.title, ...(d.state ? { state: d.state, state_label: info?.label ?? d.state, tone: info?.tone ?? null } : {}) };
      }),
    [docs, states],
  );
  const wanted = params.get(P.doc);
  const docId = docs.find((d) => d.id === wanted)?.id ?? docs[0]?.id ?? null;
  const doc = docs.find((d) => d.id === docId);
  const docQ = useSpecDocument(specId, docId);
  const [drafts, setDrafts] = useState<Readonly<Record<string, Draft | undefined>>>({});
  const [saving, setSaving] = useState(false);
  const [conflicts, setConflicts] = useState<Readonly<Record<string, true | undefined>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [transitionNote, setTransitionNote] = useState<string | null>(null);
  const [gate, setGate] = useState<SddGateBlockedDetails | null>(null);
  const wide = useMediaQuery(`(min-width: ${SDD_LIMITS.splitViewportMin}px)`);

  const server = docQ.data?.value;
  const serverHash = docQ.data?.version_hash ?? server?.content_hash;
  const draft = docId === null ? undefined : drafts[docId];
  const dirty = draft !== undefined;
  const value = draft?.text ?? server?.content ?? "";
  const externalChange = dirty && serverHash !== undefined && draft.baseHash !== undefined && serverHash !== draft.baseHash;
  const conflict = docId !== null && (conflicts[docId] === true || externalChange);
  const missing = hasCode(docQ.error, ERROR_CODES.SDD_DOCUMENT_MISSING);
  const dirtyIds = new Set(Object.entries(drafts).filter(([, d]) => d !== undefined).map(([id]) => id));
  const anyDirty = dirtyIds.size > 0;
  useEffect(() => {
    reportDirty("documents", anyDirty);
    return () => reportDirty("documents", false);
  }, [anyDirty, reportDirty]);

  const setDraft = (id: string, next: Draft | undefined) => setDrafts((prev) => ({ ...prev, [id]: next }));
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set(P.doc, id);
    next.delete(P.line);
    setParams(next, { replace: true });
    setFailure(null);
    setGate(null);
    setTransitionNote(null);
  };
  const onChange = (text: string) => {
    if (docId === null) return;
    if (server !== undefined && text === server.content && !dirty) return;
    setDraft(docId, { text, baseHash: draft?.baseHash ?? serverHash });
  };

  const save = async (expected: string | undefined) => {
    if (docId === null || doc === undefined) return;
    setSaving(true);
    setFailure(null);
    try {
      const saved = await space.client.putSpecDocument(specId, docId, value, expected === undefined ? {} : { expectedHash: expected });
      setDraft(docId, undefined);
      setConflicts((c) => ({ ...c, [docId]: undefined }));
      qc.setQueryData(sddKeys.doc(space.key, specId, docId), saved);
      void refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === ERROR_CODES.VERSION_CONFLICT) setConflicts((c) => ({ ...c, [docId]: true }));
      else if (e instanceof ApiError && e.code === ERROR_CODES.SDD_SECRET_REJECTED) {
        const lines = secretLines(e.details["issues"]);
        setFailure(m.doc.secretRejected(lines));
      } else setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.doc.saveFailed);
    } finally {
      setSaving(false);
    }
  };

  const reload = async () => {
    if (docId === null) return;
    setDraft(docId, undefined);
    setConflicts((c) => ({ ...c, [docId]: undefined }));
    await docQ.refetch();
  };
  const overwrite = async () => {
    const fresh = await docQ.refetch();
    await save(fresh.data?.version_hash ?? serverHash);
  };
  const createMissing = async () => {
    if (docId === null) return;
    try {
      await space.client.putSpecDocument(specId, docId, "", { createOnly: true });
      await docQ.refetch();
    } catch (e) {
      setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.doc.saveFailed);
    }
  };

  // ---- 상태 전환(사람이 할 수 있는 것만) ---------------------------------------------------------
  const current = doc?.state ?? null;
  const targets = useMemo(() => {
    const transitions = view.spec.rules?.transitions ?? [];
    const out = new Set<string>();
    for (const t of transitions) if ((t.from === current || t.from === "*") && (t.by ?? []).includes(HUMAN_ACTOR) && t.to !== current) out.add(t.to);
    return [...out];
  }, [view.spec.rules, current]);
  const transition = async (to: string) => {
    if (docId === null) return;
    setTransitionNote(null);
    setGate(null);
    try {
      const changed = await space.client.changeDocumentState(specId, docId, { to });
      if (changed.version_hash !== undefined) ownHashes.current.add(changed.version_hash);
      qc.setQueryData(sddKeys.spec(space.key, specId), changed);
      void qc.invalidateQueries({ queryKey: sddKeys.specs(space.key) });
      setTransitionNote(m.doc.stateChanged(stateLabel(to)));
    } catch (e) {
      if (e instanceof ApiError && e.code === ERROR_CODES.SDD_GATE_BLOCKED) setGate(e.details as unknown as SddGateBlockedDetails);
      else setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.problem.generic);
    }
  };
  const blockedTransition = ctx.readOnly ? ctx.readOnlyReason : dirty ? m.doc.saveFirst : undefined;
  const onEdit = states.length === 0 || current === null ? undefined : (view.spec.rules?.document_states ?? []).find((s) => s.id === current)?.on_edit?.to;
  const transitionMenu =
    states.length === 0 ? null : targets.length === 0 ? (
      <span className="app-muted">{m.doc.noTransition}</span>
    ) : targets.length <= 2 ? (
      <>
        {targets.map((to) => (
          <Button key={to} size="sm" aria-disabled={blockedTransition !== undefined || undefined} title={blockedTransition} onClick={() => { if (blockedTransition === undefined) void transition(to); }}>
            {m.doc.transitionTo(stateLabel(to))}
          </Button>
        ))}
      </>
    ) : (
      <MenuButton
        label={`${m.doc.changeState} ▾`}
        panelLabel={m.doc.changeState}
        blockedReason={blockedTransition}
        items={targets.map((to) => ({ id: to, label: m.doc.transitionTo(stateLabel(to)), onSelect: () => void transition(to) }))}
      />
    );

  const secret = (docQ.data?.value.issues ?? []).filter((i) => i.code === SECRET_SUSPECT_CODE);

  if (docs.length === 0) {
    return (
      <div className="sdd-state" data-testid="sdd-no-docs">
        <p role="status">{m.doc.noDocs}</p>
        <button type="button" className="app-link-btn" onClick={() => goTab("rules")}>{m.doc.noDocsAction}</button>
      </div>
    );
  }

  return (
    <div className="sdd-docs">
      <div className="sdd-docs-nav">
        <DocumentNav documents={summaries} selectedId={docId} onSelect={(d) => select(d.id)} messages={viewMessages} />
        {dirtyIds.size > 0 ? <p className="app-muted" role="status">{m.doc.unsaved}: {[...dirtyIds].map((id) => docs.find((d) => d.id === id)?.title ?? id).join(", ")}</p> : null}
        <p className="app-muted sdd-docs-foot">
          {m.doc.listFooter}{" "}
          <button type="button" className="app-link-btn" onClick={() => goTab("rules")}>{m.doc.openRules}</button>
        </p>
      </div>
      <div className="sdd-docs-main">
        {docQ.isPending ? <ListSkeleton rows={10} /> : null}
        {docQ.isError && !missing ? <FailureBlock error={docQ.error} title={m.doc.readFail} onRetry={() => void docQ.refetch()} /> : null}
        {transitionNote === null ? null : <p role="status" className="sdd-note">{transitionNote}</p>}
        {gate === null ? null : <GateNotice details={gate} documentTitles={Object.fromEntries(docs.map((d) => [d.id, d.title]))} onOpenDocument={(id) => select(id)} onDismiss={() => setGate(null)} messages={viewMessages} />}
        {failure === null ? null : <Banner tone="danger">{failure}</Banner>}
        {dirty && onEdit !== undefined ? <p className="sdd-note" role="status">{m.doc.onEditWarn(stateLabel(onEdit))}</p> : null}
        {externalChange ? <p className="sdd-note" role="status">{m.doc.externalDirty}</p> : null}
        {!docQ.isPending && (!docQ.isError || missing) ? (
          <DocumentEditor
            key={docId ?? ""}
            document={doc === undefined ? null : { id: doc.id, title: doc.title, file: doc.file }}
            value={value}
            onChange={onChange}
            onSave={() => void save(draft?.baseHash ?? serverHash)}
            dirty={dirty}
            saving={saving}
            readOnly={ctx.readOnly}
            {...(ctx.readOnlyReason === undefined ? {} : { readOnlyReason: ctx.readOnlyReason })}
            missing={missing}
            onCreateMissing={() => void createMissing()}
            conflict={conflict}
            onReload={() => void reload()}
            onOverwrite={() => void overwrite()}
            issues={secret.length > 0 ? secret : []}
            defaultMode={wide ? "split" : "edit"}
            {...(typeof ctx.info?.limits.max_doc_bytes === "number" ? { maxBytes: ctx.info.limits.max_doc_bytes } : {})}
            toolbarExtra={transitionMenu}
            messages={viewMessages}
          />
        ) : null}
        {secret.length > 0 ? <span className="ac-sr-only">{m.doc.secretSuspect(secret.length, secret.map((i) => i.line).filter((l) => l !== null && l !== undefined).join(", "))}</span> : null}
      </div>
    </div>
  );
}

/** 서버가 준 비밀 거부 이슈(`details.issues`)에서 줄 번호만 뽑는다(값은 없다). */
function secretLines(raw: unknown): string {
  if (!Array.isArray(raw)) return "";
  return raw
    .map((i) => (typeof i === "object" && i !== null ? (i as { line?: unknown }).line : undefined))
    .filter((l): l is number => typeof l === "number")
    .join(", ");
}
