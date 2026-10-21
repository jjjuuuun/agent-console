import { useState } from "react";
import type { BackendDescriptor } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { useStorage } from "../../app/StorageContext";
import type { ProbeView } from "./hooks";
import { ProbeConfirmDialog } from "./ProbeConfirmDialog";
import { PROBE_CONFIRMED_KEY_PREFIX } from "./tones";

export interface BackendProbeButtonProps {
  descriptor: Pick<BackendDescriptor, "id" | "cost_note" | "probe_cost_note">;
  probe: Pick<ProbeView, "running" | "run">;
  size?: "sm" | "md";
}

/** [연결 테스트] 버튼. 누르면 확인 다이얼로그가 먼저 뜬다("다음부터 묻지 않기" 뒤에는 바로 실행). 호출은 `probe.run`뿐이다. */
export function BackendProbeButton({ descriptor, probe, size = "sm" }: BackendProbeButtonProps) {
  const storage = useStorage();
  const [asking, setAsking] = useState(false);
  const key = `${PROBE_CONFIRMED_KEY_PREFIX}${descriptor.id}`;
  const note = descriptor.probe_cost_note || descriptor.cost_note || undefined;
  return (
    <>
      <Button
        size={size}
        disabled={probe.running}
        onClick={() => {
          if (storage.get(key) === "1") probe.run();
          else setAsking(true);
        }}
      >
        {m.backendReadiness.probeButton}
      </Button>
      <ProbeConfirmDialog
        open={asking}
        costNote={note}
        onCancel={() => setAsking(false)}
        onConfirm={(remember) => {
          if (remember) storage.set(key, "1");
          setAsking(false);
          probe.run();
        }}
      />
    </>
  );
}
