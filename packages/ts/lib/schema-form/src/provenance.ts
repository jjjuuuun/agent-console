import { parsePointer } from "./errors";
import type { ProvenanceLayer } from "./types";

type Seg = string | number;

/** 키 배열을 JSON Pointer로. 루트는 빈 문자열. */
export function toPointer(path: readonly Seg[]): string {
  return path.map((s) => "/" + String(s).replace(/~/g, "~0").replace(/\//g, "~1")).join("");
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function getIn(data: unknown, segs: readonly string[]): unknown {
  let cur = data;
  for (const s of segs) {
    if (Array.isArray(cur)) cur = cur[Number(s)];
    else if (isPlainObject(cur)) cur = cur[s];
    else return undefined;
  }
  return cur;
}

function setIn(data: unknown, segs: readonly string[], value: unknown): unknown {
  if (segs.length === 0) return value;
  const [head, ...rest] = segs as [string, ...string[]];
  const base = isPlainObject(data) ? data : {};
  return { ...base, [head]: setIn(base[head], rest, value) };
}

/** 유효 값 위에 이 층의 값을 덮어 합친다. 객체만 재귀하고, 배열·스칼라는 이 층 값이 교체한다. */
export function deepMerge(base: unknown, over: unknown): unknown {
  if (over === undefined) return base;
  if (isPlainObject(base) && isPlainObject(over)) {
    const out: Record<string, unknown> = { ...base };
    for (const [k, v] of Object.entries(over)) out[k] = deepMerge(base[k], v);
    return out;
  }
  return over;
}

/** 배열은 잎으로 보고, 이 값에 실제로 들어 있는 경로(JSON Pointer 키 배열)를 모은다. */
function leafPaths(value: unknown, prefix: string[] = []): string[][] {
  if (isPlainObject(value) && Object.keys(value).length > 0) {
    return Object.entries(value).flatMap(([k, v]) => leafPaths(v, [...prefix, k]));
  }
  return prefix.length > 0 ? [prefix] : [];
}

/**
 * 폼 엔진이 돌려준 전체 값(상속 값 포함)에서 **이 층의 값만** 뽑는다.
 * 이 층이 지정한 경로(기존 `layerValue`의 잎 + `provenance`에서 편집 층인 경로)만 새 값으로 갱신하고,
 * 상속 값은 넣지 않는다. 비운 입력은 키를 지우지 않고(상속으로 돌아가지 않음) 문자열은 "", 그 외는 null로 둔다.
 */
export function extractLayerValue(
  formData: unknown,
  layerValue: unknown,
  provenance: Record<string, string>,
  editLayerId: string | undefined,
  /** 이번 편집으로 바뀐 잎 경로(간소 출처 표시: 지정하지 않은 필드를 바로 편집하면 이 층에 들어간다) */
  extraPaths: readonly (readonly string[])[] = [],
): unknown {
  const paths = new Map<string, string[]>();
  const add = (segs: string[]) => {
    // 배열 안쪽 경로는 배열 자체로 접는다(목록은 통째로 교체).
    let cur: unknown = formData;
    let cut = segs.length;
    for (let i = 0; i < segs.length; i++) {
      if (Array.isArray(cur)) {
        cut = i;
        break;
      }
      cur = isPlainObject(cur) ? cur[segs[i] as string] : undefined;
    }
    const key = segs.slice(0, cut);
    if (key.length > 0) paths.set(toPointer(key), key);
  };
  for (const segs of leafPaths(layerValue)) add(segs);
  for (const segs of extraPaths) add([...segs]);
  if (editLayerId !== undefined) {
    for (const [ptr, id] of Object.entries(provenance)) if (id === editLayerId) add(parsePointer(ptr));
  }
  let out: unknown = isPlainObject(layerValue) || Array.isArray(layerValue) ? layerValue : {};
  for (const segs of paths.values()) {
    let next = getIn(formData, segs);
    if (next === undefined) {
      const old = getIn(layerValue, segs);
      if (old === undefined) continue;
      next = typeof old === "string" ? "" : null;
    }
    out = setIn(out, segs, next);
  }
  return out;
}

/** 두 값에서 서로 다른 잎 경로(배열은 통째로 하나의 잎). */
export function changedPaths(before: unknown, after: unknown, prefix: string[] = []): string[][] {
  if (isPlainObject(after)) {
    const b = isPlainObject(before) ? before : {};
    const keys = new Set([...Object.keys(b), ...Object.keys(after)]);
    return [...keys].flatMap((k) => changedPaths(b[k], after[k], [...prefix, k]));
  }
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  return prefix.length > 0 ? [prefix] : [];
}

export type FieldState = "set" | "inherited" | "default" | "mixed";

export interface FieldProvenance {
  state: FieldState;
  /** set·inherited일 때 배지가 가리키는 층 id(여러 층이면 우선순위가 가장 높은 층) */
  layerId?: string;
  /** 기여한 층 id(`layers` 순서) */
  layerIds: string[];
}

function pointerUnder(key: string, pointer: string): boolean {
  return key === pointer || key.startsWith(pointer + "/");
}

/**
 * 한 필드(JSON Pointer)의 출처를 계산한다. 컨테이너면 하위 잎까지 합친다.
 * 이 층의 `value`에 값이 들어 있으면 provenance가 아직 갱신되지 않았어도 이 층 지정으로 본다.
 */
export function fieldProvenance(args: {
  pointer: string;
  container: boolean;
  provenance: Record<string, string>;
  layers: readonly ProvenanceLayer[];
  editLayerId: string | undefined;
  layerValue: unknown;
}): FieldProvenance {
  const { pointer, container, provenance, layers, editLayerId, layerValue } = args;
  const ids = new Set<string>();
  for (const [k, id] of Object.entries(provenance)) if (pointerUnder(k, pointer)) ids.add(id);
  const own = getIn(layerValue, parsePointer(pointer));
  const ownHas = editLayerId !== undefined && own !== undefined;
  if (ownHas) ids.add(editLayerId);
  const order = (id: string) => {
    const i = layers.findIndex((l) => l.id === id);
    return i === -1 ? layers.length : i;
  };
  const layerIds = [...ids].sort((a, b) => order(a) - order(b));
  if (layerIds.length === 0) return { state: "default", layerIds };
  if (container) {
    return layerIds.length > 1
      ? { state: "mixed", layerIds }
      : { state: layerIds[0] === editLayerId ? "set" : "inherited", layerId: layerIds[0], layerIds };
  }
  if (editLayerId !== undefined && ids.has(editLayerId)) return { state: "set", layerId: editLayerId, layerIds };
  return { state: "inherited", layerId: layerIds[layerIds.length - 1], layerIds };
}

/** 이 경로를 덮는 `disabledPaths` 키 중 가장 상위(가장 짧은) 것. 없으면 undefined. */
export function disabledMatch(disabled: Record<string, string> | undefined, pointer: string): string | undefined {
  if (!disabled) return undefined;
  let best: string | undefined;
  for (const k of Object.keys(disabled)) {
    if (pointerUnder(pointer, k) && (best === undefined || k.length < best.length)) best = k;
  }
  return best;
}

/** 팝오버 줄에 보일 값 문자열(길면 자른다). */
export function previewValue(v: unknown, max = 60): string {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

export { getIn };
