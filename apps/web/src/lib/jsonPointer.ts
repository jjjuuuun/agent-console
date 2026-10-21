/** JSON Pointer(RFC 6901) 조작 모음. 모두 순수 함수이며 입력을 바꾸지 않는다. */

type Obj = Record<string, unknown>;

function isObj(v: unknown): v is Obj {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** `"/a/b~1c"` → `["a", "b/c"]`. 빈 문자열은 루트(빈 배열). */
export function parsePointer(pointer: string): string[] {
  if (pointer === "") return [];
  return pointer
    .split("/")
    .slice(1)
    .map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~"));
}

/** `["a", "b/c"]` → `"/a/b~1c"`. */
export function formatPointer(segments: readonly string[]): string {
  return segments.map((s) => "/" + s.replace(/~/g, "~0").replace(/\//g, "~1")).join("");
}

/** 경로의 값. 없으면 undefined. */
export function getAt(data: unknown, pointer: string): unknown {
  let cur: unknown = data;
  for (const seg of parsePointer(pointer)) {
    if (Array.isArray(cur)) cur = cur[Number(seg)];
    else if (isObj(cur)) cur = cur[seg];
    else return undefined;
  }
  return cur;
}

/** 경로에 값을 넣은 새 객체(중간 객체는 만든다). 배열 안쪽 경로는 지원하지 않는다(배열은 통째로 하나의 값). */
export function setAt(data: unknown, pointer: string, value: unknown): unknown {
  const walk = (node: unknown, segs: readonly string[]): unknown => {
    if (segs.length === 0) return value;
    const [head, ...rest] = segs as [string, ...string[]];
    const base = isObj(node) ? node : {};
    return { ...base, [head]: walk(base[head], rest) };
  };
  return walk(data, parsePointer(pointer));
}

/**
 * 경로의 키를 지운 새 객체. 지운 뒤 비게 된 상위 객체도 함께 지운다(루트는 남긴다).
 * 경로가 없으면 같은 객체를 돌려준다.
 */
export function unsetAt(data: unknown, pointer: string): unknown {
  const walk = (node: unknown, segs: readonly string[]): unknown => {
    if (!isObj(node)) return node;
    const [head, ...rest] = segs as [string, ...string[]];
    if (!(head in node)) return node;
    const next = { ...node };
    if (rest.length === 0) delete next[head];
    else {
      const child = walk(node[head], rest);
      if (child === node[head]) return node;
      if (isObj(child) && Object.keys(child).length === 0) delete next[head];
      else next[head] = child;
    }
    return next;
  };
  const segs = parsePointer(pointer);
  return segs.length === 0 ? {} : walk(data, segs);
}

/** 두 값이 깊은 비교로 같은가(JSON 값 한정, 키 순서 무시). */
export function jsonEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => jsonEqual(v, b[i]));
  if (isObj(a) && isObj(b)) {
    const ka = Object.keys(a);
    return ka.length === Object.keys(b).length && ka.every((k) => k in b && jsonEqual(a[k], b[k]));
  }
  return false;
}

/** 유효 값 위에 이 층의 값을 덮어 합친다. 객체만 재귀하고 배열·스칼라는 교체한다. */
export function deepMerge(base: unknown, over: unknown): unknown {
  if (over === undefined) return base;
  if (isObj(base) && isObj(over)) {
    const out: Obj = { ...base };
    for (const [k, v] of Object.entries(over)) out[k] = deepMerge(base[k], v);
    return out;
  }
  return over;
}
