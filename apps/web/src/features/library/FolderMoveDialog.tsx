import { useMemo, useRef, useState } from "react";
import { normalizeFolder } from "@agent-console/list-arrange";
import { Button, Dialog } from "@agent-console/ui";

export interface FolderMoveMessages {
  title: string;
  /** 대상 항목 이름이 든 안내 */
  target: (name: string) => string;
  search: string;
  listLabel: string;
  create: (folder: string) => string;
  clear: string;
  current: string;
  cancel: string;
}

export interface FolderMoveDialogProps {
  open: boolean;
  /** 옮길 항목 이름(안내용) */
  itemName: string;
  /** 지금 폴더(없으면 undefined) */
  current: string | undefined;
  /** 이미 있는 폴더 경로들 */
  folders: readonly string[];
  /** 폴더를 골랐다. `undefined`는 폴더 없음으로. */
  onPick: (folder: string | undefined) => void;
  onClose: () => void;
  messages: FolderMoveMessages;
}

/**
 * "폴더로 이동" 대화상자: 기존 폴더 목록 + 찾기 + 새 폴더 이름 입력 + 폴더 없음으로. 저장은 호출자가 한다(표현 전용).
 * 입력창에서 Enter: 입력과 같은 폴더가 있으면 그 폴더로, 없으면 새 폴더로.
 */
export function FolderMoveDialog({ open, itemName, current, folders, onPick, onClose, messages: m }: FolderMoveDialogProps) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const typed = normalizeFolder(query);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q === "" ? folders : folders.filter((f) => f.toLowerCase().includes(q));
  }, [folders, query]);
  const canCreate = typed !== undefined && !folders.includes(typed);
  const done = (folder: string | undefined) => {
    setQuery("");
    onPick(folder);
  };
  return (
    <Dialog
      open={open}
      title={m.title}
      size="sm"
      onClose={() => { setQuery(""); onClose(); }}
      initialFocus={input}
      actions={<Button onClick={() => { setQuery(""); onClose(); }}>{m.cancel}</Button>}
    >
      <p className="app-muted">{m.target(itemName)}</p>
      <input
        ref={input}
        type="search"
        className="ac-input"
        aria-label={m.search}
        placeholder={m.search}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
          e.preventDefault();
          if (typed !== undefined) done(typed);
        }}
      />
      <div role="group" aria-label={m.listLabel} className="lib-folder-list">
        {canCreate ? <button type="button" className="lib-folder-item" data-create="true" onClick={() => done(typed)}>{m.create(typed)}</button> : null}
        {shown.map((f) => (
          <button key={f} type="button" className="lib-folder-item" aria-current={f === current ? "true" : undefined} title={f} onClick={() => done(f)}>
            <span className="ac-ellipsis">{f}</span>
            {f === current ? <span className="app-muted">{m.current}</span> : null}
          </button>
        ))}
        {current !== undefined ? <button type="button" className="lib-folder-item" onClick={() => done(undefined)}>{m.clear}</button> : null}
      </div>
    </Dialog>
  );
}
