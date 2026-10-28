import { useCallback, useEffect, useRef, useState } from "react";
import type { MemoryRetentionPlan } from "@agent-console/contracts/memory";

type Obj = Record<string, unknown>;

export interface RetentionPreviewState {
  /** 미리보기에 쓴 규칙의 지문(`ruleKey`) */
  key: string | null;
  plan: MemoryRetentionPlan | null;
  /** 미리보기를 한 시각(Unix epoch 초) */
  at: number | null;
  loading: boolean;
  error: boolean;
  /** 규칙 id → 그 규칙을 미리보기했을 때의 규칙 지문(규칙별 "미리보기 안 함" 표지용) */
  seen: Readonly<Record<string, string>>;
}

export const ruleKey = (rules: readonly Obj[]): string => JSON.stringify(rules);
const ruleId = (r: Obj): string => (typeof r["id"] === "string" ? r["id"] : "");

const EMPTY: RetentionPreviewState = { key: null, plan: null, at: null, loading: false, error: false, seen: {} };

/**
 * 정리 미리보기 상태 훅. 호출(`run`)은 주입받고, 규칙이 0개면 호출하지 않는다. 오래된 응답은 버린다.
 * 규칙 지문이 바뀌어도 이전 결과는 남기되 `key`가 달라져 "다시 미리보기" 상태가 된다.
 */
export function useRetentionPreview(run: (rules: Obj[]) => Promise<MemoryRetentionPlan>, now: () => number = () => Math.floor(Date.now() / 1000)) {
  const [state, setState] = useState<RetentionPreviewState>(EMPTY);
  const seq = useRef(0);
  const latest = useRef({ run, now });
  useEffect(() => {
    latest.current = { run, now };
  });
  const preview = useCallback((rules: Obj[]) => {
    if (rules.length === 0) return;
    const mine = ++seq.current;
    const key = ruleKey(rules);
    setState((s) => ({ ...s, loading: true, error: false }));
    latest.current.run(rules).then(
      (plan) => {
        if (mine !== seq.current) return;
        setState({ key, plan, at: latest.current.now(), loading: false, error: false, seen: Object.fromEntries(rules.map((r) => [ruleId(r), JSON.stringify(r)])) });
      },
      () => {
        if (mine === seq.current) setState((s) => ({ ...s, loading: false, error: true }));
      },
    );
  }, []);
  const reset = useCallback(() => {
    seq.current++;
    setState(EMPTY);
  }, []);
  return { state, preview, reset };
}
