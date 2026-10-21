import { useCallback, useEffect, useRef, useState } from "react";
import type { Graph, Issue } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";

/** 초안 변경 뒤 자동 검증까지 기다리는 시간(ms, 5.2R.9) */
export const VALIDATION_DEBOUNCE_MS = 400;

export interface ValidationState {
  phase: "idle" | "running" | "failed";
  issues: Issue[];
  /** 마지막으로 성공한 검증이 있는가(실패해도 기존 이슈를 흐리게 보인다) */
  validated: boolean;
}

/**
 * 팀 구성 초안을 서버에서 검증한다(`POST /graphs/{id}/validate`). 초안이 바뀌면 `delayMs` 뒤에 자동으로 다시 하고,
 * `validateNow`로 즉시 할 수 있다. 응답은 마지막 요청 것만 받는다. 이슈 코드는 해석하지 않는다.
 */
export function useValidation(graphId: string, graph: Graph | undefined, delayMs = VALIDATION_DEBOUNCE_MS): ValidationState & { validateNow: () => void } {
  const { rest } = useApi();
  const [state, setState] = useState<ValidationState>({ phase: "idle", issues: [], validated: false });
  const seq = useRef(0);
  const latest = useRef(graph);
  useEffect(() => {
    latest.current = graph;
  });

  const run = useCallback(async () => {
    const g = latest.current;
    if (g === undefined) return;
    const mine = ++seq.current;
    setState((s) => ({ ...s, phase: "running" }));
    try {
      const issues = await rest.validateGraph(graphId, g);
      if (mine === seq.current) setState({ phase: "idle", issues, validated: true });
    } catch {
      if (mine === seq.current) setState((s) => ({ ...s, phase: "failed" }));
    }
  }, [rest, graphId]);

  const first = useRef(true);
  useEffect(() => {
    if (graph === undefined) return;
    const wait = first.current ? 0 : delayMs;
    first.current = false;
    const handle = setTimeout(() => void run(), wait);
    return () => clearTimeout(handle);
  }, [graph, delayMs, run]);

  return { ...state, validateNow: () => void run() };
}
