/**
 * 작업 문법·작업 문서 선행 조건(작업·계획·추적 탭 공통). 문법이 꺼져 있거나 작업 역할 문서가 없으면 본문 대신 안내와 [규칙 열기]를 그린다.
 * 어느 쪽도 아니면 `ok`이고 호출자가 본문을 그린다.
 */
import type { ReactNode } from "react";
import { EmptyState } from "@agent-console/ui";
import { KNOWN_DOCUMENT_ROLES } from "@agent-console/contracts/constants";
import type { SpecView } from "@agent-console/contracts/sdd";
import { FailureBlock, ListSkeleton } from "./parts";
import { sddMessages as m } from "./messages";
import { useSpecSyntax } from "./useSddApi";

export type TaskPrereq = { state: "ok" } | { state: "pending" } | { state: "error"; error: unknown; retry: () => void } | { state: "syntaxMissing" } | { state: "noTaskDoc" };

export function useTaskPrereq(specId: string, view: SpecView): TaskPrereq {
  const syntax = useSpecSyntax(specId);
  const hasTaskDoc = (view.spec.documents ?? []).some((d) => (d.roles ?? []).includes(KNOWN_DOCUMENT_ROLES.TASKS));
  if (syntax.isPending) return { state: "pending" };
  if (syntax.isError) return { state: "error", error: syntax.error, retry: () => void syntax.refetch() };
  if (syntax.data?.empty === true) return { state: "syntaxMissing" };
  if (!hasTaskDoc) return { state: "noTaskDoc" };
  return { state: "ok" };
}

/** `ok`가 아닌 선행 조건의 본문. `ok`면 null. */
export function PrereqState({ prereq, onOpenRules, loadFailed }: { prereq: TaskPrereq; onOpenRules: () => void; loadFailed: string }): ReactNode {
  switch (prereq.state) {
    case "ok":
      return null;
    case "pending":
      return <ListSkeleton rows={8} />;
    case "error":
      return <FailureBlock error={prereq.error} title={loadFailed} onRetry={prereq.retry} />;
    case "syntaxMissing":
      return (
        <div className="sdd-state" data-testid="sdd-syntax-missing">
          <EmptyState title={m.tasks.syntaxMissing.title} description={m.tasks.syntaxMissing.body} action={<button type="button" className="app-link-btn" onClick={onOpenRules}>{m.tasks.syntaxMissing.open}</button>} />
        </div>
      );
    case "noTaskDoc":
      return (
        <div className="sdd-state" data-testid="sdd-no-task-doc">
          <EmptyState title={m.tasks.noTaskDoc.title} description={m.tasks.noTaskDoc.body} action={<button type="button" className="app-link-btn" onClick={onOpenRules}>{m.tasks.noTaskDoc.open}</button>} />
        </div>
      );
  }
}
