import { getAt, setAt, unsetAt } from "./jsonPointer";

/**
 * [이 층에서 덮어쓰기]: 상속된(유효) 값을 이 층 값으로 복사한다.
 * 유효 값이 없으면(스키마 기본도 없음) `null`로 자리를 만든다.
 */
export function overrideAt<T>(layerValue: T, effectiveValue: unknown, pointer: string): T {
  const inherited = getAt(effectiveValue, pointer);
  return setAt(layerValue, pointer, inherited === undefined ? null : structuredClone(inherited)) as T;
}

/** [상속으로 되돌리기]: 이 층의 키를 지운다. */
export function inheritAt<T>(layerValue: T, pointer: string): T {
  return unsetAt(layerValue, pointer) as T;
}
