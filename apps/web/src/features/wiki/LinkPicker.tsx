/** 링크 넣기: 페이지 고르기 대화상자(screen-wiki §6.6). 불러온 페이지 목록에서 제목·경로로 거르고 가상 목록으로 보인다. 글자는 서버가 만든다(이 부품은 대상 경로만 돌려준다). */
import { useMemo, useRef, useState } from "react";
import { Dialog } from "@agent-console/ui";
import { VirtualList } from "@agent-console/wiki-view";
import type { WikiPageSummary } from "@agent-console/contracts/wiki";
import { isImeKeyEvent } from "../../lib/ime";
import { wikiMessages as m } from "./messages";

export interface LinkPickerProps {
  open: boolean;
  pages: readonly WikiPageSummary[];
  /** 지금 편집 중인 페이지(목록에서 뺀다) */
  currentPath?: string | null;
  onPick: (path: string) => void;
  onClose: () => void;
}

export function LinkPicker({ open, pages, currentPath = null, onPick, onClose }: LinkPickerProps) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return pages.filter((p) => p.path !== currentPath && (needle === "" || `${p.title ?? ""} ${p.path}`.toLowerCase().includes(needle)));
  }, [pages, q, currentPath]);
  const clamp = Math.min(active, Math.max(0, shown.length - 1));
  return (
    <Dialog open={open} title={m.editor.pickPage} size="sm" onClose={onClose} initialFocus={input}>
      <div className="wiki-form">
        <input
          ref={input}
          type="search"
          className="wiki-input"
          aria-label={m.editor.pickFilter}
          placeholder={m.editor.pickFilter}
          value={q}
          role="combobox"
          aria-expanded="true"
          aria-controls="wiki-link-picker-list"
          aria-activedescendant={shown.length > 0 ? `wiki-link-picker-opt${clamp}` : undefined}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (isImeKeyEvent(e.nativeEvent)) return;
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive(Math.min(clamp + 1, shown.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive(Math.max(clamp - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              const hit = shown[clamp];
              if (hit !== undefined) onPick(hit.path);
            }
          }}
        />
        <div id="wiki-link-picker-list">
          <VirtualList
            items={shown}
            rowHeight={40}
            height={Math.min(280, Math.max(40, shown.length * 40))}
            role="listbox"
            ariaLabel={m.editor.pickPage}
            activeIndex={clamp}
            getKey={(p) => p.path}
            renderRow={(p, ctx) => (
              <div
                key={p.path}
                id={`wiki-link-picker-opt${ctx.index}`}
                role="option"
                aria-selected={ctx.index === clamp}
                className="wiki-picker-row"
                style={ctx.style}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => onPick(p.path)}
              >
                <span className="ac-ellipsis wiki-picker-title">{p.title !== undefined && p.title !== "" ? p.title : p.path}</span>
                <span className="ac-mono-wrap ac-ellipsis app-muted">{p.path}</span>
              </div>
            )}
          />
        </div>
      </div>
    </Dialog>
  );
}
