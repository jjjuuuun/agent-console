import { useCallback, useEffect, useRef, useState } from "react";
import type { Issue } from "@agent-console/contracts";

export type CheckPhase = "idle" | "checking" | "done" | "failed";

export interface DebouncedCheck {
  phase: CheckPhase;
  issues: readonly Issue[];
  retry: () => void;
}

/**
 * 입력이 멈춘 지 `delayMs` 뒤에 서버 검사(`run`)를 한 번 부른다. `key`가 바뀌면 다시 센다.
 * `paused`(IME 조합 중)이면 타이머를 걸지 않고 풀리면 다시 기다린다. 오래된 응답은 버리고, 요청이 실패하면 `failed`다(저장을 막을지는 호출자가 정한다).
 * 서버 호출은 주입받는다(`run`).
 */
export function useDebouncedCheck(key: string, run: () => Promise<readonly Issue[]>, enabled: boolean, delayMs: number, paused = false): DebouncedCheck {
  const [state, setState] = useState<{ phase: CheckPhase; issues: readonly Issue[]; key: string }>({ phase: "idle", issues: [], key: "" });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(run);
  useEffect(() => {
    latest.current = run;
  });
  const full = `${key}\u0000${nonce}`;
  const active = enabled && !paused;
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      latest.current().then(
        (issues) => {
          if (!cancelled) setState({ phase: "done", issues, key: full });
        },
        () => {
          if (!cancelled) setState({ phase: "failed", issues: [], key: full });
        },
      );
    }, delayMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [active, full, delayMs]);
  const retry = useCallback(() => setNonce((n) => n + 1), []);
  const stale = enabled && state.key !== full;
  return { phase: !enabled ? "idle" : stale ? "checking" : state.phase, issues: state.issues, retry };
}
