import { useState } from "react";
import type { Issue, IssueSuggestion } from "@agent-console/contracts";
import type { GraphEditorMessages } from "../messages";
import { defaultMessages } from "../messages";

export interface IssueSuggestionButtonsProps {
  issue: Issue;
  /** 제안 버튼 클릭. 적용(그래프 patch)은 호출자가 편집기 `applySuggestion` 등으로 한다 */
  onApply: (issue: Issue, suggestion: IssueSuggestion) => void;
  /** 바로 보일 최대 개수(나머지는 [더 보기] 메뉴). 기본 3 */
  maxInline?: number;
  /** 주 버튼(채워진 강조색)으로 그린다. 기본 false */
  primary?: boolean;
  messages?: GraphEditorMessages;
}

/** 이슈의 서버 제안(`Issue.suggestions`)을 버튼으로 그린다. 이슈 코드를 해석하지 않으며, 제안이 없으면 아무것도 그리지 않는다. */
export function IssueSuggestionButtons(props: IssueSuggestionButtonsProps) {
  const m = props.messages ?? defaultMessages;
  const [open, setOpen] = useState(false);
  const all = props.issue.suggestions ?? [];
  if (all.length === 0) return null;
  const max = props.maxInline ?? 3;
  const inline = all.length > max ? all.slice(0, max) : all;
  const rest = all.slice(inline.length);
  return (
    <span className="ac-ge-suggestions">
      {inline.map((s) => (
        <button key={s.id} type="button" className={props.primary === true ? "ac-ge-btn ac-ge-btn--primary" : "ac-ge-btn"} onClick={() => props.onApply(props.issue, s)}>
          {s.label}
        </button>
      ))}
      {rest.length > 0 && (
        <span className="ac-ge-suggestions-more">
          <button type="button" className="ac-ge-btn" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((v) => !v)}>
            {m.suggestionMore}
          </button>
          {open && (
            <ul role="menu" className="ac-ge-menu">
              {rest.map((s) => (
                <li key={s.id} role="none">
                  <button
                    type="button"
                    role="menuitem"
                    className="ac-ge-btn"
                    onClick={() => {
                      setOpen(false);
                      props.onApply(props.issue, s);
                    }}
                  >
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </span>
      )}
    </span>
  );
}
