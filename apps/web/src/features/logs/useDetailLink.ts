import { useCallback, useRef } from "react";
import type { LogEventTableHandle } from "@agent-console/log-view";
import type { LogDetailPanelHandle } from "./LogDetailPanel";

/**
 * 이벤트 표와 상세 패널을 잇는 명령형 연결(DOM을 읽지 않고 두 컴포넌트의 `ref` API만 쓴다).
 * - `onActivate`: 표에서 이미 선택된 행에 `Enter`를 다시 누르면 패널의 탭 줄로 포커스를 옮긴다.
 * - `reveal`: 근거·관련 항목을 눌러 선택을 바꿀 때 표가 그 행으로 스크롤한다(표에 없으면 아무 일도 없다).
 */
export function useDetailLink(selectedUid: string | null) {
  const tableRef = useRef<LogEventTableHandle>(null);
  const panelRef = useRef<LogDetailPanelHandle>(null);
  const onActivate = useCallback(
    (uid: string) => {
      if (uid === selectedUid) panelRef.current?.focusTabs();
    },
    [selectedUid],
  );
  const reveal = useCallback((uid: string) => {
    tableRef.current?.scrollToUid(uid, { align: "center" });
  }, []);
  return { tableRef, panelRef, onActivate, reveal };
}
