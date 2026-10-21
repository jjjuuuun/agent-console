import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Issue } from "@agent-console/contracts";
import { Banner, Button, useToast } from "@agent-console/ui";
import { selectMoves, moveTargetOfIssue, MOVE_TO_SHARED_SUGGESTION_ID } from "@agent-console/projects";
import { describeError } from "../../app/errors";
import { useInvalidateLists } from "../library";
import { projectMessages as t } from "./messages";
import { useProjects } from "./ProjectsContext";

export interface MoveIssueToShared {
  /** 이 제안 id가 "공용으로 옮기기"인가 */
  handles: (suggestionId: string) => boolean;
  /** 이슈가 가리키는 정의를 공용으로 옮긴다(계획을 받아 필수 이동만 적용). 성공 여부를 돌려준다 */
  run: (issue: Issue) => Promise<boolean>;
}

/**
 * 범위 경고의 [공용으로 옮기기] 제안을 처리하는 훅. 제안 버튼이 있는 어느 화면이든 `handles`로 가르고 `run`을 부른다.
 * 프로젝트 기능이 꺼져 있으면 `handles`가 항상 false다.
 */
export function useMoveIssueToShared(): MoveIssueToShared {
  const p = useProjects();
  const toast = useToast();
  const invalidate = useInvalidateLists();
  const { client, enabled } = p;
  const handles = useCallback((id: string) => enabled && id === MOVE_TO_SHARED_SUGGESTION_ID, [enabled]);
  const run = useCallback(
    async (issue: Issue) => {
      const target = moveTargetOfIssue(issue);
      if (client === undefined || target === null) return false;
      try {
        const plan = await client.getMovePlan({ kind: target.kind, id: target.id, to: null });
        await client.applyMove(selectMoves(plan));
        await invalidate();
        toast({ tone: "success", text: t.scopeIssue.moved });
        return true;
      } catch (e) {
        toast({ tone: "danger", text: describeError(e, t.scopeIssue.moveFailed).message });
        return false;
      }
    },
    [client, invalidate, toast],
  );
  return { handles, run };
}

/** 워크스페이스 전체의 범위 경고 목록(설정 > 프로젝트). 경고가 없으면 아무것도 그리지 않는다. */
export function ScopeIssuesList() {
  const p = useProjects();
  const mover = useMoveIssueToShared();
  const { client } = p;
  const q = useQuery({ queryKey: ["list", "project-scope-issues"], queryFn: () => (client as NonNullable<typeof client>).listScopeIssues(), enabled: client !== undefined, retry: false });
  const issues = q.data ?? [];
  if (issues.length === 0) return null;
  return (
    <Banner tone="warning" title={t.scopeIssue.title(issues.length)}>
      <ul className="lib-issue-list">
        {issues.map((issue, i) => {
          const canMove = moveTargetOfIssue(issue) !== null;
          return (
            <li key={`${issue.code}-${i}`} className="prj-issue">
              <span>{issue.message}</span>
              {canMove ? <Button size="sm" onClick={() => void mover.run(issue).then((ok) => { if (ok) void q.refetch(); })}>{t.scopeIssue.moveToShared}</Button> : null}
            </li>
          );
        })}
      </ul>
    </Banner>
  );
}
