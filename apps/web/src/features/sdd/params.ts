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
  ready: boolean;
  q: string;
}

export function readTaskFilter(params: URLSearchParams): TaskFilter {
  return {
    status: params.getAll(SDD_PARAMS.status),
    stage: params.getAll(SDD_PARAMS.stage),
    ready: params.get(SDD_PARAMS.ready) === "1",
    q: params.get(SDD_PARAMS.q) ?? "",
  };
}

/** 거르기 값을 서버 질의 인자로(비어 있는 조건은 보내지 않는다). */
export function taskQueryOf(filter: TaskFilter): ListSpecTasksParams {
  return {
    ...(filter.status.length > 0 ? { status: filter.status } : {}),
    ...(filter.stage.length > 0 ? { stage: filter.stage } : {}),
    ...(filter.ready ? { ready: true } : {}),
    ...(filter.q.trim() === "" ? {} : { q: filter.q.trim() }),
  };
}
