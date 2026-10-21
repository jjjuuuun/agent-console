import { Button } from "@agent-console/ui";
import { messages as m } from "../app/messages";
import type { SavePhase } from "./useDefinitionEditor";

export interface SaveStatusProps {
  dirty: boolean;
  phase: SavePhase;
  /** 실패 시 [다시 시도] */
  onRetry?: () => void;
}

/** 저장 상태 텍스트: 저장됨 / 저장 안 됨 / 저장 중… / 저장 실패 [다시 시도]. 색 단독이 아니라 글자와 점 모양으로도 전달한다. */
export function SaveStatus({ dirty, phase, onRetry }: SaveStatusProps) {
  const state = phase === "saving" ? "saving" : phase === "failed" ? "failed" : dirty ? "dirty" : "saved";
  const text = { saved: m.definition.saved, dirty: m.definition.dirty, saving: m.definition.saving, failed: m.definition.failed }[state];
  const mark = { saved: "✓", dirty: "●", saving: "…", failed: "▲" }[state];
  return (
    <span role="status" className="app-save-status" data-state={state}>
      <span aria-hidden="true">{mark}</span>
      {text}
      {state === "failed" && onRetry !== undefined ? (
        <Button size="sm" variant="ghost" onClick={onRetry}>
          {m.definition.retry}
        </Button>
      ) : null}
    </span>
  );
}
