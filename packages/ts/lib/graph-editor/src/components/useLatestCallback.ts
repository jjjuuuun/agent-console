import { useCallback, useEffect, useRef } from "react";

/**
 * 렌더마다 새로 만들어지는 콜백을 항상 같은 참조로 감싼다. 호출하면 가장 최근에 렌더된 콜백이 실행된다.
 * 편집기 안의 파생 값(패널 props 등)이 부모의 인라인 콜백 때문에 매 렌더 새로 만들어지는 것을 막는다.
 */
export function useLatestCallback<A extends unknown[], R>(fn: ((...args: A) => R) | undefined): (...args: A) => R | undefined {
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  });
  return useCallback((...args: A) => ref.current?.(...args), []);
}
