/** 이벤트 type 접두 필터 값(접두 여럿을 한 값에 담는 형식). 화면·기능에 묶이지 않는 순수 함수. */

/** 접두 필터 값 구분자. 필터 한 값에 접두 여럿을 담는다(예: `memory.read,memory.search`). */
export const TYPE_PREFIX_SEPARATOR = ",";

export function joinTypePrefixes(prefixes: readonly string[]): string {
  return prefixes.join(TYPE_PREFIX_SEPARATOR);
}

/** 필터 값이 비었으면 모두 통과, 아니면 값 안의 접두 중 하나로 시작하는 type만 통과. */
export function matchesTypePrefix(type: string, filter: string): boolean {
  if (filter === "") return true;
  return filter.split(TYPE_PREFIX_SEPARATOR).some((x) => x !== "" && type.startsWith(x));
}
