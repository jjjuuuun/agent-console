import type { Issue } from "@agent-console/contracts";
import { useEffect, useRef, useState } from "react";

/** 저장 경고를 다음 화면으로 넘기는 라우터 state 키 */
const KEY = "savedIssues";

/** `navigate(path, { state })`에 넣을 값. 경고가 없으면 undefined(state를 만들지 않는다). */
export function savedIssuesState(issues: readonly Issue[] | undefined): { [KEY]: readonly Issue[] } | undefined {
  return issues === undefined || issues.length === 0 ? undefined : { [KEY]: issues };
}

/** 라우터 state에서 넘어온 저장 경고를 읽는다(모양이 다르면 빈 목록). */
export function readSavedIssues(state: unknown): readonly Issue[] {
  if (typeof state !== "object" || state === null) return [];
  const v = (state as Record<string, unknown>)[KEY];
  return Array.isArray(v) ? v.filter((x): x is Issue => typeof x === "object" && x !== null && typeof (x as Issue).message === "string") : [];
}

/**
 * 화면에 보일 저장 경고: 이 화면에서 저장해 경고가 갱신되면(빈 목록 포함) 그것을, 그 전에는 이전 화면에서 만들며 받은 경고를 보인다.
 * @param own 이 화면 편집기의 마지막 저장 경고
 * @param carried 이전 화면에서 넘어온 경고(`readSavedIssues(location.state)`)
 */
export function useCarriedSaveIssues(own: readonly Issue[], carried: readonly Issue[]): readonly Issue[] {
  const [replaced, setReplaced] = useState(false);
  const first = useRef(own);
  useEffect(() => {
    if (own !== first.current) setReplaced(true);
  }, [own]);
  return replaced ? own : own.length > 0 ? own : carried;
}
