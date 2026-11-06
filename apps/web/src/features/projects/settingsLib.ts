import type { AssignProjectResult, ProjectCounts, RecordsMoveResult } from "@agent-console/contracts/projects";

/** 한 기능의 앱 기록 개수(`ProjectCounts`)에서 프로젝트 하나(또는 프로젝트 없음 = null)의 몫. */
export function countFor(counts: ProjectCounts | undefined, projectId: string | null): number {
  if (counts === undefined) return 0;
  return projectId === null ? (counts.no_project ?? 0) : (counts.by_project?.[projectId] ?? 0);
}

/** 여러 `move-to-project` 응답 합산(채팅 → 실행 순서로 보낸 결과). */
export function mergeMoveResults(results: readonly RecordsMoveResult[]): Required<Pick<RecordsMoveResult, "moved" | "skipped">> & { failed: NonNullable<RecordsMoveResult["failed"]> } {
  return {
    moved: results.reduce((n, r) => n + (r.moved ?? 0), 0),
    skipped: results.reduce((n, r) => n + (r.skipped ?? 0), 0),
    failed: results.flatMap((r) => r.failed ?? []),
  };
}

/** `assign-project` 응답을 토스트 문구 재료로: 넣은 수와 건너뛴 수. */
export function assignSummary(result: AssignProjectResult, requested: number): { ok: number; skipped: number; total: number } {
  const skipped = result.skipped?.length ?? 0;
  return { ok: result.assigned, skipped, total: Math.max(requested, result.assigned + skipped) };
}

/** 기능 제목을 데이터로 받지 못했을 때 키 원문을 쓴다. */
export function featureTitle(titles: Readonly<Record<string, string | undefined>>, key: string): string {
  return titles[key] ?? key;
}
