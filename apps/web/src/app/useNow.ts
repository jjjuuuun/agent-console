import { useEffect, useState } from "react";

/** `active`인 동안 `intervalMs`마다 갱신되는 현재 시각(ms). 비활성이면 마지막 값을 유지한다. */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const handle = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(handle);
  }, [active, intervalMs]);
  return now;
}
