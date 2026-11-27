import { useCallback, useMemo, useState } from "react";
import { ApiError } from "@agent-console/api-client";
import type { Fix } from "@agent-console/contracts";
import { useAppMessages } from "./appMessages";

export interface ErrorView {
  /** 사용자에게 보일 문장(서버 message 우선) */
  message: string;
  /** 접힌 "상세"에만 보일 code */
  code?: string;
  status?: number;
  /** 서버가 준 해결 버튼(`ErrorBlock`·`FixButtons`가 그린다) */
  fix?: Fix;
}

/** 서버 오류 코드(`project.config_readonly` 등)를 화면 언어의 문장으로 바꾸는 함수. 모르는 코드는 `undefined`. */
export type ErrorCodeText = (code: string) => string | undefined;

/**
 * 어떤 오류든 화면용 문장으로. 알 수 없는 오류는 `fallback`. 토큰 등 비밀은 다루지 않는다.
 * @param codeText 코드별 문구(없으면 서버 message를 그대로 쓴다). 화면에서는 `useDescribeError()`가 현재 언어 표를 채워 준다.
 */
export function describeError(error: unknown, fallback: string, codeText?: ErrorCodeText): ErrorView {
  if (error instanceof ApiError) {
    const byCode = codeText?.(error.code);
    return { message: byCode ?? (error.message !== "" ? error.message : fallback), code: error.code, status: error.status, ...(error.fix === undefined ? {} : { fix: error.fix }) };
  }
  if (error instanceof Error && error.message !== "") return { message: error.message };
  return { message: fallback };
}

/** `describeError`와 같은 모양의 함수(화면 언어 문구가 들어간 것을 훅 밖 도우미에 넘길 때). */
export type DescribeErrorFn = (error: unknown, fallback: string) => ErrorView;

/** 현재 화면 언어의 코드별 문구가 들어간 `describeError`(컴포넌트 안에서 부른다). */
export function useDescribeError(): DescribeErrorFn {
  const { errorByCode } = useAppMessages();
  return useCallback((error, fallback) => describeError(error, fallback, errorByCode), [errorByCode]);
}

const NO_TEXTS: Readonly<Record<string, string>> = {};

/** 일어난 오류를 문구로 바꾸지 않고 그대로 담아 둔 값(`useErrorState`가 그릴 때 현재 화면 언어로 바꾼다). */
export interface RaisedError {
  readonly raised: { readonly error: unknown; readonly fallback: string | undefined; readonly key?: string };
}

/**
 * 오류와 대체 문구를 `useErrorState`·`useErrorView`의 setter에 넘길 값으로 묶는다.
 * `fallback`을 생략하면 훅에 준 대체 문구(`useErrorState(fallback)`, 그릴 때의 화면 언어)를 쓴다.
 */
export function raised(error: unknown, fallback?: string): RaisedError {
  return { raised: { error, fallback } };
}

/**
 * 서버 오류가 아니라 이 화면이 직접 만든 문제(예: "zip 파일이 아닙니다")를 `useErrorState(fallback, texts)`의 setter에 넘길 값으로 묶는다.
 * 문구는 `texts[key]`(그릴 때의 화면 언어)에서 가져오므로 언어를 바꾸면 따라 바뀐다.
 * `error`를 같이 주면 그 오류의 문장을 먼저 쓰고, 문장이 없을 때만 `texts[key]`가 대체 문구가 된다(한 상태에 대체 문구가 여럿일 때).
 */
export function raisedAs(key: string, error?: unknown): RaisedError {
  return { raised: { error, fallback: undefined, key } };
}

function raisedText(r: RaisedError["raised"], fallback: string, texts: Readonly<Record<string, string>>, describe: DescribeErrorFn): ErrorView {
  if (r.key !== undefined) {
    const text = texts[r.key] ?? fallback;
    return r.error === undefined ? { message: text } : describe(r.error, text);
  }
  return describe(r.error, r.fallback ?? fallback);
}

/**
 * `useErrorState`와 같되 `ErrorView`(문장·코드·해결 버튼)로 돌려준다.
 * @param fallback 오류에 문장이 없을 때 쓸 대체 문구. 매 렌더의 값이 쓰이므로 언어를 바꾸면 새 언어로 바뀐다
 */
export function useErrorView(fallback = "", texts: Readonly<Record<string, string>> = NO_TEXTS): [ErrorView | null, (next: null | RaisedError) => void] {
  const describe = useDescribeError();
  const [state, setState] = useState<null | RaisedError>(null);
  const view = useMemo(() => (state === null ? null : raisedText(state.raised, fallback, texts, describe)), [state, describe, fallback, texts]);
  return [view, setState];
}

/**
 * 화면에 붙어 있는 오류 문구 상태. 문구가 아니라 오류를 저장하고 렌더 때 `describeError`로 문구를 만들므로,
 * 오류가 떠 있는 채로 화면 언어를 바꾸면 새 언어로 바뀐다. 대체 문구는 `raised(error)`로 생략하고 훅 인자로 주면 항상 현재 언어다.
 * setter는 문자열·null·`raised(error, fallback?)`를 받는다.
 * @param fallback 현재 언어의 대체 문구(`raised`에서 생략했을 때 쓴다)
 * @param texts `raisedAs(key)`가 찾는 현재 언어 문구 표(렌더마다 새로 만들어도 된다)
 */
export function useErrorState(fallback = "", texts: Readonly<Record<string, string>> = NO_TEXTS): [string | null, (next: string | null | RaisedError) => void] {
  const describe = useDescribeError();
  const [state, setState] = useState<string | null | RaisedError>(null);
  const text = useMemo(() => (state === null || typeof state === "string" ? state : raisedText(state.raised, fallback, texts, describe).message), [state, describe, fallback, texts]);
  return [text, setState];
}
