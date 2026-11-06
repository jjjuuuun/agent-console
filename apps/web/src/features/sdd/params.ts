/** 주소 인자 도우미(순수). 같은 이름의 값을 여러 번 쓰는 목록 인자를 통째로 바꾸고, 작업 거르기 인자를 읽는다. */
import type { ListSpecTasksParams } from "@agent-console/api-client";
import { SDD_PARAMS } from "./sddConfig";

export function setList(params: URLSearchParams, name: string, values: readonly string[]): void {
  params.delete(name);
  for (const v of values) params.append(name, v);
}

/** 주소에서 읽은 작업 거르기 값(화면 상태). */
export interface TaskFilter {
  status: string[];
  stage: string[];
  /** `키=값` 필드 거르기(같은 키는 OR, 다른 키는 AND — 서버 규칙) */
  field: string[];
  ready: boolean;
  q: string;
}

export function readTaskFilter(params: URLSearchParams): TaskFilter {
  return {
    status: params.getAll(SDD_PARAMS.status),
    stage: params.getAll(SDD_PARAMS.stage),
    field: params.getAll(SDD_PARAMS.field),
    ready: params.get(SDD_PARAMS.ready) === "1",
    q: params.get(SDD_PARAMS.q) ?? "",
  };
}

/** 거르기 값을 서버 질의 인자로(비어 있는 조건은 보내지 않는다). */
export function taskQueryOf(filter: TaskFilter): ListSpecTasksParams {
  return {
    ...(filter.status.length > 0 ? { status: filter.status } : {}),
    ...(filter.stage.length > 0 ? { stage: filter.stage } : {}),
    ...(filter.field.length > 0 ? { field: filter.field } : {}),
    ...(filter.ready ? { ready: true } : {}),
    ...(filter.q.trim() === "" ? {} : { q: filter.q.trim() }),
  };
}

/** `키=값` 한 쌍을 나눈다(첫 `=` 기준). `=`가 없으면 값은 빈 문자열. */
export function splitFieldPair(pair: string): { key: string; value: string } {
  const at = pair.indexOf("=");
  return at < 0 ? { key: pair, value: "" } : { key: pair.slice(0, at), value: pair.slice(at + 1) };
}

export const fieldPair = (key: string, value: string): string => `${key}=${value}`;

/** 작업들에 실제 나온 필드 키 → 값(많이 나온 순) 목록. 키 순서는 처음 나온 순서. 필드 이름은 서버 데이터라 코드에 없다. */
export function collectFieldValues(tasks: readonly { fields?: Readonly<Record<string, string>> | undefined }[]): { key: string; values: { value: string; count: number }[] }[] {
  const byKey = new Map<string, Map<string, number>>();
  for (const task of tasks) {
    for (const [key, value] of Object.entries(task.fields ?? {})) {
      const values = byKey.get(key) ?? new Map<string, number>();
      values.set(value, (values.get(value) ?? 0) + 1);
      byKey.set(key, values);
    }
  }
  return [...byKey].map(([key, values]) => ({ key, values: [...values].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value)) }));
}
