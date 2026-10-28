/**
 * 새 항목 모드(상세 칸에서 같은 자리를 쓴다). 범위·키·형식·태그·고정·본문을 받아 `POST /memory/entries`.
 * 키는 입력 중 규칙을 검사하고(IME 조합 중에는 보류) 서버 검사가 최종이다. 같은 범위·키가 있으면 409 → 필드 아래 오류 + [열기].
 */
import { useEffect, useId, useRef, useState } from "react";
import { Banner, Button } from "@agent-console/ui";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts/constants";
import type { MemoryEntry, MemoryScopeKindInfo, MemoryScopeRef, MemoryScopeSummary, MemorySecretRejectedDetails } from "@agent-console/contracts/memory";
import { MemoryEntryEditor, keyErrorText, secretRejectedField, validateKey, type MemoryEntryEditorHandle } from "@agent-console/memory-view";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { isImeKeyEvent } from "../../lib/ime";
import { memoryMessages as t } from "./messages";
import { viewMessages } from "./format";
import { pickOf, pickedScope, ScopePicker, type ScopePickerState } from "./ScopePicker";
import { SecretBand } from "./SecretBand";
import { useMemoryContext } from "./useMemoryContext";

export interface NewEntryFormProps {
  /** 처음 채울 범위(지금 보는 범위). 없으면 비워 둔다 */
  initialScope: MemoryScopeRef | null;
  /** 처음 채울 본문(지운 항목의 내 내용을 새 항목으로 저장할 때) */
  initialContent?: string;
  kinds: readonly MemoryScopeKindInfo[];
  scopes: readonly MemoryScopeSummary[];
  labelOf: (scope: MemoryScopeRef) => string;
  maxBytes: number | null;
  /** 만들기에 성공했다 */
  onCreated: (entry: MemoryEntry) => void;
  /** 이미 있는 항목 열기(409) */
  onOpenExisting: (entryId: string) => void;
  onCancel: () => void;
  /** 내용이 바뀌었는지 알린다(이탈 확인용) */
  onDirtyChange?: (dirty: boolean) => void;
}

export function NewEntryForm({ initialScope, initialContent = "", kinds, scopes, labelOf, maxBytes, onCreated, onOpenExisting, onCancel, onDirtyChange }: NewEntryFormProps) {
  const { rest } = useApi();
  const ctx = useMemoryContext();
  const uid = useId();
  const [pick, setPick] = useState<ScopePickerState>(() => pickOf(initialScope));
  const [key, setKey] = useState("");
  const [checkedKey, setCheckedKey] = useState("");
  const composing = useRef(false);
  const [contentType, setContentType] = useState("");
  const [tagText, setTagText] = useState("");
  const [pinned, setPinned] = useState(false);
  const [content, setContent] = useState(initialContent);
  const [busy, setBusy] = useState(false);
  const [existing, setExisting] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ field: "content" | "key" | "tags" | null } | null>(null);
  const editorRef = useRef<MemoryEntryEditorHandle>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const tagRef = useRef<HTMLInputElement>(null);

  const scope = pickedScope(pick, kinds);
  const keyCode = checkedKey === "" && key === "" ? null : validateKey(checkedKey);
  const keyError = keyCode === null ? null : keyErrorText(keyCode, checkedKey, viewMessages);
  const dirty = key !== "" || content !== initialContent || tagText !== "" || contentType !== "" || pinned;
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);
  const tags = tagText.split(",").map((x) => x.trim()).filter((x, i, a) => x !== "" && a.indexOf(x) === i);
  const canCreate = scope !== null && key !== "" && validateKey(key) === null && !busy;

  const touch = () => {
    setExisting(null);
    setFailure(null);
    setSecret(null);
  };

  const create = async () => {
    if (scope === null || !canCreate) return;
    setBusy(true);
    setExisting(null);
    setFailure(null);
    setSecret(null);
    try {
      const created = await rest.createMemoryEntry({
        scope,
        key,
        content,
        ...(contentType.trim() === "" ? {} : { content_type: contentType.trim() }),
        ...(tags.length === 0 ? {} : { tags }),
        ...(pinned ? { pinned: true } : {}),
      });
      onCreated(created);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const id = e.details["entry_id"];
        setExisting(typeof id === "string" ? id : "");
      } else if (e instanceof ApiError && e.code === ERROR_CODES.MEMORY_SECRET_REJECTED) {
        setSecret({ field: secretRejectedField((e.details as Partial<MemorySecretRejectedDetails>).field) });
      } else {
        setFailure(describeError(e, t.newEntry.createFailed).message);
      }
    } finally {
      setBusy(false);
    }
  };

  const goTo = (field: "content" | "key" | "tags" | null) => {
    if (field === "key") keyRef.current?.focus();
    else if (field === "tags") tagRef.current?.focus();
    else document.querySelector<HTMLElement>(".mem-new .cm-content")?.focus();
  };

  return (
    <form
      className="mem-new"
      aria-label={t.newEntry.title}
      onSubmit={(e) => {
        e.preventDefault();
        void create();
      }}
      onKeyDown={(e) => {
        // 한글 조합을 확정하는 Enter가 폼 제출로 새지 않게 한다
        if (e.key === "Enter" && isImeKeyEvent(e)) e.preventDefault();
        if (e.key === "Escape" && !(e.nativeEvent.isComposing || e.keyCode === 229)) {
          e.stopPropagation();
          onCancel();
        }
      }}
    >
      <div className="mem-detail-head">
        <h2 className="mem-detail-title">{t.newEntry.title}</h2>
        <div className="mem-detail-actions">
          <Button type="button" onClick={onCancel}>{t.newEntry.cancel}</Button>
          <Button type="submit" variant="primary" disabled={!canCreate} loading={busy}>{t.newEntry.create}</Button>
        </div>
      </div>
      {secret !== null ? <SecretBand field={secret.field} onGo={() => goTo(secret.field)} /> : null}
      {failure !== null ? <Banner tone="danger" className="mem-band">{failure}</Banner> : null}
      <div className="mem-new-fields">
        <ScopePicker
          label={t.newEntry.scope}
          kinds={kinds}
          scopes={scopes}
          state={pick}
          labelOf={labelOf}
          pickers={ctx.pickers}
          onChange={(next) => {
            setPick(next);
            touch();
          }}
        />
        <div className="mem-field">
          <label htmlFor={`${uid}-key`} className="mem-label">{t.newEntry.key}</label>
          <input
            ref={keyRef}
            id={`${uid}-key`}
            className="mem-input mem-mono"
            value={key}
            placeholder={t.newEntry.keyPlaceholder}
            aria-invalid={keyError !== null || existing !== null}
            aria-describedby={`${uid}-key-err`}
            onCompositionStart={() => (composing.current = true)}
            onCompositionEnd={(e) => {
              composing.current = false;
              setCheckedKey(e.currentTarget.value);
            }}
            onChange={(e) => {
              setKey(e.target.value);
              if (!composing.current) setCheckedKey(e.target.value);
              touch();
            }}
          />
          <span id={`${uid}-key-err`} className="mem-error" role={keyError !== null || existing !== null ? "alert" : undefined}>
            {keyError ?? (existing !== null ? t.newEntry.exists : "")}
            {existing !== null && existing !== "" ? (
              <>
                {" "}
                <button type="button" className="mem-linkbtn" onClick={() => onOpenExisting(existing)}>{t.newEntry.open}</button>
              </>
            ) : null}
          </span>
        </div>
        <div className="mem-field-row">
          <div className="mem-field">
            <label htmlFor={`${uid}-ct`} className="mem-label">{viewMessages["detail.contentType"]}</label>
            <input id={`${uid}-ct`} className="mem-input" value={contentType} placeholder="text/markdown" onChange={(e) => (setContentType(e.target.value), touch())} />
          </div>
          <div className="mem-field">
            <label htmlFor={`${uid}-tags`} className="mem-label">{viewMessages["detail.tags"]}</label>
            <input ref={tagRef} id={`${uid}-tags`} className="mem-input" value={tagText} placeholder="a, b" onChange={(e) => (setTagText(e.target.value), touch())} />
          </div>
          <label className="mem-check">
            <input type="checkbox" checked={pinned} onChange={(e) => (setPinned(e.target.checked), touch())} />
            <span>{viewMessages["detail.pinned"]}</span>
          </label>
        </div>
      </div>
      <div className="mem-new-editor" data-ac-editable>
        <MemoryEntryEditor
          value={content}
          onChange={(v) => (setContent(v), touch())}
          entryKey={key === "" ? t.newEntry.title : key}
          contentType={contentType === "" ? null : contentType}
          saveState={busy ? "saving" : dirty ? "dirty" : "saved"}
          maxBytes={maxBytes}
          onSave={() => void create()}
          handleRef={editorRef}
        />
      </div>
    </form>
  );
}

