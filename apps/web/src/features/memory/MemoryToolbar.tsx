/**
 * 도구줄: [범위 ▾](2칸일 때) · 검색(`/`) · [태그 ▾] · [쓴 주체 ▾] · 보관/지운 항목 포함 · [정렬 ▾] · 새로고침·상태.
 * 값은 모두 props(주소 상태)이고 바꾸려는 값은 콜백으로만 낸다. 검색은 입력이 멈춘 뒤 300ms에 질의하고 한글 조합 중에는 질의하지 않는다.
 */
import { useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { Choice, Icon, Popover, Spinner } from "@agent-console/ui";
import { MemorySortMenu, type SortState } from "@agent-console/memory-view";
import { isImeKeyEvent } from "../../lib/ime";
import { AUTHOR_KIND_FILTERS, ENTRY_SORTS, MEMORY_LIMITS } from "./memoryConfig";
import { memoryMessages as t } from "./messages";
import { useMemoryTags } from "./useMemoryApi";
import type { MemoryViewState } from "./memoryUrl";

export interface MemoryToolbarProps {
  view: MemoryViewState;
  onChange: (patch: Partial<MemoryViewState>) => void;
  /** 2칸일 때 맨 앞에 놓는 범위 고르기(팝오버 트리거 포함). 3칸이면 null */
  scopePicker: ReactNode;
  /** 검색 입력(`/` 단축키가 포커스를 준다) */
  searchRef: Ref<HTMLInputElement>;
  refreshing: boolean;
  onRefresh: () => void;
  disconnected: boolean;
  /** 서버 경고 `검색 폴백`이 있어 3글자 미만이 느릴 수 있다 */
  searchSlow: boolean;
}

function SearchBox({ value, onCommit, inputRef, placeholder }: { value: string; onCommit: (q: string) => void; inputRef: Ref<HTMLInputElement>; placeholder: string }) {
  const [text, setText] = useState(value);
  const [seen, setSeen] = useState(value);
  const composing = useRef(false);
  // 주소의 검색어가 밖에서 바뀌었으면(칩·필터 지우기) 입력도 따라간다(렌더 중 보정).
  if (seen !== value) {
    setSeen(value);
    setText(value);
  }
  const latest = useRef(onCommit);
  useEffect(() => {
    latest.current = onCommit;
  });
  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => {
      if (!composing.current) latest.current(text);
    }, MEMORY_LIMITS.searchDebounceMs);
    return () => clearTimeout(timer);
  }, [text, value]);
  return (
    <div className="mem-search">
      <Icon name="filter" size={14} />
      <input
        ref={inputRef}
        type="search"
        role="searchbox"
        className="mem-search-input"
        aria-label={t.toolbar.searchLabel}
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onCompositionStart={() => (composing.current = true)}
        onCompositionEnd={(e) => {
          composing.current = false;
          setText(e.currentTarget.value);
          onCommit(e.currentTarget.value);
        }}
        onKeyDown={(e) => {
          if (isImeKeyEvent(e)) return;
          if (e.key === "Enter") onCommit(text);
          else if (e.key === "Escape") {
            if (text !== "") {
              e.stopPropagation();
              setText("");
              onCommit("");
            } else {
              (e.currentTarget as HTMLInputElement).blur();
              document.querySelector<HTMLElement>(".ac-mem-tr[tabindex='0']")?.focus();
            }
          }
        }}
      />
      {text !== "" ? (
        <button type="button" className="mem-iconbtn" aria-label={t.toolbar.searchClear} title={t.toolbar.searchClear} onClick={() => (setText(""), onCommit(""))}>
          <Icon name="close" size={12} />
        </button>
      ) : null}
    </div>
  );
}

function TagPopover({ view, onChange }: Pick<MemoryToolbarProps, "view" | "onChange">) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const tags = useMemoryTags(view.scope, view.includeArchived, open);
  const shown = (tags.data?.tags ?? []).filter((x) => x.tag.toLowerCase().includes(filter.trim().toLowerCase()));
  const pick = (tag: string | null) => {
    onChange({ tag });
    setOpen(false);
  };
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelLabel={t.tags.list}
      panelClassName="mem-pop"
      renderTrigger={(p) => (
        <button {...p} type="button" className="mem-tool" data-active={view.tag !== null ? "" : undefined}>
          {view.tag === null ? t.toolbar.tag : t.chip.tag(view.tag)} <Icon name="chevron-down" size={12} />
        </button>
      )}
    >
      <div className="mem-pop-body">
        <input
          className="mem-input"
          aria-label={t.tags.inputLabel}
          placeholder={t.tags.placeholder}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !isImeKeyEvent(e) && filter.trim() !== "") {
              e.preventDefault();
              pick(filter.trim());
            }
          }}
        />
        {tags.isPending ? (
          <div className="mem-skeleton" role="status" aria-label={t.loading}><Spinner /></div>
        ) : tags.isError ? (
          <p className="mem-error" role="alert">
            {t.tags.error} <button type="button" className="mem-linkbtn" onClick={() => void tags.refetch()}>{t.retry}</button>
          </p>
        ) : (
          <ul className="mem-taglist" aria-label={t.tags.list}>
            {shown.length === 0 ? <li className="mem-muted">{t.tags.empty}</li> : null}
            {shown.map((x) => (
              <li key={x.tag}>
                <Choice checked={view.tag === x.tag} onChange={() => pick(view.tag === x.tag ? null : x.tag)}>
                  <span className="ac-ellipsis" title={x.tag}>{x.tag}</span> <span className="mem-muted">{x.entries.toLocaleString("ko-KR")}</span>
                </Choice>
              </li>
            ))}
          </ul>
        )}
        {tags.data?.truncated === true ? <p className="mem-help">{t.tags.truncated}</p> : null}
      </div>
    </Popover>
  );
}

function AuthorPopover({ view, onChange }: Pick<MemoryToolbarProps, "view" | "onChange">) {
  const [open, setOpen] = useState(false);
  const current = view.authorKind ?? "";
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelLabel={t.toolbar.authorKind}
      panelClassName="mem-pop"
      renderTrigger={(p) => (
        <button {...p} type="button" className="mem-tool" data-active={current !== "" ? "" : undefined}>
          {current === "" ? t.toolbar.authorKind : t.chip.authorKind(t.authorKind[current] ?? current)} <Icon name="chevron-down" size={12} />
        </button>
      )}
    >
      <div className="mem-pop-body" role="radiogroup" aria-label={t.toolbar.authorKind}>
        {AUTHOR_KIND_FILTERS.map((kind) => (
          <Choice
            key={kind === "" ? "all" : kind}
            kind="radio"
            name="mem-author-kind"
            checked={current === kind}
            onChange={() => {
              onChange({ authorKind: kind === "" ? null : kind });
              setOpen(false);
            }}
          >
            {kind === "" ? t.authorKind["all"] : (t.authorKind[kind] ?? kind)}
          </Choice>
        ))}
      </div>
    </Popover>
  );
}

function SortPopover({ view, onChange }: Pick<MemoryToolbarProps, "view" | "onChange">) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelLabel={t.toolbar.sort}
      panelClassName="mem-pop"
      align="end"
      renderTrigger={(p) => (
        <button {...p} type="button" className="mem-tool" data-active={view.sort !== null ? "" : undefined}>
          {t.toolbar.sort} <Icon name="chevron-down" size={12} />
        </button>
      )}
    >
      <MemorySortMenu sorts={ENTRY_SORTS} value={view.sort satisfies SortState | null} onChange={(sort) => onChange({ sort })} />
    </Popover>
  );
}

export function MemoryToolbar({ view, onChange, scopePicker, searchRef, refreshing, onRefresh, disconnected, searchSlow }: MemoryToolbarProps) {
  return (
    <div className="mem-toolbar" role="toolbar" aria-label={t.toolbar.label}>
      {scopePicker}
      <SearchBox value={view.q} inputRef={searchRef} placeholder={t.toolbar.search} onCommit={(q) => onChange({ q })} />
      <TagPopover view={view} onChange={onChange} />
      <AuthorPopover view={view} onChange={onChange} />
      <Choice checked={view.includeArchived} onChange={(e) => onChange({ includeArchived: e.target.checked })}>{t.toolbar.includeArchived}</Choice>
      <Choice checked={view.includeDeleted} onChange={(e) => onChange({ includeDeleted: e.target.checked })}>{t.toolbar.includeDeleted}</Choice>
      <SortPopover view={view} onChange={onChange} />
      <span className="mem-toolbar-end">
        {searchSlow && view.q.trim() !== "" && [...view.q.trim()].length < 3 ? <span className="mem-muted" role="status">{t.toolbar.searchSlow}</span> : null}
        {disconnected ? (
          <span className="mem-warn" role="status">
            <span className="mem-mark" aria-hidden="true" /> {t.live.disconnected}{" "}
            <button type="button" className="mem-linkbtn" onClick={onRefresh}>{t.live.refresh}</button>
          </span>
        ) : null}
        {refreshing ? <Spinner label={t.toolbar.refreshing} /> : null}
        <button type="button" className="mem-iconbtn" aria-label={t.toolbar.refresh} title={t.toolbar.refresh} onClick={onRefresh}>
          <Icon name="refresh" />
        </button>
      </span>
    </div>
  );
}
