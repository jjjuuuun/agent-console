type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * 폼 엔진이 마운트 때 채우는 널 기본값을 걷어 낸다: `next`에서 값이 null인데 `prev`(사용자가 만든 값)에 그 키가 없던 곳을 지운다.
 * 객체·배열 안쪽까지 같은 위치끼리 비교한다. 입력은 바꾸지 않는다.
 */
export function dropFilledNulls(next: unknown, prev: unknown): unknown {
  if (Array.isArray(next)) return next.map((v, i) => dropFilledNulls(v, Array.isArray(prev) ? prev[i] : undefined));
  if (!isObj(next)) return next;
  const before = isObj(prev) ? prev : {};
  const out: Obj = {};
  for (const [k, v] of Object.entries(next)) {
    if (v === null && !(k in before)) continue;
    out[k] = dropFilledNulls(v, before[k]);
  }
  return out;
}
