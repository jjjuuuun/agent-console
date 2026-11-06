/** 자동 진행 멈춤·다시 시작(컨테이너 훅). 응답이 오면 스펙 질의를 다시 읽고, 실패는 `error` 문구로 돌려준다. */
import { useState } from "react";
import { ApiError } from "@agent-console/api-client";
import type { SddAutomationOp } from "@agent-console/api-client";
import { sddMessages as m } from "./messages";
import { useInvalidateSdd, useSddSpace } from "./useSddApi";

export interface AutomationControl {
  control: (op: SddAutomationOp) => Promise<void>;
  busy: boolean;
  error: string | null;
}

export function useAutomationControl(specId: string): AutomationControl {
  const space = useSddSpace();
  const invalidate = useInvalidateSdd();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const control = async (op: SddAutomationOp) => {
    setBusy(true);
    setError(null);
    try {
      await space.client.controlAutomation(specId, op);
      await invalidate();
    } catch (e) {
      setError(e instanceof ApiError && e.message !== "" ? e.message : m.automation.stopFailed);
    } finally {
      setBusy(false);
    }
  };
  return { control, busy, error };
}
