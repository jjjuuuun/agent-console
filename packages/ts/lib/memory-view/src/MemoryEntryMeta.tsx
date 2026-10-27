import type { MemoryEntry, MemoryEntrySummary } from "@agent-console/contracts/memory";
import { useId, useState, type KeyboardEvent } from "react";
import { formatBytes, formatTimestamp } from "./format";
import { formatMessage, resolveMessages } from "./messages";
import { formatAuthor, type FormatAuthorOptions, type ScopeLabel } from "./scopes";

/** 본문 저장과 함께 한 번의 PUT으로 가는 값(태그·형식·고정). 보관은 즉시 호출이라 따로 둔다. */
export interface MemoryMetaDraft {
  tags: readonly string[];
  contentType: string;
  pinned: boolean;
}

export interface MemoryEntryMetaProps {
  entry: MemoryEntry | MemoryEntrySummary;
  /** 범위 라벨(`scopeLabel` 결과). 칩은 라벨의 상태에서 만든다. */
  scope: ScopeLabel;
  /** 편집 중인 값. 생략하면 항목 값을 읽기만 한다(`onChange` 없이). */
  draft?: MemoryMetaDraft;
  onDraftChange?: (next: MemoryMetaDraft) => void;
  /** 보관 스위치는 즉시 호출이다. */
  onArchivedChange?: (archived: boolean) => void;
  readOnly?: boolean;
  /** 형식 입력 제안(현재 범위에서 쓰인 값). 코드에 고정된 목록은 없다. */
  contentTypeSuggestions?: readonly string[];
  authorOptions?: FormatAuthorOptions;
  onOpenHistory?: () => void;
  /** 복사 단추를 낸다(클립보드는 앱이 다룬다). */
  onCopy?: (text: string) => void;
  /** 실행 열기(역할 `runs`가 있을 때만 앱이 넘긴다). 없으면 실행 id를 글자로만 보인다. */
  onOpenRun?: (runId: string) => void;
  /** 한 번에 보이는 태그 수(넘으면 `+N`으로 접힘). 기본 8. */
  maxVisibleTags?: number;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 항목 정보 영역(2열 격자): 범위·버전·크기·해시·만든 이·고친 이·태그·형식·고정·보관.
 * 태그 입력은 Enter·쉼표·Tab으로 확정하고(IME 조합 중에는 무시) 중복은 무시한다.
 */
export function MemoryEntryMeta({
  entry, scope, draft, onDraftChange, onArchivedChange, readOnly = false, contentTypeSuggestions = [], authorOptions, onOpenHistory, onCopy, onOpenRun,
  maxVisibleTags = 8, messages: custom, className,
}: MemoryEntryMetaProps) {
  const m = resolveMessages(custom);
  const uid = useId();
  const value: MemoryMetaDraft = draft ?? { tags: entry.tags ?? [], contentType: entry.content_type ?? "", pinned: entry.pinned === true };
  const editable = !readOnly && onDraftChange !== undefined;
  const [input, setInput] = useState("");
  const [expanded, setExpanded] = useState(false);
  const set = (patch: Partial<MemoryMetaDraft>) => onDraftChange?.({ ...value, ...patch });
  const addTag = (raw: string): boolean => {
    const tag = raw.trim();
    if (!tag) return false;
    if (!value.tags.includes(tag)) set({ tags: [...value.tags, tag] });
    return true;
  };
  const onTagKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing || e.key === "Process") return;
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (addTag(input)) setInput("");
    } else if (e.key === "Tab" && input.trim() !== "") {
      e.preventDefault();
      if (addTag(input)) setInput("");
    } else if (e.key === "Backspace" && input === "" && value.tags.length > 0) {
      set({ tags: value.tags.slice(0, -1) });
    }
  };
  const created = formatAuthor(entry.created_by, authorOptions);
  const updated = formatAuthor(entry.updated_by, authorOptions);
  const hidden = !expanded ? Math.max(0, value.tags.length - maxVisibleTags) : 0;
  const shownTags = hidden > 0 ? value.tags.slice(0, maxVisibleTags) : value.tags;

  const authorCell = (a: ReturnType<typeof formatAuthor>, at: number, runId?: string | null, link?: boolean) => (
    <span className="ac-mem-meta-author">
      <span className={`${a.chip ? "ac-mem-chip" : ""}${a.mono ? " ac-mem-mono" : ""}`.trim() || undefined} title={a.tooltip}>{a.text}</span>
      {a.ruleId ? <span className="ac-mem-mono">{a.ruleId}</span> : null}
      <span className="ac-mem-muted">{formatTimestamp(at)}</span>
      {link && runId ? (onOpenRun ? <button type="button" className="ac-mem-linkbtn" onClick={() => onOpenRun(runId)}>{m["detail.openRun"]} ↗</button> : <span className="ac-mem-mono ac-mem-muted">{runId}</span>) : null}
    </span>
  );
  const cell = (id: string, label: string, body: React.ReactNode, wide = false) => (
    <div className="ac-mem-meta-cell" data-wide={wide ? "" : undefined}>
      <dt id={`${uid}-${id}`}>{label}</dt>
      <dd aria-labelledby={`${uid}-${id}`}>{body}</dd>
    </div>
  );
  const sw = (id: string, label: string, tip: string, checked: boolean, onChange: ((v: boolean) => void) | undefined) => (
    <label className="ac-mem-switch" title={tip}>
      <input type="checkbox" role="switch" checked={checked} disabled={!onChange} onChange={(e) => onChange?.(e.target.checked)} aria-label={label} aria-describedby={`${uid}-${id}-tip`} />
      <span>{checked ? m["detail.on"] : m["detail.off"]}</span>
      <span id={`${uid}-${id}-tip`} className="ac-mem-sr">{tip}</span>
    </label>
  );

  return (
    <section className={`ac-mem-root ac-mem-meta${className ? ` ${className}` : ""}`} aria-label={m["detail.info"]}>
      <dl className="ac-mem-meta-grid">
        {cell("scope", m["detail.scope"] as string, (
          <span className="ac-mem-meta-scope">
            {scope.parts.map((p, i) => <span key={i} className={p.mono ? "ac-mem-mono" : undefined}>{i > 0 ? " / " : ""}{p.text}</span>)}
            {scope.unknownKind ? <span className="ac-mem-chip" data-tone="warning">{m["scope.unknownKind"]}</span> : null}
            {scope.disabledKind ? <span className="ac-mem-chip" data-tone="warning">{m["scope.disabledKind"]}</span> : null}
            {scope.deleted ? <span className="ac-mem-chip" data-tone="warning">{m["scope.deleted"]}</span> : null}
          </span>
        ))}
        {cell("version", m["detail.version"] as string, (
          <span>v{entry.version}{onOpenHistory ? <> <button type="button" className="ac-mem-linkbtn" onClick={onOpenHistory}>{m["detail.history"]}</button></> : null}</span>
        ))}
        {cell("size", m["detail.size"] as string, <span title={formatMessage(m["detail.bytesExact"] as string, { n: entry.bytes.toLocaleString("en-US") })}>{formatBytes(entry.bytes, m)}</span>)}
        {cell("hash", m["detail.hash"] as string, (
          <span className="ac-mem-meta-hash" title={entry.sha256}>
            <span className="ac-mem-mono">{entry.sha256.slice(0, 12)}</span>
            {onCopy ? <button type="button" className="ac-mem-iconbtn" aria-label={`${m["detail.hash"]} ${m["detail.copy"]}`} title={`${m["detail.hash"]} ${m["detail.copy"]}`} onClick={() => onCopy(entry.sha256)}><span aria-hidden="true">⧉</span></button> : null}
          </span>
        ))}
        {cell("created", m["detail.createdBy"] as string, authorCell(created, entry.created_at))}
        {cell("updated", m["detail.updatedBy"] as string, authorCell(updated, entry.updated_at, entry.updated_by.run_id, true))}
        {cell("tags", m["detail.tags"] as string, (
          <span className="ac-mem-taginput">
            {shownTags.map((t) => (
              <span key={t} className="ac-mem-chip ac-mem-tag">
                <span className="ac-ellipsis" title={t}>{t}</span>
                {editable ? (
                  <button type="button" className="ac-mem-chip-x" aria-label={formatMessage(m["detail.tagRemove"] as string, { tag: t })} title={formatMessage(m["detail.tagRemove"] as string, { tag: t })} onClick={() => set({ tags: value.tags.filter((x) => x !== t) })}><span aria-hidden="true">✕</span></button>
                ) : null}
              </span>
            ))}
            {hidden > 0 ? <button type="button" className="ac-mem-chip" onClick={() => setExpanded(true)}>{formatMessage(m["detail.tagsMore"] as string, { n: hidden })}</button> : null}
            {expanded && value.tags.length > maxVisibleTags ? <button type="button" className="ac-mem-linkbtn" onClick={() => setExpanded(false)}>{m["detail.tagsLess"]}</button> : null}
            {editable ? (
              <input type="text" className="ac-mem-input ac-mem-taginput-field" value={input} aria-label={m["detail.tagInput"]} onChange={(e) => setInput(e.target.value)} onKeyDown={onTagKey}
                onBlur={() => { if (addTag(input)) setInput(""); }} />
            ) : null}
          </span>
        ), true)}
        {cell("type", m["detail.contentType"] as string, editable ? (
          <>
            <input type="text" className="ac-mem-input" list={`${uid}-types`} value={value.contentType} onChange={(e) => set({ contentType: e.target.value })} aria-labelledby={`${uid}-type`} />
            <datalist id={`${uid}-types`}>{contentTypeSuggestions.map((t) => <option key={t} value={t} />)}</datalist>
          </>
        ) : <span className="ac-mem-mono">{value.contentType}</span>)}
        {cell("pinned", m["detail.pinned"] as string, sw("pinned", m["detail.pinned"] as string, m["detail.pinned.tip"] as string, value.pinned, editable ? (v) => set({ pinned: v }) : undefined))}
        {cell("archived", m["detail.archived"] as string, sw("archived", m["detail.archived"] as string, m["detail.archived.tip"] as string, entry.archived === true, readOnly ? undefined : onArchivedChange))}
      </dl>
    </section>
  );
}
