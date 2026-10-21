import type { ProgressStep } from "./types";

/** 평탄화된 진행 단계 하나: 화면에서 실제로 그리는 들여 쓰기 단계와 부모 키를 함께 가진다. */
export interface FlatStep {
  step: ProgressStep;
  /** 실제 들여 쓰기 단계: 자식은 부모보다 최소 1 크다. */
  indent: number;
  parentKey: string | null;
}

/**
 * 단계 트리를 위에서 아래 순서로 펴고 후손까지 모두 담는다(접힘과 무관). 단계 수 세기·요약 규칙은 이 목록 기준이다.
 * 같은 키가 겹치면 먼저 나온 것만 남긴다(순환·중복 방지).
 */
export function flattenSteps(steps: readonly ProgressStep[]): FlatStep[] {
  const out: FlatStep[] = [];
  const seen = new Set<string>();
  const walk = (list: readonly ProgressStep[], floor: number, parentKey: string | null) => {
    for (const step of list) {
      if (seen.has(step.key)) continue;
      seen.add(step.key);
      const indent = Math.max(0, Math.floor(step.indent), floor);
      out.push({ step, indent, parentKey });
      if (step.children?.length) walk(step.children, indent + 1, step.key);
    }
  };
  walk(steps, 0, null);
  return out;
}

/** 펼침 상태(`expanded`)에 따라 실제로 보이는 단계만 남긴다. 접힌 칩의 후손은 빠진다. */
export function visibleSteps(flat: readonly FlatStep[], expanded: ReadonlySet<string>): FlatStep[] {
  const byKey = new Map(flat.map((f) => [f.step.key, f]));
  const open = (f: FlatStep): boolean => {
    let p = f.parentKey;
    while (p !== null) {
      if (!expanded.has(p)) return false;
      p = byKey.get(p)?.parentKey ?? null;
    }
    return true;
  };
  return flat.filter(open);
}

/** 접힌 칩의 "현재: 이름". 후손 중 가장 나중에 나온 `running` 상태 단계의 이름(없으면 undefined). */
export function currentStepLabel(step: ProgressStep, runningStatus: (status: string) => boolean): string | undefined {
  const flat = flattenSteps(step.children ?? []);
  for (let i = flat.length - 1; i >= 0; i -= 1) {
    const f = flat[i];
    if (f && runningStatus(f.step.status)) return f.step.toLabel;
  }
  return undefined;
}
