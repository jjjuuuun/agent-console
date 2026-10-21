/**
 * 연결선 경고 칩(ux-overhaul §10.2 규칙 5). 표현 컴포넌트: "연결선 N개가 노드를 지납니다 · [자동 경로로]"와 닫기만 있고 데이터는 바꾸지 않는다.
 * 사후 토스트가 아니라 캔버스 상단 좌측에 붙는 `warning` 칩이다(하단의 미니맵·컨트롤·[정리]를 가리지 않는다).
 */
import type { ReactNode } from "react";
import { defaultMessages } from "../messages";
import type { GraphEditorMessages } from "../messages";
import { format } from "../messages";

export interface EdgeTroubleChipProps {
  /** 노드를 지나는 연결선 수 */
  count: number;
  /** [자동 경로로]. 없으면 버튼을 그리지 않는다 */
  onAutoRoute?: () => void;
  onDismiss: () => void;
  messages?: GraphEditorMessages;
  className?: string;
}

export function EdgeTroubleChip({ count, onAutoRoute, onDismiss, messages, className }: EdgeTroubleChipProps): ReactNode {
  const m = messages ?? defaultMessages;
  return (
    <div className={["ac-ge-trouble", className].filter(Boolean).join(" ")} role="status">
      <span className="ac-ge-trouble-text">{format(m.troubleHint, { count })}</span>
      {onAutoRoute !== undefined && (
        <>
          <span aria-hidden="true">·</span>
          <button type="button" className="ac-ge-btn" onClick={onAutoRoute}>
            {m.troubleAutoRoute}
          </button>
        </>
      )}
      <button type="button" className="ac-ge-btn" onClick={onDismiss}>
        {m.troubleDismiss}
      </button>
    </div>
  );
}
