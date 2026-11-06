import type { WikiAuthor } from "@agent-console/contracts/wiki";
import { ToneChip } from "@agent-console/markdown-doc";
import { authorFacts, authorLabel, resolveDisplay, type WikiDisplay } from "./display";
import { formatMessage, resolveMessages } from "./messages";

export interface OpChipProps {
  /** 기록 동작 값(열린 문자열). 표시 표에 없으면 원문 + 중립. */
  op: string;
  display?: WikiDisplay;
  size?: "dense" | "normal";
}

/** 기록 동작 칩. 동작 이름·톤은 `display.ops`(데이터)가 정한다. */
export function OpChip({ op, display, size }: OpChipProps) {
  const d = resolveDisplay(display?.ops, op);
  return <ToneChip label={d.label} tone={d.tone} title={d.hint ?? d.label} {...(size ? { size } : {})} />;
}

export interface AuthorChipProps {
  author: WikiAuthor;
  display?: WikiDisplay;
  /** 실행 링크: 실행 id를 받아 그 화면으로 보낸다. 없으면 실행 id는 글자만(역할 `runs`가 없는 조립). */
  onOpenRun?: (runId: string, rootRunId: string | null) => void;
  /** 한 줄 작게 */
  size?: "dense" | "normal";
  messages?: Readonly<Record<string, string>>;
}

/**
 * 쓴 주체 칩 = 아이콘 + `label ?? agent_id ?? 종류 표시`, 실행이 있으면 `실행 {id 앞 8자}`.
 * 종류별 아이콘·이름은 `display.authorKinds`가 정하고 모르는 종류는 원문 + 중립 아이콘이다. 툴팁에 에이전트·노드·실행 값을 모은다.
 */
export function AuthorChip({ author, display, onOpenRun, size = "dense", messages }: AuthorChipProps) {
  const t = resolveMessages(messages);
  const kind = resolveDisplay(display?.authorKinds, author.kind);
  const label = authorLabel(author, display);
  const facts = authorFacts(author);
  const tip = [
    facts.agentId ? formatMessage(t["author.tip.agent"], { id: facts.agentId }) : null,
    facts.nodePath ? formatMessage(t["author.tip.node"], { path: facts.nodePath }) : null,
    facts.runId ? formatMessage(t["author.tip.run"], { id: facts.runId }) : null,
  ].filter((s): s is string => s !== null);
  const runId = author.run_id ?? null;
  return (
    <span className="ac-wk-author" data-size={size}>
      <span className="ac-wk-chip" data-tone={kind.tone} data-kind-icon={kind.icon ?? "neutral"} title={tip.length > 0 ? tip.join(" · ") : kind.hint ?? label}>
        <span className="ac-wk-chip-icon" aria-hidden="true" />
        <span className="ac-wk-chip-text">{label}</span>
      </span>
      {runId ? (
        onOpenRun ? (
          <button type="button" className="ac-wk-linkbtn ac-wk-mono" onClick={() => onOpenRun(runId, author.root_run_id ?? null)}>
            {formatMessage(t["author.run"], { id: runId.slice(0, 8) })}
          </button>
        ) : (
          <span className="ac-wk-mono ac-wk-muted">{formatMessage(t["author.run"], { id: runId.slice(0, 8) })}</span>
        )
      ) : null}
    </span>
  );
}
