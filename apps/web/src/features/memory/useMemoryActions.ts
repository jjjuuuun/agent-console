/**
 * 항목 쓰기 동작(보관·지우기·완전 삭제·복원·내보내기)과 토스트. 호출 결과는 호출자가 쓰도록 돌려주고
 * 실패는 토스트로 알린 뒤 null/false를 돌려준다. 성공하면 메모리 질의를 모두 다시 읽게 한다.
 */
import { useCallback, useMemo } from "react";
import { useToast } from "@agent-console/ui";
import type { MemoryEntry, MemoryEntrySummary, MemoryScopeRef } from "@agent-console/contracts/memory";
import { formatBytes } from "@agent-console/memory-view";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { saveBlob } from "../../lib/download";
import { MEMORY_LIMITS } from "./memoryConfig";
import { memoryMessages as t } from "./messages";
import { useInvalidateMemory } from "./useMemoryApi";
import { sizeMessages } from "./format";

type Target = Pick<MemoryEntry | MemoryEntrySummary, "id" | "version">;

export interface MemoryActions {
  archive: (entry: Target, archived: boolean) => Promise<MemoryEntry | null>;
  remove: (entry: Target) => Promise<MemoryEntry | null>;
  purge: (entry: Pick<Target, "id">) => Promise<boolean>;
  restore: (entry: Pick<Target, "id">) => Promise<MemoryEntry | null>;
  exportScope: (scope: MemoryScopeRef | null) => Promise<boolean>;
}

export function useMemoryActions(): MemoryActions {
  const { rest } = useApi();
  const toast = useToast();
  const invalidate = useInvalidateMemory();

  const fail = useCallback(
    (e: unknown) => {
      toast({ tone: "danger", text: `${t.toast.failed}: ${describeError(e, t.toast.failed).message}` });
    },
    [toast],
  );

  return useMemo<MemoryActions>(() => {
    const restore: MemoryActions["restore"] = async (entry) => {
      try {
        const out = await rest.restoreMemoryEntry(entry.id);
        await invalidate();
        return out;
      } catch (e) {
        fail(e);
        return null;
      }
    };
    const archive: MemoryActions["archive"] = async (entry, archived) => {
      try {
        const out = archived ? await rest.archiveMemoryEntry(entry.id, entry.version) : await rest.unarchiveMemoryEntry(entry.id, entry.version);
        await invalidate();
        toast({
          tone: "success",
          text: archived ? t.toast.archived : t.toast.unarchived,
          durationMs: MEMORY_LIMITS.undoMs,
          action: {
            label: t.toast.undo,
            onClick: () => {
              void (async () => {
                try {
                  if (archived) await rest.unarchiveMemoryEntry(entry.id);
                  else await rest.archiveMemoryEntry(entry.id);
                  await invalidate();
                } catch (e) {
                  fail(e);
                }
              })();
            },
          },
        });
        return out;
      } catch (e) {
        fail(e);
        return null;
      }
    };
    const remove: MemoryActions["remove"] = async (entry) => {
      try {
        const out = await rest.deleteMemoryEntry(entry.id, entry.version);
        await invalidate();
        toast({ tone: "success", text: t.toast.deleted, durationMs: MEMORY_LIMITS.undoMs, action: { label: t.toast.undo, onClick: () => void restore(entry) } });
        return out;
      } catch (e) {
        fail(e);
        return null;
      }
    };
    const purge: MemoryActions["purge"] = async (entry) => {
      try {
        await rest.purgeMemoryEntry(entry.id);
        await invalidate();
        toast({ tone: "success", text: t.toast.purged });
        return true;
      } catch (e) {
        fail(e);
        return false;
      }
    };
    const exportScope: MemoryActions["exportScope"] = async (scope) => {
      try {
        const file = await rest.exportMemory(scope === null ? {} : { scopes: [scope] });
        const name = file.filename ?? t.export.fallbackName(new Date().toISOString().slice(0, 10));
        saveBlob(file.blob, name);
        toast({ tone: "success", text: t.toast.exported(name, formatBytes(file.blob.size, sizeMessages)) });
        return true;
      } catch (e) {
        toast({ tone: "danger", text: `${t.toast.exportFailed}: ${describeError(e, t.toast.exportFailed).message}` });
        return false;
      }
    };
    return { archive, remove, purge, restore, exportScope };
  }, [rest, toast, invalidate, fail]);
}
