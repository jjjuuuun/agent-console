import { ApiError } from "@agent-console/api-client";
import type { Fix } from "@agent-console/contracts";

export interface ErrorView {
  /** 사용자에게 보일 문장(서버 message 우선) */
  message: string;
  /** 접힌 "상세"에만 보일 code */
  code?: string;
  status?: number;
  /** 서버가 준 해결 버튼(`ErrorBlock`·`FixButtons`가 그린다) */
  fix?: Fix;
}

/** 어떤 오류든 화면용 문장으로. 알 수 없는 오류는 `fallback`. 토큰 등 비밀은 다루지 않는다. */
export function describeError(error: unknown, fallback: string): ErrorView {
  if (error instanceof ApiError) {
    return { message: error.message !== "" ? error.message : fallback, code: error.code, status: error.status, ...(error.fix === undefined ? {} : { fix: error.fix }) };
  }
  if (error instanceof Error && error.message !== "") return { message: error.message };
  return { message: fallback };
}
