/**
 * 버전 기록: 왼쪽 버전 목록(최신순), 오른쪽 직전/현재 비교. 본문은 선택한 버전만 지연 로드한다.
 * 되돌리기는 새 버전이 하나 더 생기는 동작이다(역사를 지우지 않는다). 편집기에 저장 안 된 변경이 있으면 먼저 확인한다.
 */
import { useMemo, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import type { MemoryEntry, MemoryEntrySummary, MemoryScopeRef } from "@agent-console/contracts/memory";
import { MemoryVersionDiff, MemoryVersionList, type VersionCompareTarget } from "@agent-console/memory-view";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { useStorage } from "../../app/StorageContext";
import { useToast } from "@agent-console/ui";
import { viewMessages } from "./format";
import { MEMORY_STORAGE } from "./memoryConfig";
import { memoryMessages as t } from "./messages";
import { useInvalidateMemory, useMemoryVersion, useMemoryVersions } from "./useMemoryApi";
import type { MemoryContext } from "./useMemoryContext";

export interface HistoryDialogProps {
  entry: MemoryEntry | MemoryEntrySummary;
  ctx: MemoryContext;
  labelOf: (scope: MemoryScopeRef) => string;
  /** 본문에 저장하지 않은 변경이 있다 */
  dirty: boolean;
  maxVersions: number | null;
  onClose: () => void;
  /** 되돌렸다(새 항목 값) */
  onRestored: (entry: MemoryEntry) => void;
}

export function HistoryDialog({ entry, ctx, labelOf, dirty, maxVersions, onClose, onRestored }: HistoryDialogProps) {
  const { rest } = useApi();
  const toast = useToast();
  const invalidate = useInvalidateMemory();
  const storage = useStorage();
  const list = useMemoryVersions(entry.id, true);
  const versions = useMemo(() => list.data ?? [], [list.data]);
  const latest = versions.reduce((n, v) => Math.max(n, v.version), 0);
  const [picked, setPicked] = useState<number | null>(null);
  const selected = picked ?? (latest > 0 ? latest : null);
  const [compare, setCompare] = useState<VersionCompareTarget>("prev");
  const [layout, setLayout] = useState<"auto" | "split" | "unified">(() => {
    const saved = storage.get(MEMORY_STORAGE.diffLayout);
    return saved === "split" || saved === "unified" ? saved : "auto";
  });
  const [confirm, setConfirm] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const sorted = useMemo(() => [...versions].sort((a, b) => a.version - b.version), [versions]);
  const index = sorted.findIndex((v) => v.version === selected);
  const version = index >= 0 ? (sorted[index] ?? null) : null;
  const base = compare === "prev" ? (index > 0 ? (sorted[index - 1] ?? null) : null) : version !== null && version.version !== latest ? (sorted[sorted.length - 1] ?? null) : null;
  const content = useMemoryVersion(entry.id, version?.version ?? null);
  const baseContent = useMemoryVersion(entry.id, base?.version ?? null);
  const isCurrent = version !== null && version.version === latest;

  const restore = async (v: number) => {
    setBusy(true);
    try {
      const out = await rest.restoreMemoryEntry(entry.id, v);
      await invalidate();
      toast({ tone: "success", text: t.history.restored });
      onRestored(out);
    } catch (e) {
      toast({ tone: "danger", text: `${t.history.failed}: ${describeError(e, t.history.failed).message}` });
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  return (
    <>
      <Dialog open size="xl" title={`${viewMessages["history.title"]} · ${entry.key}`} onClose={onClose} actions={<Button onClick={onClose}>{t.close}</Button>}>
        <div className="mem-history">
          <MemoryVersionList
            versions={versions}
            selected={selected}
            onSelect={setPicked}
            currentVersion={latest}
            loading={list.isPending}
            error={list.isError}
            onRetry={() => void list.refetch()}
            authorOptions={ctx.authorOptions}
          />
          <MemoryVersionDiff
            version={version}
            base={base}
            {...(content.data === undefined ? {} : { versionContent: content.data.content })}
            {...(baseContent.data === undefined ? {} : { baseContent: baseContent.data.content })}
            compare={compare}
            onCompareChange={setCompare}
            layout={layout}
            onLayoutChange={(next) => {
              setLayout(next);
              storage.set(MEMORY_STORAGE.diffLayout, next);
            }}
            isCurrent={isCurrent}
            onRestore={(v) => (dirty ? setConfirm(v) : void restore(v))}
            loading={content.isPending || (base !== null && baseContent.isPending)}
            error={content.isError || baseContent.isError}
            onRetry={() => {
              void content.refetch();
              void baseContent.refetch();
            }}
            scopeText={labelOf}
            contentType={entry.content_type}
            authorOptions={ctx.authorOptions}
            maxVersions={maxVersions}
          />
        </div>
      </Dialog>
      {confirm !== null ? (
        <Dialog
          open
          size="sm"
          title={t.history.restoreConfirm}
          onClose={() => setConfirm(null)}
          actions={
            <>
              <Button onClick={() => setConfirm(null)}>{t.cancel}</Button>
              <Button variant="danger" loading={busy} onClick={() => void restore(confirm)}>{t.history.restoreSubmit}</Button>
            </>
          }
        >
          <p className="ac-text">{t.history.restoreConfirm}</p>
        </Dialog>
      ) : null}
    </>
  );
}
