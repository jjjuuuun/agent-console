/**
 * 항목 하나의 편집 상태(서버 값 + 로컬 초안 + 명시 저장 + 충돌).
 * 서버 값은 질의 캐시가 진실이고, 편집을 시작하면 그 시점의 서버 값(`from`)과 초안을 함께 기억한다.
 * 그래서 서버 쪽이 바뀌어도(실시간 알림·창 복귀) 편집 중이 아니면 조용히 따라가고, 편집 중이면 덮어쓰지 않고 띠로 알린다.
 */
import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, memoryConflictVersion } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts/constants";
import type { MemoryEntry, MemorySecretRejectedDetails, MemoryUpdateRequest } from "@agent-console/contracts/memory";
import { secretRejectedField, type EntrySaveState, type MemoryMetaDraft } from "@agent-console/memory-view";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { memoryKeys, useMemoryEntry } from "./useMemoryApi";

export interface EntryDraft extends MemoryMetaDraft {
  content: string;
}

interface Edit {
  from: MemoryEntry;
  draft: EntryDraft;
}

/** 본문 위에 얹는 띠. 한 번에 하나만 보인다(가장 급한 것부터). */
export type EditorBand =
  | { kind: "deleted" }
  | { kind: "deletedNow" }
  | { kind: "moved"; to: MemoryEntry }
  | { kind: "newer"; server: MemoryEntry };

export interface SecretNote {
  /** 위치(`content`·`key`·`tags`). 모르면 null(일반 문구). 찾은 값·규칙 id는 받지 않는다 */
  field: "content" | "key" | "tags" | null;
}

export interface EntryEditor {
  status: "loading" | "error" | "notfound" | "ready";
  error: Error | null;
  reload: () => void;
  /** 서버가 마지막으로 준 값 */
  entry: MemoryEntry | null;
  draft: EntryDraft | null;
  dirty: boolean;
  readOnly: boolean;
  saveState: EntrySaveState;
  failure: string | null;
  secret: SecretNote | null;
  redacted: boolean;
  dismissRedacted: () => void;
  band: EditorBand | null;
  setContent: (content: string) => void;
  setMeta: (meta: MemoryMetaDraft) => void;
  /** 저장. 성공하면 true. 충돌(412)이면 `conflict`가 채워지고 false */
  save: () => Promise<boolean>;
  /** 충돌 대화상자에 보일 서버 최신 항목(없으면 닫힘) */
  conflict: MemoryEntry | null;
  /** 내가 편집을 시작한 때의 서버 버전(충돌 대화상자 머리) */
  openedVersion: number;
  openCompare: () => Promise<void>;
  closeConflict: () => void;
  /** 내 변경을 서버 최신 버전 위에 저장 */
  saveOverServer: () => Promise<boolean>;
  /** 내 변경을 버리고 서버 버전을 불러온다 */
  loadServer: () => void;
  /** 지금 서버 값으로 기준을 옮긴다(보관·옮기기·복원 같은 즉시 동작의 응답). 편집 중인 초안은 살린다 */
  rebase: (entry: MemoryEntry) => void;
  followMove: () => void;
  /** 편집 내용을 버린다 */
  discard: () => void;
}

const sameTags = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((t, i) => t === b[i]);

function draftOf(e: MemoryEntry): EntryDraft {
  return { content: e.content, contentType: e.content_type ?? "", tags: e.tags ?? [], pinned: e.pinned === true };
}

/** 두 초안이 같은가(본문·형식·태그·고정). */
export function sameDraft(a: EntryDraft, b: EntryDraft): boolean {
  return a.content === b.content && a.contentType === b.contentType && a.pinned === b.pinned && sameTags(a.tags, b.tags);
}

/** 기준 `from`과 다른 필드만 담은 PUT 본문. 바뀐 것이 없으면 빈 객체. */
export function patchOf(from: MemoryEntry, draft: EntryDraft): MemoryUpdateRequest {
  const base = draftOf(from);
  return {
    ...(draft.content === base.content ? {} : { content: draft.content }),
    ...(draft.contentType === base.contentType ? {} : { content_type: draft.contentType }),
    ...(sameTags(draft.tags, base.tags) ? {} : { tags: [...draft.tags] }),
    ...(draft.pinned === base.pinned ? {} : { pinned: draft.pinned }),
  };
}

export function useEntryEditor(id: string, fallbackMessage: string): EntryEditor {
  const { rest } = useApi();
  const qc = useQueryClient();
  const query = useMemoryEntry(id, true);
  const server = query.data ?? null;

  const [edit, setEdit] = useState<Edit | null>(null);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [secret, setSecret] = useState<SecretNote | null>(null);
  const [redacted, setRedacted] = useState(false);
  const [conflict, setConflict] = useState<MemoryEntry | null>(null);

  const dirty = edit !== null && !sameDraft(edit.draft, draftOf(edit.from));
  const draft = useMemo(() => (server === null ? null : dirty && edit !== null ? edit.draft : draftOf(server)), [server, dirty, edit]);
  const readOnly = server?.deleted_at !== null && server?.deleted_at !== undefined;

  const band = useMemo<EditorBand | null>(() => {
    if (server === null) return null;
    if (readOnly) return dirty && edit !== null && edit.from.deleted_at == null ? { kind: "deletedNow" } : { kind: "deleted" };
    if (dirty && edit !== null) {
      if (edit.from.key !== server.key || edit.from.scope.kind !== server.scope.kind || (edit.from.scope.id ?? "") !== (server.scope.id ?? "")) return { kind: "moved", to: server };
      if (server.version > edit.from.version) return { kind: "newer", server };
    }
    return null;
  }, [server, readOnly, dirty, edit]);

  const patch = useCallback(
    (change: (cur: EntryDraft) => EntryDraft) => {
      if (server === null || readOnly) return;
      setEdit((cur) => {
        const from = cur?.from ?? server;
        const current = cur?.draft ?? draftOf(server);
        return { from, draft: change(current) };
      });
      setFailure(null);
      setSecret(null);
      setRedacted(false);
    },
    [server, readOnly],
  );
  const setContent = useCallback((content: string) => patch((d) => ({ ...d, content })), [patch]);
  const setMeta = useCallback((meta: MemoryMetaDraft) => patch((d) => ({ ...d, tags: [...meta.tags], contentType: meta.contentType, pinned: meta.pinned })), [patch]);

  const adopt = useCallback(
    (entry: MemoryEntry) => {
      qc.setQueryData(memoryKeys.entry(id), entry);
      void qc.invalidateQueries({ queryKey: memoryKeys.root, predicate: (q) => q.queryKey[1] !== "entry" });
    },
    [qc, id],
  );

  const commit = useCallback(
    async (from: MemoryEntry, mine: EntryDraft, version: number): Promise<boolean> => {
      const body = patchOf(from, mine);
      if (Object.keys(body).length === 0) return true;
      setSaving(true);
      setFailure(null);
      setSecret(null);
      try {
        const saved = await rest.updateMemoryEntry(id, body, version);
        adopt(saved);
        // 저장하는 동안 더 고친 내용은 살린다. 서버가 본문을 바꿔 돌려줬으면(가림) 알린다.
        setEdit((cur) => (cur !== null && cur.draft.content !== mine.content ? { from: saved, draft: cur.draft } : null));
        setRedacted(body.content !== undefined && saved.content !== body.content);
        setConflict(null);
        return true;
      } catch (e) {
        if (memoryConflictVersion(e) !== undefined || (e instanceof ApiError && e.status === 412)) {
          try {
            const latest = await rest.getMemoryEntry(id, { includeDeleted: true });
            qc.setQueryData(memoryKeys.entry(id), latest);
            setConflict(latest);
          } catch (inner) {
            setFailure(describeError(inner, fallbackMessage).message);
          }
        } else if (e instanceof ApiError && e.code === ERROR_CODES.MEMORY_SECRET_REJECTED) {
          const details = e.details as Partial<MemorySecretRejectedDetails>;
          setSecret({ field: secretRejectedField(details.field) });
        } else {
          setFailure(describeError(e, fallbackMessage).message);
        }
        return false;
      } finally {
        setSaving(false);
      }
    },
    [rest, id, adopt, qc, fallbackMessage],
  );

  const save = useCallback(async (): Promise<boolean> => {
    if (server === null || edit === null || !dirty || readOnly || saving) return false;
    return commit(edit.from, edit.draft, edit.from.version);
  }, [server, edit, dirty, readOnly, saving, commit]);

  const saveOverServer = useCallback(async (): Promise<boolean> => {
    if (conflict === null || edit === null) return false;
    return commit(edit.from, edit.draft, conflict.version);
  }, [conflict, edit, commit]);

  const openCompare = useCallback(async () => {
    try {
      const latest = await rest.getMemoryEntry(id, { includeDeleted: true });
      qc.setQueryData(memoryKeys.entry(id), latest);
      setConflict(latest);
    } catch (e) {
      setFailure(describeError(e, fallbackMessage).message);
    }
  }, [rest, id, qc, fallbackMessage]);

  const discard = useCallback(() => {
    setEdit(null);
    setFailure(null);
    setSecret(null);
    setRedacted(false);
    setConflict(null);
  }, []);

  const loadServer = useCallback(() => {
    discard();
    void query.refetch();
  }, [discard, query]);

  const rebase = useCallback(
    (entry: MemoryEntry) => {
      adopt(entry);
      setEdit((cur) => (cur === null ? null : { from: entry, draft: cur.draft }));
    },
    [adopt],
  );
  const followMove = useCallback(() => {
    if (server !== null) setEdit((cur) => (cur === null ? null : { from: server, draft: cur.draft }));
  }, [server]);

  const saveState: EntrySaveState = saving ? "saving" : failure !== null || secret !== null ? "failed" : dirty ? "dirty" : "saved";
  const notFound = query.error instanceof ApiError && query.error.status === 404;

  return {
    status: server !== null ? "ready" : notFound ? "notfound" : query.isError ? "error" : "loading",
    error: query.error,
    reload: () => void query.refetch(),
    entry: server,
    draft,
    dirty,
    readOnly,
    saveState,
    failure,
    secret,
    redacted,
    dismissRedacted: () => setRedacted(false),
    band,
    setContent,
    setMeta,
    save,
    conflict,
    openedVersion: edit?.from.version ?? server?.version ?? 0,
    openCompare,
    closeConflict: () => setConflict(null),
    saveOverServer,
    loadServer,
    rebase,
    followMove,
    discard,
  };
}
