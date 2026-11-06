/**
 * 작업 행의 [실행 ▾] 메뉴(screen-sdd §7.3). 메뉴를 열 때 동작 목록을 읽는다(30초 캐시). 항목 이름은 `TaskAction.label` 그대로(프로필 이름은 데이터)이고,
 * 연동이 둘 이상 섞이면 연동 id 원문을 구분 제목으로 단다. 지금 쓸 수 없는 동작은 `aria-disabled` + 서버가 준 이유를 두 번째 줄에 보인다.
 * 데이터 읽기는 `useTaskActions`, 동작 시작은 부모가 준 콜백이다.
 */
import { useState, type KeyboardEvent } from "react";
import type { Issue } from "@agent-console/contracts";
import { Button, Popover } from "@agent-console/ui";
import type { ParsedTask, TaskAction } from "@agent-console/contracts/sdd";
import { ListSkeleton } from "./parts";
import { sddMessages as m } from "./messages";
import { useTaskActions } from "./useSddApi";

export interface TaskActionsMenuProps {
  specId: string;
  task: ParsedTask;
  /** 쓸 수 있는 동작을 골랐다 */
  onRun: (task: ParsedTask, action: TaskAction) => void;
  /** 막힌 동작을 눌렀다(관문이면 안내를 띄운다) */
  onBlockedPick?: (issue: Issue) => void;
  /** 시작 중이다 */
  busy?: boolean;
  /** 실행 자체가 막힌 이유(기록 파일 쓰기 불가 등). 있으면 메뉴를 열지 않는다 */
  blockedReason?: string | undefined;
}

export function TaskActionsMenu({ specId, task, onRun, onBlockedPick, busy = false, blockedReason }: TaskActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const actions = useTaskActions(specId, task.key, open && !blocked);
  const list = actions.data ?? [];
  const multi = new Set(list.map((a) => a.integration)).size > 1;

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'));
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? (at + 1) % items.length : e.key === "ArrowUp" ? (at - 1 + items.length) % items.length : e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : undefined;
    if (next === undefined || items.length === 0) return;
    e.preventDefault();
    items[next]?.focus();
  };

  return (
    <Popover
      open={open && !blocked}
      onOpenChange={(next) => setOpen(next && !blocked)}
      panelRole="menu"
      panelLabel={m.run.actionsLabel(task.title ?? task.key)}
      align="end"
      renderTrigger={(trigger) => (
        <Button size="sm" {...trigger} loading={busy} aria-disabled={blocked || undefined} title={blocked ? blockedReason : undefined} aria-label={`${task.key} ${m.run.action}`}>
          {m.run.action} ▾
        </Button>
      )}
    >
      {({ close }) => (
        <div className="sdd-actions-menu" onKeyDown={onKey} data-testid="sdd-actions-menu">
          {actions.isPending ? <ListSkeleton rows={2} /> : null}
          {actions.isError ? (
            <div className="sdd-actions-error" role="alert">
              <span>{m.run.error}</span>
              <Button size="sm" onClick={() => void actions.refetch()}>{m.run.retry}</Button>
            </div>
          ) : null}
          {actions.isSuccess && list.length === 0 ? <p className="app-muted sdd-actions-none" role="status">{m.run.none}</p> : null}
          {list.map((a, i) => {
            const issue = a.disabled ?? null;
            const heading = multi && (i === 0 || list[i - 1]?.integration !== a.integration);
            return (
              <div key={`${a.integration}:${a.id}`}>
                {heading ? <p className="sdd-actions-heading app-muted">{m.run.integration(a.integration)}</p> : null}
                <button
                  type="button"
                  role="menuitem"
                  className="sdd-action-item"
                  tabIndex={i === 0 ? 0 : -1}
                  aria-disabled={issue !== null || undefined}
                  onClick={() => {
                    if (issue !== null) {
                      onBlockedPick?.(issue);
                      close();
                      return;
                    }
                    onRun(task, a);
                    close();
                  }}
                >
                  <span className="ac-ellipsis">{a.label}</span>
                  {issue === null ? null : <span className="sdd-action-reason app-muted">{issue.message}</span>}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </Popover>
  );
}
