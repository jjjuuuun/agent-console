/**
 * 머리의 본문 검색(screen-wiki §6.7): 250ms 디바운스(IME 조합 중 보류) → `GET …/search` → 입력 칸 아래 결과 패널(`SearchResults`).
 * `↑↓` 이동 · `Enter` 열기 · `Esc` 닫기(입력 유지). 필터(폴더·태그)는 불러온 페이지 목록에서 만든다. 조각은 서버가 비밀을 가린 글이고 강조 범위는 서버 `marks`다.
 */
import { useId, useMemo, useRef, useState, type Ref } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Popover } from "@agent-console/ui";
import { SearchResults, searchOptionId, allFolders, type SearchResultsHandle } from "@agent-console/wiki-view";
import type { WikiPageSummary } from "@agent-console/contracts/wiki";
import { useWikiSpace } from "./useWikiApi";
import { DebouncedInput } from "./parts";
import { WIKI_LIMITS } from "./wikiConfig";
import { wikiMessages as m } from "./messages";

export interface WikiSearchProps {
  wikiId: string;
  /** 필터 후보를 만드는 페이지 목록(없어도 검색은 된다) */
  pages: readonly WikiPageSummary[];
  onOpen: (path: string) => void;
  inputRef?: Ref<HTMLInputElement>;
}

export function WikiSearch({ wikiId, pages, onOpen, inputRef }: WikiSearchProps) {
  const space = useWikiSpace();
  const baseId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const listId = `wikisr${baseId}`;
  const [q, setQ] = useState("");
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [prefix, setPrefix] = useState("");
  const [tags, setTags] = useState<readonly string[]>([]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [active, setActive] = useState(0);
  const handle = useRef<SearchResultsHandle>(null);
  const folders = useMemo(() => allFolders(pages).slice().sort(), [pages]);
  const allTags = useMemo(() => [...new Set(pages.flatMap((p) => p.tags ?? []))].sort(), [pages]);
  const text = q.trim();
  const search = useQuery({
    queryKey: ["wiki", space.key, "wiki", wikiId, "search", text, prefix, tags.join("\u0000")],
    queryFn: ({ signal }) => space.client.searchWiki(wikiId, { q: text, ...(prefix === "" ? {} : { prefix }), ...(tags.length === 0 ? {} : { tags }), limit: WIKI_LIMITS.searchLimit }, signal),
    enabled: text !== "",
    retry: false,
    staleTime: 0,
  });
  const hits = search.data?.items ?? [];
  const open = focused && !dismissed && text !== "";
  const filters = (prefix === "" ? 0 : 1) + tags.length;
  const optionsId = active < hits.length ? searchOptionId(listId, active) : undefined;

  return (
    <div className="wiki-search-wrap" data-focused={focused || undefined}>
      <DebouncedInput
        value={q}
        onCommit={(next) => {
          setQ(next);
          setDismissed(false);
          setActive(0);
        }}
        label={m.search.label}
        placeholder={m.search.placeholder}
        className="wiki-search wiki-search-input"
        inputRef={inputRef}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 120)}
        aria={{ "aria-controls": open ? listId : undefined, "aria-expanded": open, "aria-activedescendant": open ? optionsId : undefined, "aria-autocomplete": "list" }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setDismissed(false);
            handle.current?.move(1);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            handle.current?.move(-1);
          } else if (e.key === "Enter" && open && hits.length > 0) {
            e.preventDefault();
            handle.current?.openActive();
          } else if (e.key === "Escape" && open) {
            e.stopPropagation();
            setDismissed(true);
          }
        }}
      />
      <Popover
        open={filterOpen}
        onOpenChange={setFilterOpen}
        panelRole="dialog"
        panelLabel={m.search.filter}
        renderTrigger={(trigger) => <Button size="sm" {...trigger}>{filters === 0 ? m.search.filter : m.search.filterN(filters)} ▾</Button>}
      >
        <div className="wiki-filter-panel">
          <label className="wiki-field">
            <span className="wiki-label">{m.search.folder}</span>
            <select className="wiki-input" value={prefix} onChange={(e) => setPrefix(e.target.value)}>
              <option value="">{m.search.folderAll}</option>
              {folders.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          {allTags.length === 0 ? null : (
            <fieldset className="wiki-field">
              <legend className="wiki-label">{m.search.tags}</legend>
              {allTags.map((t) => (
                <label key={t} className="ac-choice">
                  <input type="checkbox" checked={tags.includes(t)} onChange={(e) => setTags(e.target.checked ? [...tags, t] : tags.filter((x) => x !== t))} />
                  <span>{t}</span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
      </Popover>
      {open ? (
        <div className="wiki-search-panel" onMouseDown={(e) => e.preventDefault()} data-testid="wiki-search-panel">
          {search.isError ? (
            <p className="app-field-error" role="alert">{m.search.failed}</p>
          ) : search.isPending ? (
            <p className="app-muted" role="status">{m.search.searching}</p>
          ) : (
            <SearchResults
              hits={hits}
              query={text}
              degraded={search.data?.degraded === true}
              truncated={search.data?.truncated === true}
              activeIndex={active}
              onActiveChange={setActive}
              id={listId}
              handleRef={handle}
              onOpen={(hit) => {
                setDismissed(true);
                onOpen(hit.path);
              }}
            />
          )}
        </div>
      ) : null}
    </div>
  );
}
