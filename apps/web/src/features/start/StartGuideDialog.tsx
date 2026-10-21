import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { Button, Dialog } from "@agent-console/ui";
import { StartGuide } from "./StartGuide";
import { startMessages } from "./messages";

export interface StartGuideDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * 첫 단계 안내를 대화상자로 다시 연다(도움말의 "시작 순서 다시 보기").
 * 열렸을 때만 안내를 그려 데이터를 받고, 단계 버튼으로 다른 화면에 가면 닫는다.
 */
export function StartGuideDialog({ open, onClose }: StartGuideDialogProps) {
  const { pathname } = useLocation();
  const opened = useRef(pathname);
  useEffect(() => {
    if (open) opened.current = pathname;
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (open && pathname !== opened.current) onClose();
  }, [open, pathname, onClose]);
  return (
    <Dialog open={open} title={startMessages.title} onClose={onClose} wide actions={<Button variant="primary" onClick={onClose}>{startMessages.close}</Button>}>
      <p className="app-muted">{startMessages.description}</p>
      {open ? <StartGuide /> : null}
    </Dialog>
  );
}
