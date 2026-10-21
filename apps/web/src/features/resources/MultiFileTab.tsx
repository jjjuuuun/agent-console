import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { Markdown } from "@agent-console/chat";
import type { TextEditorStatus } from "@agent-console/text-editor";
import { Banner, Button, ConfirmDialog, FileTree, useToast, type FileTreeItem } from "@agent-console/ui";
import { formatBytes } from "../../lib/bytes";
import { isImeKeyEvent } from "../../lib/ime";
import { LazyTextEditor } from "../library";
import { checkPath, decodeUtf8, dirOf, entryChanged, entrySize, languageForFile, removeEntries, renameEntries, sortEntries, totalSize, upsertEntry, type FileEntry } from "./fileTreeLogic";
import { resourceMessages as t } from "./messages";
import { MAX_EDIT_BYTES } from "./resourceLogic";

export interface MultiFileTabProps {
  /** 편집 중인 파일들(초안) */
  files: readonly FileEntry[];
  /** 서버에 있는 파일들(수정됨 표시용) */
  originFiles: readonly FileEntry[];
  onChange: (next: FileEntry[]) => void;
  /** 저장하다 실패한 파일의 서버 메시지(경로 -> 메시지) */
  errors?: Readonly<Record<string, string>>;
  /** 사용자가 그 파일을 고치기 시작했다(오류 표시를 치운다) */
  onDismissError?: (path: string) => void;
  /** 저장(편집기·트리 안 Ctrl+S) */
  onSave: () => void;
  /** 저장 중 등으로 편집을 막는다 */
  disabled?: boolean;
}

type NameMode = { kind: "file" } | { kind: "folder" } | { kind: "rename"; from: string; isFolder: boolean };
interface Target {
  path: string;
  kind: "file" | "folder";
}

/**
 * 여러 파일 리소스 본문 편집: 파일 트리(role=tree) + 선택한 파일 편집기.
 * 로컬 초안만 바꾸고(저장은 부모), 서버·종류 이름을 모른다. 키보드: 트리 `N` 새 파일, `F2` 이름 바꾸기, `Delete` 삭제, `F6` 트리/편집기.
 */
export function MultiFileTab({ files, originFiles, onChange, errors = {}, onDismissError, onSave, disabled = false }: MultiFileTabProps) {
  const toast = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [nameMode, setNameMode] = useState<NameMode | null>(null);
  const [nameValue, setNameValue] = useState("");
  const [nameProblem, setNameProblem] = useState<string | null>(null);
  const [confirmFolder, setConfirmFolder] = useState<string | null>(null);
  const [preview, setPreview] = useState(true);
  const [status, setStatus] = useState<TextEditorStatus>({ line: 1, col: 1, chars: 0 });
  const rootRef = useRef<HTMLDivElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const filesRef = useRef(files);
  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  const paths = useMemo(() => files.map((f) => f.path), [files]);
  const originByPath = useMemo(() => new Map(originFiles.map((f) => [f.path, f])), [originFiles]);
  const current = files.find((f) => f.path === selected);
  const errorCount = Object.keys(errors).length;

  const items: FileTreeItem[] = useMemo(
    () =>
      files.map((f) => {
        const changed = entryChanged(originByPath.get(f.path), f);
        const error = errors[f.path];
        return {
          path: f.path,
          trailing: (
            <>
              {error === undefined ? null : (
                <span role="img" aria-label={`${t.files.errorMark}: ${error}`} title={error} className="res-file-error">
                  !
                </span>
              )}
              {changed ? (
                <span role="img" aria-label={t.files.modified} title={t.files.modified}>
                  ●
                </span>
              ) : null}
            </>
          ),
        };
      }),
    [files, originByPath, errors],
  );

  const focusTree = () => rootRef.current?.querySelector<HTMLElement>('[role="treeitem"][tabindex="0"]')?.focus();
  const focusEditor = () => rootRef.current?.querySelector<HTMLElement>(".cm-content")?.focus();

  const beginName = (mode: NameMode, initial: string) => {
    setNameMode(mode);
    setNameValue(initial);
    setNameProblem(null);
  };
  const defaultDir = (): string => (target?.kind === "folder" ? `${target.path}/` : dirOf(selected ?? target?.path ?? ""));
  const startFile = () => beginName({ kind: "file" }, defaultDir());
  const startFolder = () => beginName({ kind: "folder" }, defaultDir());
  const startRename = () => {
    const t0 = target ?? (selected === null ? null : { path: selected, kind: "file" as const });
    if (t0 === null) return;
    const entry = files.find((f) => f.path === t0.path);
    if (t0.kind === "file" && entry?.text === null) {
      toast({ tone: "info", text: t.files.binaryNoRename });
      return;
    }
    beginName({ kind: "rename", from: t0.path, isFolder: t0.kind === "folder" }, t0.path);
  };
  const doRemove = (t0: Target | null) => {
    const tg = t0 ?? (selected === null ? null : { path: selected, kind: "file" as const });
    if (tg === null) return;
    if (tg.kind === "folder") {
      setConfirmFolder(tg.path);
      return;
    }
    removePath(tg.path);
  };
  const removePath = (path: string) => {
    const before = filesRef.current;
    const { files: next, removed } = removeEntries(before, path);
    if (removed === 0) return;
    const gone = before.filter((f) => !next.includes(f));
    onChange(next);
    if (selected !== null && gone.some((g) => g.path === selected)) setSelected(null);
    setTarget(null);
    toast({
      tone: "info",
      text: removed === 1 ? t.files.removed(path) : t.files.removedFolder(removed),
      action: { label: t.files.undo, onClick: () => onChange(sortEntries([...filesRef.current, ...gone.filter((g) => !filesRef.current.some((f) => f.path === g.path))])) },
    });
  };

  const submitName = (event: FormEvent) => {
    event.preventDefault();
    if (nameMode === null) return;
    const value = nameValue.trim();
    if (nameMode.kind === "folder") {
      const problem = checkPath(value.replace(/\/+$/, ""), []);
      if (problem !== null && problem !== "duplicate") return setNameProblem(t.files.problems[problem]);
      beginName({ kind: "file" }, `${value.replace(/\/+$/, "")}/`);
      return;
    }
    const ignore = nameMode.kind === "rename" ? nameMode.from : undefined;
    const others = nameMode.kind === "rename" && nameMode.isFolder ? paths.filter((p) => !p.startsWith(`${nameMode.from}/`)) : paths;
    const problem = checkPath(value, others, ignore);
    if (problem !== null) return setNameProblem(t.files.problems[problem]);
    if (nameMode.kind === "file") {
      onChange(sortEntries([...files, { path: value, text: "", size: 0 }]));
      setSelected(value);
      setNameMode(null);
      setTimeout(focusEditor, 0);
      return;
    }
    const { files: next, moved } = renameEntries(files, nameMode.from, value);
    const before = [...files];
    onChange(sortEntries(next));
    if (selected !== null) setSelected(renameEntries([{ path: selected, text: "", size: 0 }], nameMode.from, value).files[0]!.path);
    setNameMode(null);
    if (nameMode.isFolder) toast({ tone: "info", text: t.files.moved(moved), action: { label: t.files.undo, onClick: () => onChange(before) } });
    setTimeout(focusTree, 0);
  };

  const edit = (path: string, text: string) => {
    onChange(files.map((f) => (f.path === path ? { ...f, text } : f)));
    if (errors[path] !== undefined) onDismissError?.(path);
  };

  const onUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    let next: FileEntry[] = [...filesRef.current];
    let last: string | null = null;
    const skipped: string[] = [];
    for (const file of picked) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const path = `${current !== undefined && picked.length === 1 && current.text === null ? dirOf(current.path) : defaultDir()}${file.name}`;
      const problem = checkPath(path, next.map((f) => f.path).filter((p) => p !== path));
      if (problem !== null) {
        skipped.push(`${path}: ${t.files.problems[problem]}`);
        continue;
      }
      const text = decodeUtf8(bytes);
      const entry: FileEntry = text === null ? { path, text: null, size: bytes.length, bytes } : { path, text, size: bytes.length };
      if (file.type !== "") entry.mediaType = file.type;
      next = upsertEntry(next, entry);
      last = path;
    }
    onChange(sortEntries(next));
    if (last !== null) setSelected(last);
    if (skipped.length > 0) toast({ tone: "danger", text: t.files.uploadSkipped(skipped) });
  };

  const onTreeKeyDown = (event: KeyboardEvent) => {
    if (isImeKeyEvent(event) || disabled) return;
    const row = (event.target as HTMLElement).closest<HTMLElement>('[role="treeitem"]');
    const tg: Target | null = row === null ? null : { path: row.dataset["path"] ?? "", kind: row.dataset["kind"] === "folder" ? "folder" : "file" };
    if (event.key === "F2") {
      event.preventDefault();
      if (tg !== null) setTarget(tg);
      if (tg !== null) {
        const entry = files.find((f) => f.path === tg.path);
        if (tg.kind === "file" && entry?.text === null) toast({ tone: "info", text: t.files.binaryNoRename });
        else beginName({ kind: "rename", from: tg.path, isFolder: tg.kind === "folder" }, tg.path);
      }
    } else if (event.key === "Delete") {
      event.preventDefault();
      doRemove(tg);
    } else if (event.key === "n" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      startFile();
    } else if (event.key === "F6") {
      event.preventDefault();
      focusEditor();
    }
  };
  const onEditorKeyDown = (event: KeyboardEvent) => {
    if (event.key === "F6" || (event.key === "Escape" && !isImeKeyEvent(event))) {
      event.preventDefault();
      focusTree();
    }
  };

  const language = current === undefined ? "text" : languageForFile(current.path, current.mediaType);
  const canPreview = language === "markdown";

  return (
    <div className="res-files" ref={rootRef}>
      <div className="res-files-side">
        <div className="res-files-head">
          <strong>{t.files.heading(files.length)}</strong>
          {errorCount > 0 ? <span className="res-file-error" role="status">{t.files.saveFailedSummary(errorCount)}</span> : null}
        </div>
        <div className="res-files-toolbar" role="toolbar" aria-label={t.files.treeLabel}>
          <Button size="sm" onClick={startFile} disabled={disabled}>{t.files.addFile}</Button>
          <Button size="sm" onClick={startFolder} disabled={disabled}>{t.files.addFolder}</Button>
          <Button size="sm" onClick={startRename} disabled={disabled || (target === null && selected === null)}>{t.files.rename}</Button>
          <Button size="sm" variant="danger" onClick={() => doRemove(target)} disabled={disabled || (target === null && selected === null)}>{t.files.remove}</Button>
          <Button size="sm" onClick={() => uploadRef.current?.click()} disabled={disabled}>{t.files.upload}</Button>
          <input ref={uploadRef} type="file" multiple hidden aria-label={t.files.uploadLabel} onChange={(e) => void onUpload(e)} />
        </div>
        {nameMode === null ? null : (
          <form
            className="res-files-name"
            onSubmit={submitName}
            onKeyDown={(e) => {
              if (e.key !== "Escape") return;
              e.stopPropagation();
              setNameMode(null);
              focusTree();
            }}
          >
            <label>
              <span className="app-muted">{nameMode.kind === "folder" ? t.files.nameLabelFolder : nameMode.kind === "rename" ? t.files.nameLabelRename : t.files.nameLabelFile}</span>
              <input
                autoFocus
                className="lib-mono"
                value={nameValue}
                onChange={(e) => {
                  setNameValue(e.target.value);
                  setNameProblem(null);
                }}
                aria-invalid={nameProblem !== null}
                aria-describedby="res-files-name-problem"
              />
            </label>
            <span id="res-files-name-problem" role="alert" className="res-file-error">{nameProblem}</span>
            <span className="app-muted lib-field-note">{t.files.nameHint}</span>
            <span className="res-files-name-actions">
              <Button size="sm" type="submit" variant="primary">{t.files.nameConfirm}</Button>
              <Button size="sm" type="button" onClick={() => setNameMode(null)}>{t.files.nameCancel}</Button>
            </span>
          </form>
        )}
        <div
          className="res-files-tree"
          onKeyDown={onTreeKeyDown}
          onFocusCapture={(e) => {
            const row = (e.target as HTMLElement).closest<HTMLElement>('[role="treeitem"]');
            if (row !== null) setTarget({ path: row.dataset["path"] ?? "", kind: row.dataset["kind"] === "folder" ? "folder" : "file" });
          }}
        >
          {files.length === 0 ? <p className="app-muted">{t.files.empty}</p> : <FileTree items={items} ariaLabel={t.files.treeLabel} selected={selected} onSelect={(p) => {
            setSelected(p);
            setTarget({ path: p, kind: "file" });
          }} />}
        </div>
        <div className="res-files-total app-muted" data-testid="res-files-total">{t.files.total(formatBytes(totalSize(files)))}</div>
        <p className="app-muted lib-field-note">{t.files.keysHint}</p>
      </div>
      <div className="res-files-main" onKeyDown={onEditorKeyDown}>
        {current === undefined ? (
          <p className="app-muted res-files-empty">{t.files.pickFile}</p>
        ) : (
          <>
            <div className="res-content-bar">
              <strong className="lib-mono">{current.path}</strong>
              <span className="app-muted">{language} · {formatBytes(entrySize(current))}</span>
              {canPreview && current.text !== null ? (
                <label className="app-check">
                  <input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} />
                  {t.files.preview}
                </label>
              ) : null}
            </div>
            {errors[current.path] === undefined ? null : <Banner tone="danger">{errors[current.path]}</Banner>}
            {current.text === null ? (
              <div className="res-files-binary">
                <p>{t.files.notText(current.mediaType ?? "application/octet-stream", formatBytes(entrySize(current)), "")}</p>
                <div className="res-files-toolbar">
                  <Button onClick={() => uploadRef.current?.click()} disabled={disabled}>{t.files.replace}</Button>
                  <Button variant="danger" onClick={() => removePath(current.path)} disabled={disabled}>{t.files.remove}</Button>
                </div>
              </div>
            ) : (
              <div className="res-content-split" data-preview={canPreview && preview ? "true" : "false"} data-narrow="false">
                <div className="res-editor">
                  <LazyTextEditor
                    key={current.path}
                    value={current.text}
                    onChange={(text) => edit(current.path, text)}
                    language={language}
                    ariaLabel={t.files.editorLabel(current.path)}
                    onSave={onSave}
                    maxBytes={MAX_EDIT_BYTES}
                    onStatus={setStatus}
                    height="fill"
                    readOnly={disabled}
                    messages={{ tooLarge: t.content.tooLargeShort }}
                  />
                </div>
                {canPreview && preview ? (
                  <section className="res-preview" aria-label={t.files.preview}>
                    {current.text.trim() === "" ? <p className="app-muted">{t.content.previewEmpty}</p> : <Markdown text={current.text} />}
                  </section>
                ) : null}
              </div>
            )}
            {current.text === null ? null : <div className="res-statusline app-muted" role="status">{t.files.status(status.line, status.col, current.text.length, language)}</div>}
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirmFolder !== null}
        title={t.files.confirmFolderTitle}
        confirmLabel={t.files.confirmDelete}
        cancelLabel={t.files.cancel}
        danger
        onCancel={() => setConfirmFolder(null)}
        onConfirm={() => {
          if (confirmFolder !== null) removePath(confirmFolder);
          setConfirmFolder(null);
        }}
      >
        {confirmFolder === null ? null : t.files.confirmFolder(confirmFolder, files.filter((f) => f.path.startsWith(`${confirmFolder}/`)).length)}
      </ConfirmDialog>
    </div>
  );
}
