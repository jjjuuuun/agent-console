type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * 유효 값에서 한 층이 정한 잎을 뺀 "그 아래 층들의 값"(근사). 상속 값 표시에 쓴다.
 * 그 층이 덮어쓴 잎의 아래 층 값은 서버가 주지 않아 비워 둔다(스키마 기본으로 보인다).
 */
export function withoutLayer(effective: unknown, provenance: Readonly<Record<string, string>> | undefined, layerId: string | undefined): unknown {
  if (provenance === undefined || layerId === undefined) return effective;
  let out = structuredClone(effective);
  for (const [path, layer] of Object.entries(provenance)) {
    if (layer !== layerId) continue;
    out = removeAt(out, path.split("/").slice(1));
  }
  return out;
}

function removeAt(node: unknown, segs: readonly string[]): unknown {
  if (segs.length === 0 || !isObj(node)) return node;
  const [head, ...rest] = segs as [string, ...string[]];
  if (!(head in node)) return node;
  if (rest.length === 0) {
    const { [head]: _gone, ...others } = node;
    void _gone;
    return others;
  }
  return { ...node, [head]: removeAt(node[head], rest) };
}
