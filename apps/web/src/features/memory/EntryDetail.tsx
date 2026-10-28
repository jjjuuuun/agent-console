/**
 * 항목 상세: 머리(키·저장 상태·동작) / 띠 / 정보(접힘) / 본문 편집기 / 상태 줄.
 * 서버 값과 초안은 `useEntryEditor`가, 그림은 `@agent-console/memory-view`가 맡고 이 컴포넌트는 둘을 잇는다.
 */
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { Banner, Button, Disclosure, Icon, IconButton, Menu, Popover, Spinner, StatusIcon } from "@agent-console/ui";
import type { MemoryEntry, MemoryScopeKindInfo, MemoryScopeRef } from "@agent-console/contracts/memory";
import { MemoryEntryEditor, MemoryEntryMeta, scopeLabel, type MemoryEntryEditorHandle, type ScopeLabel } from "@agent-console/memory-view";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { useStorage } from "../../app/StorageContext";
import { relativeTime, viewMessages } from "./format";
import { MEMORY_LIMITS, MEMORY_STORAGE } from "./memoryConfig";
import { memoryMessages as t } from "./messages";
import { SecretBand } from "./SecretBand";
import { ConflictDialog } from "./ConflictDialog";
import { useEntryEditor } from "./useEntryEditor";
import type { MemoryContext } from "./useMemoryContext";
import type { MemoryLimits } from "./useMemoryApi";

/** 밖에서 부르는 동작: 저장(이탈 확인의 "저장하고 이동"), 초안 버리기. */
export interface EntryDetailHandle {
  save: () => Promise<boolean>;
  discard: () => void;
}

export interface EntryDetailProps {
  id: string;
  /** 목록에서 이미 아는 키(상세를 불러오는 동안 머리에 먼저 보인다) */
  knownKey?: string;
  kinds: readonly MemoryScopeKindInfo[];
  ctx: MemoryContext;
  limits: MemoryLimits;
  /** 현재 필터에 맞는가(안 맞으면 머리 아래 안내 한 줄) */
  inFilter: boolean;
  /** 2칸 모드면 머리에 [✕] */
  closable: boolean;
  /** 형식 입력 제안(현재 범위에서 쓰인 값) */
  contentTypeSuggestions: readonly string[];
  /** 실행 열기(역할이 있을 때만) */
  onOpenRun?: ((runId: string) => void) | undefined;
  onClose: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onHistory: (entry: MemoryEntry, dirty: boolean) => void;
  onMove: (entry: MemoryEntry, dirty: boolean) => void;
  onArchive: (entry: MemoryEntry, archived: boolean) => Promise<MemoryEntry | null>;
  onDelete: (entry: MemoryEntry) => void;
  onPurge: (entry: MemoryEntry) => void;
  onRestore: (entry: MemoryEntry) => Promise<MemoryEntry | null>;
  /** 지운 뒤 내 내용을 새 항목으로 저장 */
  onSaveAsNew: (draft: { content: string; entry: MemoryEntry }) => void;
  handleRef?: Ref<EntryDetailHandle>;
}

export function EntryDetail(props: EntryDetailProps) {
  const { id, knownKey, kinds, ctx, limits, inFilter, closable, contentTypeSuggestions, onOpenRun, onClose, onDirtyChange, onHistory, onMove, onArchive, onDelete, onPurge, onRestore, onSaveAsNew } = props;
  const editor = useEntryEditor(id, t.detail.saveFailedNote);
  const storage = useStorage();
  const editorHandle = useRef<MemoryEntryEditorHandle>(null);
  const [pending, setPending] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [metaOpen, setMetaOpen] = useState(() => {
    const saved = storage.get(MEMORY_STORAGE.metaOpen);
    return saved === null ? (typeof window === "undefined" ? true : window.innerHeight >= MEMORY_LIMITS.metaOpenMinHeight) : saved === "1";
  });
  const { dirty, entry } = editor;

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useImperativeHandle(props.handleRef, () => ({ save: editor.save, discard: editor.discard }), [editor.save, editor.discard]);

  const label = (scope: MemoryScopeRef): ScopeLabel => scopeLabel(scope, kinds.find((k) => k.kind === scope.kind), ctx.resolvers, kinds.some((k) => k.kind === scope.kind));

  if (editor.status === "loading") {
    return (
      <section className="mem-detail" aria-busy="true" aria-label={knownKey ?? t.detail.loadingEntry}>
        <div className="mem-detail-head">
          <h2 className="mem-detail-title ac-ellipsis" title={knownKey}>{knownKey ?? ""}</h2>
        </div>
        <div className="mem-skeleton" role="status" aria-label={t.detail.loadingEntry}><Spinner /></div>
      </section>
    );
  }
  if (editor.status === "notfound") {
    return (
      <section className="mem-detail">
        <ErrorBlock title={t.detail.notFoundTitle} message={t.detail.notFoundBody}>
          <Button onClick={onClose}>{t.detail.toList}</Button>
        </ErrorBlock>
      </section>
    );
  }
  if (editor.status === "error" || entry === null || editor.draft === null) {
    return (
      <section className="mem-detail">
        <ErrorBlock title={t.detail.loadFailed} message={describeError(editor.error, t.detail.loadFailed).message} retryLabel={t.retry} onRetry={editor.reload} />
      </section>
    );
  }

  const draft = editor.draft;
  const scope = label(entry.scope);
  const deleted = editor.readOnly;
  const saveText =
    editor.saveState === "saving"
      ? viewMessages["save.saving"]
      : pending
        ? viewMessages["save.pending"]
        : editor.saveState === "failed"
          ? viewMessages["save.failed"]
          : editor.saveState === "dirty"
            ? viewMessages["save.dirty"]
            : viewMessages["save.saved"];
  const goField = (field: "content" | "key" | "tags" | null) => {
    if (field === "tags") document.querySelector<HTMLElement>(".mem-detail input[aria-label]")?.focus();
    else document.querySelector<HTMLElement>(".mem-detail .cm-content")?.focus();
  };
  const savedAgo = relativeTime(entry.updated_at);

  const menu = (
    <Menu
      onClose={() => setMenuOpen(false)}
      items={[
        { id: "move", label: t.menu.move, disabled: deleted, onSelect: () => onMove(entry, dirty) },
        { id: "history", label: t.menu.history, onSelect: () => onHistory(entry, dirty) },
        {
          id: "archive",
          label: entry.archived === true ? t.menu.unarchive : t.menu.archive,
          icon: "archive",
          disabled: deleted,
          onSelect: () => void onArchive(entry, entry.archived !== true).then((e) => e && editor.rebase(e)),
        },
        { id: "delete", label: t.menu.delete, disabled: deleted, onSelect: () => onDelete(entry) },
        { id: "purge", label: t.menu.purge, danger: true, onSelect: () => onPurge(entry) },
      ]}
    />
  );

  return (
    <section className="mem-detail" aria-label={entry.key}>
      <div className="mem-detail-head">
        <h2 className="mem-detail-title ac-ellipsis" title={entry.key}>{entry.key}</h2>
        <IconButton label={t.detail.copyKey} size="sm" icon={<Icon name="copy" />} onClick={() => void navigator.clipboard?.writeText(entry.key)} />
        <span className="mem-save-state" role="status" data-state={editor.saveState} title={savedAgo}>
          {editor.saveState === "failed" ? <StatusIcon status="failed" kind="run" size={14} /> : null}
          {saveText}
        </span>
        {editor.saveState === "failed" && editor.dirty ? (
          <button type="button" className="mem-linkbtn" onClick={() => editorHandle.current?.requestSave()}>{t.retry}</button>
        ) : null}
        <div className="mem-detail-actions">
          <Button variant="primary" size="sm" disabled={!editor.dirty || deleted || editor.saveState === "saving"} loading={editor.saveState === "saving"} onClick={() => editorHandle.current?.requestSave()} title="Ctrl+S">
            {t.detail.save}
          </Button>
          <Button size="sm" onClick={() => onHistory(entry, dirty)}>{t.detail.history}</Button>
          <Popover
            open={menuOpen}
            onOpenChange={setMenuOpen}
            align="end"
            panelRole="menu"
            panelLabel={t.menu.label(entry.key)}
            renderTrigger={(p) => (
              <button {...p} type="button" className="mem-iconbtn" aria-label={t.detail.more} title={t.detail.more}>
                <Icon name="more" />
              </button>
            )}
          >
            {menu}
          </Popover>
          {closable ? <IconButton label={t.detail.close} size="sm" icon={<Icon name="close" />} onClick={onClose} /> : null}
        </div>
      </div>
      {!inFilter ? <p className="mem-note" role="status">{t.detail.notInFilter}</p> : null}
      <div className="mem-bands">
        {editor.secret !== null ? <SecretBand field={editor.secret.field} onGo={() => goField(editor.secret?.field ?? null)} /> : null}
        {editor.failure !== null ? <Banner tone="danger" className="mem-band">{editor.failure}</Banner> : null}
        {editor.band?.kind === "deleted" ? (
          <Banner tone="info" className="mem-band" actions={<Button size="sm" onClick={() => void onRestore(entry).then((e) => e && editor.rebase(e))}>{t.band.restore}</Button>}>
            {t.band.deleted}
          </Banner>
        ) : null}
        {editor.band?.kind === "deletedNow" ? (
          <Banner
            tone="warning"
            className="mem-band"
            actions={
              <>
                <Button size="sm" onClick={() => void onRestore(entry).then((e) => e && editor.rebase(e))}>{t.band.restore}</Button>
                <Button size="sm" onClick={() => onSaveAsNew({ content: draft.content, entry })}>{t.band.saveAsNew}</Button>
              </>
            }
          >
            {t.band.deletedNow}
          </Banner>
        ) : null}
        {editor.band?.kind === "moved" ? (
          <Banner tone="info" className="mem-band" actions={<Button size="sm" onClick={editor.followMove}>{t.band.followMove}</Button>}>
            {t.band.movedNow(`${label(editor.band.to.scope).text}/${editor.band.to.key}`)}
          </Banner>
        ) : null}
        {editor.band?.kind === "newer" ? (
          <Banner
            tone="info"
            className="mem-band"
            actions={
              <>
                <Button size="sm" onClick={() => void editor.openCompare()}>{t.band.compare}</Button>
                <Button size="sm" onClick={editor.loadServer}>{t.band.loadServer}</Button>
              </>
            }
          >
            {t.band.newerVersion(editor.band.server.version, serverAuthor(editor.band.server, ctx), relativeTime(editor.band.server.updated_at))}
          </Banner>
        ) : null}
        {editor.redacted ? (
          <Banner tone="info" className="mem-band" actions={<Button size="sm" onClick={editor.dismissRedacted}>{t.close}</Button>}>
            {t.band.redacted}
          </Banner>
        ) : null}
      </div>
      <Disclosure
        className="mem-meta"
        summary={viewMessages["detail.info"]}
        open={metaOpen}
        onOpenChange={(open) => {
          setMetaOpen(open);
          storage.set(MEMORY_STORAGE.metaOpen, open ? "1" : "0");
        }}
      >
        <MemoryEntryMeta
          entry={entry}
          scope={scope}
          draft={{ tags: draft.tags, contentType: draft.contentType, pinned: draft.pinned }}
          onDraftChange={editor.setMeta}
          onArchivedChange={(archived) => void onArchive(entry, archived).then((e) => e && editor.rebase(e))}
          readOnly={deleted}
          contentTypeSuggestions={contentTypeSuggestions}
          authorOptions={ctx.authorOptions}
          onOpenHistory={() => onHistory(entry, dirty)}
          onCopy={(text) => void navigator.clipboard?.writeText(text)}
          {...(onOpenRun === undefined ? {} : { onOpenRun })}
        />
      </Disclosure>
      <div className="mem-detail-editor" data-ac-editable>
        <MemoryEntryEditor
          value={draft.content}
          onChange={editor.setContent}
          entryKey={entry.key}
          contentType={draft.contentType === "" ? entry.content_type : draft.contentType}
          onSave={() => void editor.save()}
          saveState={editor.saveState}
          readOnly={deleted}
          maxBytes={limits.maxEntryBytes}
          handleRef={editorHandle}
          onSavePendingChange={setPending}
        />
      </div>
      {editor.conflict !== null && editor.draft !== null ? (
        <ConflictDialog
          open
          openedVersion={editor.openedVersion}
          server={editor.conflict}
          serverAuthor={serverAuthor(editor.conflict, ctx)}
          mine={draft.content}
          contentType={draft.contentType === "" ? entry.content_type : draft.contentType}
          saving={editor.saveState === "saving"}
          onKeepEditing={editor.closeConflict}
          onLoadServer={editor.loadServer}
          onSaveMine={() => void editor.saveOverServer()}
        />
      ) : null}
    </section>
  );
}

function serverAuthor(entry: MemoryEntry, ctx: MemoryContext): string {
  const a = entry.updated_by;
  const named = a.agent_id !== undefined && a.agent_id !== null ? ctx.authorOptions.resolveAgent?.(a.agent_id) : undefined;
  return a.label ?? (named?.status === "named" ? named.name : (a.agent_id ?? a.kind));
}
