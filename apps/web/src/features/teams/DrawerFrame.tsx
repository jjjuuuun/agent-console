import { useState, type KeyboardEvent, type ReactNode } from "react";
import { Banner, Button, ConfirmDialog, Drawer } from "@agent-console/ui";
import { teamMessages as t } from "./messages";

export interface DrawerFrameProps {
  title: string;
  note: string;
  /** 입력한 것이 있는가: 있으면 닫기 전에 확인한다 */
  dirty: boolean;
  canSubmit: boolean;
  busy: boolean;
  /** 실패 문구(서랍은 닫지 않고 위쪽에 보인다) */
  error: string | null;
  submitLabel: string;
  onSubmit: () => void;
  onClose: () => void;
  /** 버튼 위 줄에 끼울 내용(붙일 곳 라디오 등) */
  footerExtra?: ReactNode;
  children: ReactNode;
  testId?: string;
}

/** 만들기 서랍의 공통 틀: 안내 한 줄, 실패 배너, 하단 고정 [만들고 추가]·[취소], Ctrl+Enter 제출, 닫기 전 확인. 정의 종류를 모른다. */
export function DrawerFrame({ title, note, dirty, canSubmit, busy, error, submitLabel, onSubmit, onClose, footerExtra, children, testId }: DrawerFrameProps) {
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const close = () => {
    if (busy) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && canSubmit && !busy) {
      e.preventDefault();
      onSubmit();
    }
  };
  return (
    <>
      <Drawer
        open
        title={title}
        description={note}
        closeLabel={t.drawer.close}
        onClose={close}
        width={560}
        {...(testId === undefined ? {} : { testId })}
        actions={
          <div className="team-drawer-foot">
            {footerExtra}
            <div className="team-drawer-buttons">
              <Button onClick={close} disabled={busy}>{t.drawer.cancel}</Button>
              <Button variant="primary" loading={busy} disabled={!canSubmit} title={t.drawer.submitHint} aria-keyshortcuts="Control+Enter" onClick={onSubmit}>
                {submitLabel}
              </Button>
            </div>
          </div>
        }
      >
        <div className="team-drawer-body" onKeyDown={onKeyDown}>
          {error ? <Banner tone="danger" role="alert">{error}</Banner> : null}
          {children}
        </div>
      </Drawer>
      <ConfirmDialog
        open={confirmDiscard}
        title={t.drawer.discardTitle}
        confirmLabel={t.drawer.discardConfirm}
        cancelLabel={t.drawer.discardKeep}
        danger
        onConfirm={() => {
          setConfirmDiscard(false);
          onClose();
        }}
        onCancel={() => setConfirmDiscard(false)}
      >
        <p className="ac-text">{t.drawer.discardBody}</p>
      </ConfirmDialog>
    </>
  );
}
