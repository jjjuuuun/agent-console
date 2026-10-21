import type { ReactNode } from "react";
import { messages as m } from "../../app/messages";
import { WirePreview } from "./widgets/RadioCardsWidget";

/**
 * 값별 미리보기 그림(정적 와이어). 키는 설정 JSON Pointer → 값 → 그림.
 * 여기에 없는 값(서버가 새로 추가한 enum)은 그림 없이 라디오로만 보인다.
 */
export const ENUM_PREVIEWS: Readonly<Record<string, Readonly<Record<string, ReactNode>>>> = {
  "/chat/reply_display": {
    separate: (
      <>
        <WirePreview rows={[{ width: 70, filled: true }, { width: 55, filled: true }, { width: 62, filled: true }]} />
        <span className="app-muted">{m.settings.replyDisplayPreview.separate}</span>
      </>
    ),
    merged: (
      <>
        <WirePreview rows={[{ width: 90, filled: true }, { width: 90, filled: true }, { width: 60, filled: true }]} />
        <span className="app-muted">{m.settings.replyDisplayPreview.merged}</span>
      </>
    ),
    final_only: (
      <>
        <WirePreview rows={[{ width: 60 }, { width: 60 }, { width: 80, filled: true }]} />
        <span className="app-muted">{m.settings.replyDisplayPreview.final_only}</span>
      </>
    ),
  },
};
