/**
 * 저장하지 않은 변경 보호. 같은 화면 안의 이동(다른 행 고르기·항목 닫기·새 항목)은 `guard(action)`으로 감싸고,
 * 다른 화면으로 가는 라우트 이동·탭 닫기는 자동으로 막는다. 확인 창: [취소](기본 포커스) [버리고 이동] [저장하고 이동].
 */
import { useCallback, useRef, useState, type ReactNode } from "react";
import { useBlocker } from "react-router";
import { Button, Dialog } from "@agent-console/ui";
import { useReportUnsaved } from "../../definition/unsaved";
import { memoryMessages as t } from "./messages";

export interface LeaveGuard {
  /** 변경이 없으면 바로 `action`을 부르고, 있으면 확인 창을 띄워 고른 뒤에 부른다. */
  guard: (action: () => void) => void;
  dialog: ReactNode;
}

/**
 * @param dirty 저장하지 않은 변경이 있는가
 * @param save 저장(성공하면 true). 없으면 [저장하고 이동]이 없다(새 항목 작성 중처럼 저장이 곧 만들기인 경우)
 * @param discard 변경을 버린다(이동 전에 호출)
 */
export function useLeaveGuard(dirty: boolean, save: (() => Promise<boolean>) | undefined, discard: () => void): LeaveGuard {
  useReportUnsaved(dirty);
  const [pending, setPending] = useState<{ run: () => void } | null>(null);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [saving, setSaving] = useState(false);

  const guard = useCallback(
    (action: () => void) => {
      if (!dirty) action();
      else setPending({ run: action });
    },
    [dirty],
  );

  const routeBlocked = blocker.state === "blocked";
  const open = pending !== null || routeBlocked;
  const cancel = () => {
    setPending(null);
    if (blocker.state === "blocked") blocker.reset();
  };
  const proceed = (after: () => void) => {
    const run = pending?.run;
    setPending(null);
    after();
    if (run !== undefined) run();
    else if (blocker.state === "blocked") blocker.proceed();
  };

  const dialog = (
    <Dialog
      open={open}
      size="sm"
      title={t.leave.title}
      onClose={cancel}
      initialFocus={cancelRef}
      actions={
        <>
          <Button ref={cancelRef} onClick={cancel}>{t.leave.cancel}</Button>
          <Button variant="danger" onClick={() => proceed(discard)}>{t.leave.discard}</Button>
          {save === undefined ? null : (
            <Button
              variant="primary"
              loading={saving}
              onClick={() => {
                setSaving(true);
                void save()
                  .then((ok) => ok && proceed(() => undefined))
                  .finally(() => setSaving(false));
              }}
            >
              {t.leave.save}
            </Button>
          )}
        </>
      }
    >
      <p className="ac-text">{t.leave.body}</p>
    </Dialog>
  );
  return { guard, dialog };
}
