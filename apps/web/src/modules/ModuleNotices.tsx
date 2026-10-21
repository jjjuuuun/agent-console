import { useEffect, useRef } from "react";
import { useToast } from "@agent-console/ui";
import { messages as m } from "../app/messages";
import { useModules } from "./ModulesContext";
import { modulesSignature, problemModules } from "./resolve";

const SEEN_KEY = "ac.modules.problems";
const PROBLEM_TOAST_MS = 10_000;
const CHANGED_TOAST_MS = 6_000;

function readSeen(): string | null {
  try {
    return window.sessionStorage.getItem(SEEN_KEY);
  } catch {
    return null;
  }
}
function writeSeen(value: string): void {
  try {
    window.sessionStorage.setItem(SEEN_KEY, value);
  } catch {
    // 저장소를 쓸 수 없으면 알림이 반복될 수 있을 뿐이다
  }
}

export interface ModuleNoticesProps {
  /** 문제 알림의 [보기]가 가는 곳(설정의 기능 모듈 섹션) */
  modulesHref: string | undefined;
  navigate: (path: string) => void;
}

/**
 * 모듈 목록의 알림(화면은 없다).
 * - 문제 모듈(`unsatisfied`·`failed`·`conflict`, 사용자가 끈 `disabled`는 제외)이 있으면 경고 토스트를 한 번 띄운다.
 *   같은 문제 집합은 같은 세션에서 반복하지 않는다.
 * - 이미 받은 목록의 `id:status` 집합이 바뀌면 "서버의 기능 구성이 바뀌었습니다".
 */
export function ModuleNotices({ modulesHref, navigate }: ModuleNoticesProps) {
  const { state } = useModules();
  const toast = useToast();
  const lastSignature = useRef<string | null>(null);

  useEffect(() => {
    if (state.phase !== "ready") return;
    const signature = modulesSignature(state.modules);
    const first = lastSignature.current === null;
    const changed = !first && lastSignature.current !== signature;
    lastSignature.current = signature;
    if (changed) toast({ tone: "info", text: m.modules.configChanged, durationMs: CHANGED_TOAST_MS });

    const problems = problemModules(state.modules);
    if (problems.length === 0) return;
    const problemKey = modulesSignature(problems);
    if (readSeen() === problemKey) return;
    writeSeen(problemKey);
    toast({
      tone: "warning",
      text: m.modules.problemToast(problems.length),
      durationMs: PROBLEM_TOAST_MS,
      ...(modulesHref === undefined ? {} : { action: { label: m.modules.problemToastAction, onClick: () => navigate(modulesHref) } }),
    });
  }, [state, toast, modulesHref, navigate]);
  return null;
}
