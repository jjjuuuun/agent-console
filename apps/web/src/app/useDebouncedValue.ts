import { useEffect, useState } from "react";

/** 값이 `delayMs` 동안 바뀌지 않으면 그 값을 돌려준다(검색어를 서버 질의로 보낼 때 입력마다 요청하지 않게). */
export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
