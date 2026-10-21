import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { ContentChange, DefinitionVersion, DiffChange, VersionConflictDetails } from "@agent-console/contracts";
import { Banner, Button, Dialog, useToast } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { useNow } from "../../app/useNow";
import { ConflictBanner } from "../../definition/ConflictBanner";
import { shortId } from "../../lib/format";
import { ContentChanges, type SideText } from "./ContentChanges";
import { DiffTable } from "./DiffTable";
import { RestoreDialog, type RestoreIssue } from "./RestoreDialog";
import { VersionList } from "./VersionList";
import { versionMessages as t } from "./messages";
import { useVersionDiff, useVersionDoc, useVersionFiles, useVersionList, versionKeys } from "./useVersionData";
import { compareTarget, diffTotals, isSameDiff, readIssues, readablePath, sizeOfFile, type CompareMode, type ReadablePathOptions } from "./versionsLogic";
import "./versions.css";

export interface VersionHistoryProps {
  /** 정의 경로(`definitionBase("/agents", id)`처럼 만든 문자열). 정의 종류 이름을 몰라도 된다 */
  base: string;
  /** 서버가 아는 현재 해시(되돌릴 때 `If-Match`). 생략하면 목록 맨 앞 */
  currentHash?: string | undefined;
  /** 편집 화면에 저장 안 된 변경이 있다(안내·경고 표시) */
  dirty?: boolean;
  /** 읽는 경로 옵션(배열 원소 이름 후보 키·스키마 title) */
  pathOptions?: ReadablePathOptions;
  /** 되돌리기(또는 실행 취소)에 성공한 뒤. 편집 화면이 초안을 버리고 다시 읽는다 */
  onRestored?: (result: { value: DefinitionVersion; version_hash: string | undefined }) => void;
}

function hash8Of(hash: string | undefined): string {
  return hash === undefined ? "" : shortId(hash);
}

/**
 * 버전 탭 본문(정의 종류 공통): 목록 + 비교(필드 변경 표·본문 텍스트 비교) + 되돌리기(확인·토스트 [실행 취소]).
 * 서버 호출은 `base` 경로로만 한다. 비밀 값은 서버가 가린 그대로 보이고, 412는 충돌 배너, 422는 서버 이슈를 다이얼로그에 보인다.
 */
export function VersionHistory({ base, currentHash, dirty = false, pathOptions, onRestored }: VersionHistoryProps) {
  const { rest } = useApi();
  const toast = useToast();
  const queryClient = useQueryClient();
  const now = useNow(true, 30_000);
  const list = useVersionList(base);
  const versions = useMemo(() => list.data ?? [], [list.data]);

  const [mode, setMode] = useState<CompareMode>("current");
  const [checked, setChecked] = useState<string[]>([]);
  const [rawFor, setRawFor] = useState<string | null>(null);
  const [restoreFor, setRestoreFor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [issues, setIssues] = useState<RestoreIssue[] | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ details: VersionConflictDetails; hash: string; message: string } | null>(null);

  const serverCurrent = currentHash ?? versions[0]?.version_hash;
  const target = useMemo(() => compareTarget(versions, checked, mode), [versions, checked, mode]);
  const diff = useVersionDiff(base, target?.from, target?.to);
  const fromDoc = useVersionDoc(base, diff.data?.from_hash);
  const toDoc = useVersionDoc(base, diff.data?.to_hash);
  const hasContent = (diff.data?.content_changes ?? []).length > 0;
  const fromFiles = useVersionFiles(base, diff.data?.from_hash, hasContent);
  const toFiles = useVersionFiles(base, diff.data?.to_hash, hasContent);

  const readable = useCallback(
    (change: DiffChange) => {
      const doc = change.op === "add" ? toDoc.data?.content : fromDoc.data?.content;
      return readablePath(change.path, doc, pathOptions);
    },
    [fromDoc.data, toDoc.data, pathOptions],
  );

  const toggle = (hash: string) =>
    setChecked((prev) => {
      if (mode === "current") return prev.includes(hash) ? [] : [hash];
      if (prev.includes(hash)) return prev.filter((h) => h !== hash);
      return [...prev, hash].slice(-2);
    });
  const compareCurrent = (hash: string) => {
    setMode("current");
    setChecked(hash === versions[0]?.version_hash ? [] : [hash]);
  };
  const comparePair = () => {
    if (mode !== "pair") setMode("pair");
  };
  const changeMode = (next: CompareMode) => {
    setMode(next);
    setChecked((prev) => (next === "current" ? prev.filter((h) => h !== versions[0]?.version_hash).slice(-1) : prev));
  };

  const isCurrentTarget = target !== undefined && target.to === undefined && target.from !== serverCurrent;
  const restoreSummaryDiff = useVersionDiff(base, restoreFor ?? undefined, undefined, restoreFor !== null);
  const summary = restoreSummaryDiff.data === undefined ? undefined : diffTotals(restoreSummaryDiff.data);

  const closeRestore = () => {
    setRestoreFor(null);
    setIssues(null);
    setRestoreError(null);
  };

  const finish = useCallback(
    async (result: { value: DefinitionVersion; version_hash: string | undefined }) => {
      await queryClient.invalidateQueries({ queryKey: versionKeys.all(base) });
      onRestored?.(result);
    },
    [queryClient, base, onRestored],
  );

  const restore = async (hash: string, message: string, ifMatch: string | undefined) => {
    setBusy(true);
    setIssues(null);
    setRestoreError(null);
    try {
      const result = await rest.restoreDefinitionVersion(base, hash, message === "" ? {} : { message }, ifMatch);
      const created = result.version_hash ?? result.value.version_hash;
      closeRestore();
      setConflict(null);
      setChecked([]);
      await finish(result);
      toast({
        tone: "success",
        text: t.restore.done(hash8Of(hash), hash8Of(created)),
        durationMs: 10_000,
        action: {
          label: t.restore.undo,
          onClick: () => {
            if (ifMatch === undefined) return;
            rest.restoreDefinitionVersion(base, ifMatch, {}, created).then(
              (undone) => {
                void finish(undone);
                toast({ tone: "success", text: t.restore.undone(hash8Of(undone.version_hash ?? undone.value.version_hash)) });
              },
              (e: unknown) => toast({ tone: "danger", text: `${t.restore.undoFailed}: ${describeError(e, "").message}` }),
            );
          },
        },
      });
    } catch (e) {
      if (e instanceof ApiError && e.versionConflict !== undefined) {
        closeRestore();
        setConflict({ details: e.versionConflict, hash, message });
      } else if (e instanceof ApiError && e.status === 422) {
        setIssues(readIssues(e.details["issues"]));
        if (readIssues(e.details["issues"]).length === 0) setRestoreError(e.message);
      } else {
        setRestoreError(describeError(e, t.restore.failed).message);
      }
    } finally {
      setBusy(false);
    }
  };

  const loadSides = useCallback(
    async (change: ContentChange): Promise<{ before: SideText; after: SideText }> => {
      const d = diff.data;
      if (d === undefined) throw new Error("no diff");
      const [before, after] = await Promise.all([
        change.before_hash == null ? Promise.resolve({ text: "" }) : rest.readVersionFile(base, d.from_hash, change.path),
        change.after_hash == null ? Promise.resolve({ text: "" }) : rest.readVersionFile(base, d.to_hash, change.path),
      ]);
      return { before: { text: before.text }, after: { text: after.text } };
    },
    [diff.data, rest, base],
  );
  const sizeOf = useCallback(
    (path: string, side: "before" | "after") => sizeOfFile(side === "before" ? fromFiles.data : toFiles.data, path),
    [fromFiles.data, toFiles.data],
  );

  if (list.isLoading) {
    return (
      <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.list.label}>
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className="app-skeleton-row" aria-hidden="true" />
        ))}
      </div>
    );
  }
  if (list.isError) {
    return <ErrorBlock title={t.list.failed} message={list.error.message} retryLabel={t.retry} onRetry={() => void list.refetch()} />;
  }
  if (versions.length === 0) return <p className="app-muted">{t.list.empty}</p>;

  const onlyCurrent = versions.length === 1;
  const fromLabel = hash8Of(diff.data?.from_hash ?? target?.from);
  const toLabel = target?.to === undefined ? t.compare.currentOf(hash8Of(diff.data?.to_hash ?? serverCurrent)) : hash8Of(target.to);
  const rawVersion = rawFor === null ? undefined : versions.find((v) => v.version_hash === rawFor);

  return (
    <div className="ver-root">
      {dirty ? <Banner tone="info">{t.unsavedInfo}</Banner> : null}
      {conflict === null ? null : (
        <ConflictBanner
          details={conflict.details}
          busy={busy}
          onLoadServer={() => {
            setConflict(null);
            void queryClient.invalidateQueries({ queryKey: versionKeys.all(base) });
          }}
          onOverwrite={() => void restore(conflict.hash, conflict.message, conflict.details.current_version_hash)}
        />
      )}
      {onlyCurrent ? (
        <p className="app-muted">{t.list.onlyCurrent}</p>
      ) : (
        <div className="ver-layout">
          <VersionList
            versions={versions}
            now={now}
            checked={checked}
            mode={mode}
            onModeChange={changeMode}
            onToggle={toggle}
            onCompareCurrent={compareCurrent}
            onComparePair={comparePair}
            onRestore={(hash) => {
              setIssues(null);
              setRestoreError(null);
              setRestoreFor(hash);
            }}
            onViewRaw={setRawFor}
            onCopyHash={(hash) => {
              void navigator.clipboard?.writeText(hash).then(() => toast({ tone: "success", text: t.menu.copied }));
            }}
          />
          <section className="ver-compare" aria-label={t.compare.region}>
            {target === undefined ? (
              <p className="app-muted">{mode === "pair" ? t.mode.pairHint : t.compare.pickTwo}</p>
            ) : (
              <>
                <div className="ver-compare-head">
                  <h3 className="app-block-title" aria-live="polite">
                    {t.compare.heading(fromLabel, toLabel)}
                  </h3>
                  {diff.data === undefined ? null : <span className="app-muted ac-num">{t.compare.summary(diffTotals(diff.data).fields, diffTotals(diff.data).content)}</span>}
                  <span className="app-spacer" />
                  <Button
                    disabled={!isCurrentTarget}
                    title={isCurrentTarget ? undefined : t.compare.restoreOnlyCurrent}
                    onClick={() => {
                      setIssues(null);
                      setRestoreError(null);
                      setRestoreFor(target.from);
                    }}
                  >
                    {t.compare.restore}
                  </Button>
                </div>
                {diff.isLoading ? (
                  <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.compare.loading}>
                    {Array.from({ length: 5 }, (_, i) => (
                      <span key={i} className="app-skeleton-row" aria-hidden="true" />
                    ))}
                  </div>
                ) : null}
                {diff.isError ? <ErrorBlock title={t.compare.failed} message={diff.error.message} retryLabel={t.retry} onRetry={() => void diff.refetch()} /> : null}
                {diff.data !== undefined && isSameDiff(diff.data) ? <p className="app-muted">{t.compare.same}</p> : null}
                {diff.data !== undefined && !isSameDiff(diff.data) ? (
                  <>
                    <section aria-label={t.fields.title}>
                      <h3 className="app-block-title">{t.fields.title}</h3>
                      <DiffTable changes={diff.data.changes ?? []} readable={readable} />
                    </section>
                    <ContentChanges changes={diff.data.content_changes ?? []} sizeOf={sizeOf} load={loadSides} />
                  </>
                ) : null}
              </>
            )}
          </section>
        </div>
      )}
      {restoreFor === null ? null : (
        <RestoreDialog
          open
          hash8={hash8Of(restoreFor)}
          summary={summary}
          dirty={dirty}
          busy={busy}
          issues={issues}
          error={restoreError}
          onConfirm={(message) => void restore(restoreFor, message, serverCurrent)}
          onCancel={closeRestore}
        />
      )}
      {rawVersion === undefined ? null : <RawVersionDialog base={base} version={rawVersion} onClose={() => setRawFor(null)} />}
    </div>
  );
}

function RawVersionDialog({ base, version, onClose }: { base: string; version: DefinitionVersion; onClose: () => void }) {
  const doc = useVersionDoc(base, version.version_hash);
  return (
    <Dialog open wide title={t.raw.title(shortId(version.version_hash))} onClose={onClose} actions={<Button onClick={onClose}>{t.raw.close}</Button>}>
      {doc.isLoading ? <p className="app-muted">{t.raw.loading}</p> : null}
      {doc.isError ? <p role="alert">{t.raw.failed}</p> : null}
      {doc.data === undefined ? null : <pre className="ac-pre app-json ver-raw">{JSON.stringify(doc.data.content ?? {}, null, 2)}</pre>}
    </Dialog>
  );
}
