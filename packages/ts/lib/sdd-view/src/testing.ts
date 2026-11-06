/**
 * 테스트·문서 예제용 표본 데이터. 상태·단계·문서 이름은 예시일 뿐이고 컴포넌트 코드와 무관하다.
 * 앱 번들에 넣지 않는다(`@agent-console/sdd-view/testing`).
 */
import type { ParsedStage, ParsedTask, SpecDocumentSummary, SpecSummary, TaskPlan, TaskStatusInfo, TraceMatrix } from "@agent-console/contracts/sdd";

export function sampleStatuses(): TaskStatusInfo[] {
  return [
    { id: "s-open", label: "열림", tone: "neutral" },
    { id: "s-doing", label: "진행", tone: "info" },
    { id: "s-done", label: "끝", tone: "success", done: true },
    { id: "s-fail", label: "실패", tone: "danger" },
  ];
}

export function sampleStages(): ParsedStage[] {
  return [
    { id: "st1", title: "1단계", document: "d-tasks", line: 1, done: 1, total: 2 },
    { id: "st2", title: "2단계", document: "d-tasks", line: 9, done: 0, total: 2 },
  ];
}

export function sampleTasks(): ParsedTask[] {
  const t = (key: string, status: string, stage: number | null, extra: Partial<ParsedTask> = {}): ParsedTask => ({
    key,
    id: key,
    title: `작업 ${key}`,
    status,
    document: "d-tasks",
    line: 3,
    line_hash: `h-${key}`,
    ready: status !== "s-done",
    ...(stage ? { stage: { id: `st${stage}`, title: `${stage}단계` } } : {}),
    ...extra,
  });
  return [
    t("T1", "s-done", 1),
    t("T2", "s-open", 1, { dependencies: ["T1"], requirements: ["R1"], fields: { owner: "a", size: "S" } }),
    t("T3", "s-open", 2, { dependencies: ["T2"], links: [{ integration: "x", kind: "k-run", ref: "run-1", status: "ok" }] }),
    t("T4", "s-doing", 2, { dependencies: ["T2"] }),
    t("T5", "s-open", null),
  ];
}

export function samplePlan(): TaskPlan {
  return { ready: ["T2"], layers: [["T1", "T5"], ["T2"], ["T3", "T4"]], critical_path: ["T1", "T2", "T3"], blocked: ["T3", "T4"], cycles: [] };
}

export function sampleDocuments(): SpecDocumentSummary[] {
  return [
    { id: "d-req", title: "요구", state: "g-draft", state_label: "초안", tone: "neutral" },
    { id: "d-tasks", title: "작업", state: "g-ok", state_label: "승인", tone: "success" },
    { id: "d-note", title: "메모" },
  ];
}

export function sampleSpecs(): SpecSummary[] {
  return [
    { id: "sp1", name: "결제", directory: "specs/pay", tasks_total: 5, tasks_done: 1, ready: 2, current_stage: { id: "st1", title: "1단계" }, updated_at: 1_700_000_000, documents: sampleDocuments(), issues: 1 },
    { id: "sp2", directory: "specs/ship", tasks_total: 0, tasks_done: 0 },
  ];
}

export function sampleTrace(): TraceMatrix {
  return {
    rows: [
      { id: "R1", title: "첫 요구", document: "d-req", line: 2, tasks: ["T2"], runs: [{ integration: "x", kind: "k-run", ref: "run-1" }], verification: { status: "v-pass" }, gaps: [] },
      { id: "R2", title: "둘째 요구", document: "d-req", line: 3, tasks: [], runs: [], verification: null, gaps: ["g-none", "g-unknown-code"] },
    ],
    orphans: { tasks_without_requirements: ["T5"], unknown_requirement_refs: [], unknown_task_links: [] },
  };
}

/** n개 작업(스크롤 테스트용). */
export function manyTasks(n: number): ParsedTask[] {
  return Array.from({ length: n }, (_, i) => ({ key: `M${i}`, title: `많은 ${i}`, status: "s-open", document: "d-tasks", line: i + 1, line_hash: `m${i}`, ready: true }));
}
