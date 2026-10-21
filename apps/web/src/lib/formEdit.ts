import { getDefaultValue, type JsonSchema } from "@agent-console/schema-form";
import { jsonEqual } from "./jsonPointer";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

function merge(prev: unknown, shown: unknown, next: unknown, def: unknown, unsetOnDefault: boolean): unknown {
  // 폼이 보여 준 값에서 바뀌지 않은 곳은 저장 원문을 그대로 둔다(생략한 키는 생략한 채).
  if (jsonEqual(next, shown)) return prev;
  if (isObj(next) && isObj(shown)) {
    const base = isObj(prev) ? prev : {};
    const out: Obj = { ...base };
    for (const key of new Set([...Object.keys(shown), ...Object.keys(next)])) {
      if (!(key in next)) {
        delete out[key];
        continue;
      }
      const value = merge(base[key], shown[key], next[key], isObj(def) ? def[key] : undefined, unsetOnDefault);
      if (value === undefined) delete out[key];
      else out[key] = value;
    }
    return out;
  }
  // 바꾼 값이 기본값과 같아지면 "지정 안 함"으로 되돌린 것으로 본다(층이 없는 설정용)
  if (unsetOnDefault && def !== undefined && jsonEqual(next, def)) return undefined;
  return next;
}

/**
 * 폼 값의 변경을 저장 원문에 반영한다. 폼 엔진은 스키마 기본값을 채워 돌려주므로 그대로 저장하면
 * 사용자가 건드리지 않은 키까지 "지정한 값"이 되어 위 층의 값을 가린다(생략 = 상속).
 * 이 함수는 폼이 처음 보여 준 값(`원문 + 기본값`)과 달라진 곳만 `prev`에 반영한다.
 * 배열·스칼라는 바뀌었으면 통째로 교체한다.
 * 지움과 생략: 값이 있던 칸을 비우면 폼이 null/빈 값을 돌려주므로 그 값이 "지운 상태"로 저장된다.
 * 키를 아예 없애(= 생략, 상속/기본) 되돌리려면 `unsetOnDefault`로 기본값과 같아지게 하거나 호출 측이 키를 지운다. 입력은 바꾸지 않는다.
 *
 * @param schema 폼에 넘긴 JSON Schema
 * @param prev 저장 원문(지정한 키만)
 * @param next 폼이 돌려준 값
 * @param options.unsetOnDefault 바꾼 값이 스키마 기본값과 같아지면 키를 지운다(위 층이 없는 노드·연결 설정용).
 *   끄면(기본) 사용자가 일부러 지정한 값으로 남긴다(출처 표시가 있는 층 폼).
 */
export function applyFormEdit(schema: JsonSchema, prev: Obj | undefined, next: unknown, options: { unsetOnDefault?: boolean } = {}): Obj {
  const shown = getDefaultValue(schema, prev);
  const def = options.unsetOnDefault === true ? getDefaultValue(schema) : undefined;
  const result = merge(prev, shown, next ?? {}, def, options.unsetOnDefault === true);
  return isObj(result) ? result : {};
}
