import { useState } from "react";
import { useNavigate } from "react-router";
import type { Issue, IssueSuggestion } from "@agent-console/contracts";
import { useResolvedFix } from "../../app/fix";
import { teamMessages as t } from "./messages";
import type { RowSuggestion } from "./issueRows";

export interface IssueActionsProps {
  /** 행의 대표 이슈(서버 `fix`를 읽는다) */
  issue: Issue;
  suggestions: readonly RowSuggestion[];
  /** 노드 설정 열기를 낼 수 있는가(노드가 있을 때) */
  canOpenNode: boolean;
  onApply: (issue: Issue, suggestion: IssueSuggestion) => void;
  onOpenNode: () => void;
  /** 바로 보일 최대 개수(나머지는 [더 보기]). 기본 2 */
  maxInline?: number;
}

interface Action {
  key: string;
  label: string;
  run: () => void;
}

/**
 * 이슈 행의 해결 버튼 줄: 서버 제안(같은 id는 합쳐 `(n개)`) -> `fix` -> [노드 설정 열기].
 * 제안·fix는 서버 데이터 그대로이고 이슈 코드는 해석하지 않는다.
 */
export function IssueActions({ issue, suggestions, canOpenNode, onApply, onOpenNode, maxInline = 2 }: IssueActionsProps) {
  const navigate = useNavigate();
  const fixes = useResolvedFix(issue.fix);
  const [open, setOpen] = useState(false);
  const actions: Action[] = [
    ...suggestions.map(({ suggestion, count }) => ({
      key: `s:${suggestion.id}`,
      label: count > 1 ? t.issues.actionUnsetCount(suggestion.label, count) : suggestion.label,
      run: () => onApply(issue, suggestion),
    })),
    ...fixes.map((f) => ({ key: `f:${f.to}`, label: f.label, run: () => void navigate(f.to) })),
    ...(canOpenNode ? [{ key: "open", label: t.issues.actionOpenNode, run: onOpenNode }] : []),
  ];
  if (actions.length === 0) return null;
  const inline = actions.length > maxInline ? actions.slice(0, maxInline) : actions;
  const rest = actions.slice(inline.length);
  return (
    <span className="team-issue-actions">
      {inline.map((a, i) => (
        <button key={a.key} type="button" className={i === 0 ? "ac-ge-btn ac-ge-btn--primary" : "ac-ge-btn"} onClick={a.run}>{a.label}</button>
      ))}
      {rest.length > 0 ? (
        <span className="team-issue-more">
          <button type="button" className="ac-ge-btn" aria-haspopup="menu" aria-expanded={open} aria-label={t.issues.actionMoreLabel} onClick={() => setOpen((v) => !v)}>
            {t.issues.actionMore} ▾
          </button>
          {open ? (
            <ul role="menu" className="ac-ge-menu">
              {rest.map((a) => (
                <li key={a.key} role="none">
                  <button type="button" role="menuitem" className="ac-ge-btn" onClick={() => { setOpen(false); a.run(); }}>{a.label}</button>
                </li>
              ))}
            </ul>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
