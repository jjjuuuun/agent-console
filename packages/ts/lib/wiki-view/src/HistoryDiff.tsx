import { TextDiff } from "@agent-console/text-editor";
import { useState } from "react";
import { formatMessage, resolveMessages } from "./messages";

/** 비교 기준 */
export type HistoryDiffBase = "previous" | "current";

export interface HistoryDiffProps {
  /** 보고 있는 버전 번호 */
  version: number;
  /** 그 버전의 본문 */
  content: string;
  /** 바로 앞 버전 본문. 없으면(첫 버전) 현재 본문과 비교로 자동 전환한다. */
  previousContent?: string | null;
  /** 지금 페이지 본문 */
  currentContent: string;
  /** 기준(제어형). 없으면 안에서 관리: 기본 이전 버전, 이전이 없으면 현재. */
  base?: HistoryDiffBase;
  onBaseChange?: (base: HistoryDiffBase) => void;
  onClose?: () => void;
  language?: string;
  maxHeight?: number;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 기록 비교(읽기 전용). text-editor `TextDiff`로 `이전 버전과` / `현재 본문과`를 보인다. `Esc`로 닫는다.
 * 첫 버전은 이전 버전이 없다는 안내와 함께 현재 본문과 비교한다.
 */
export function HistoryDiff({
  version, content, previousContent = null, currentContent, base, onBaseChange, onClose, language = "markdown", maxHeight = 480, messages, className,
}: HistoryDiffProps) {
  const t = resolveMessages(messages);
  const hasPrevious = previousContent !== null;
  const [inner, setInner] = useState<HistoryDiffBase>(hasPrevious ? "previous" : "current");
  const effective: HistoryDiffBase = !hasPrevious ? "current" : (base ?? inner);
  const choose = (b: HistoryDiffBase) => {
    if (b === "previous" && !hasPrevious) return;
    setInner(b);
    onBaseChange?.(b);
  };
  // 기준 ↔ 이 버전: 이전 버전과 = (이전 → 이 버전), 현재와 = (이 버전 → 현재)
  const before = effective === "previous" ? (previousContent ?? "") : content;
  const after = effective === "previous" ? content : currentContent;
  const same = before === after;
  return (
    <section
      className={`ac-wk-root ac-wk-diff${className ? ` ${className}` : ""}`}
      aria-label={formatMessage(t["diff.label"], { v: version })}
      onKeyDown={(e) => {
        if (e.key === "Escape" && onClose) {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="ac-wk-inline ac-wk-diff-head">
        <span className="ac-wk-mono">v{version}</span>
        <div role="group" aria-label={t["diff.base"]} className="ac-wk-segment">
          <button type="button" className="ac-wk-btn" aria-pressed={effective === "previous"} aria-disabled={!hasPrevious || undefined} onClick={() => choose("previous")}>
            {t["diff.base.previous"]}
          </button>
          <button type="button" className="ac-wk-btn" aria-pressed={effective === "current"} onClick={() => choose("current")}>
            {t["diff.base.current"]}
          </button>
        </div>
        <span className="ac-wk-grow" />
        {onClose ? <button type="button" className="ac-wk-btn" onClick={onClose}>{t["common.close"]}</button> : null}
      </div>
      {!hasPrevious ? <p className="ac-wk-banner" data-tone="info" role="status">{t["diff.noPrevious"]}</p> : null}
      {same ? (
        <p className="ac-wk-muted" role="status">{t["diff.same"]}</p>
      ) : (
        <TextDiff before={before} after={after} language={language} ariaLabel={formatMessage(t["diff.label"], { v: version })} maxHeight={maxHeight} />
      )}
    </section>
  );
}
