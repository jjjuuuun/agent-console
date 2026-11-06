import type { SafeStorage } from "../../app/storage";

/** 입력 초안 저장 키(`ac.run.draft.<프로젝트>.<구성>`). 화면 어디서든 이 함수로만 만든다. */
export const RUN_DRAFT_PREFIX = "ac.run.draft.";
const INDEX_KEY = "ac.run.draft.index";
/** 초안 보관 개수 상한(오래된 것부터 지운다) */
export const RUN_DRAFT_LIMIT = 20;
/** 값 하나의 직렬화 크기 상한(문자 수). 넘으면 저장하지 않는다 */
export const RUN_DRAFT_MAX_CHARS = 20_000;

export const runDraftKey = (project: string, graph: string): string => `${RUN_DRAFT_PREFIX}${project}.${graph}`;

function readIndex(storage: SafeStorage): string[] {
  try {
    const parsed: unknown = JSON.parse(storage.get(INDEX_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function readRunDraft(storage: SafeStorage, project: string, graph: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(storage.get(runDraftKey(project, graph)) ?? "null");
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** 초안을 저장한다(최근 20개 LRU). 비었거나 너무 크면 지운다. */
export function writeRunDraft(storage: SafeStorage, project: string, graph: string, values: Record<string, unknown>): void {
  const key = runDraftKey(project, graph);
  const raw = JSON.stringify(values);
  const empty = Object.values(values).every((v) => v === undefined || v === null || v === "");
  if (empty || raw.length > RUN_DRAFT_MAX_CHARS) {
    clearRunDraft(storage, project, graph);
    return;
  }
  storage.set(key, raw);
  const index = [key, ...readIndex(storage).filter((k) => k !== key)];
  for (const old of index.slice(RUN_DRAFT_LIMIT)) storage.remove(old);
  storage.set(INDEX_KEY, JSON.stringify(index.slice(0, RUN_DRAFT_LIMIT)));
}

export function clearRunDraft(storage: SafeStorage, project: string, graph: string): void {
  const key = runDraftKey(project, graph);
  storage.remove(key);
  storage.set(INDEX_KEY, JSON.stringify(readIndex(storage).filter((k) => k !== key)));
}
