import type { Graph, ResourceAttachment } from "@agent-console/contracts";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 서버가 정한 첨부 방식 기본값. 이 값은 저장 문서에 적지 않는다(생략 = 기본). */
const DEFAULT_ATTACHMENT_MODE = "add";

/**
 * 새 첨부 하나. UI가 자동으로 고른 방식이 서버 기본과 같으면 `mode`를 적지 않는다.
 * 사용자가 방식을 직접 바꾼 첨부는 이 함수를 거치지 않으므로 그대로 저장된다.
 */
export function newAttachment(ref: string, mode?: string): ResourceAttachment {
  return mode === undefined || mode === DEFAULT_ATTACHMENT_MODE ? { ref } : ({ ref, mode } as ResourceAttachment);
}

/** 객체의 최상위 null 값 키를 지운다(없앨 게 없으면 같은 객체). */
function dropNullKeys<T extends Obj>(o: T): T {
  if (!Object.values(o).includes(null)) return o;
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null)) as T;
}

function compactEntry<T extends Obj>(entry: T): T {
  let out = dropNullKeys(entry);
  if (isObj(out["config"])) {
    const config = dropNullKeys(out["config"]);
    if (Object.keys(config).length === 0) {
      const { config: _gone, ...rest } = out;
      void _gone;
      out = rest as T;
    } else if (config !== out["config"]) out = { ...out, config };
  }
  return out;
}

/**
 * 저장 직전 직렬화: 팀 구성의 노드·연결과 그 `config` 최상위에서 null(= 비어 있음) 키를 지운다.
 * "빈 값 = 키 삭제"(생략 = 상속/기본). 값이 있는 키와 그 안쪽(층 설정의 명시적 null 등)은 건드리지 않는다.
 * 입력은 바꾸지 않고, 바뀐 곳이 없으면 같은 객체를 돌려준다.
 */
export function compactGraph(graph: Graph): Graph {
  const nodes = graph.nodes?.map((n) => compactEntry(n as unknown as Obj) as unknown as typeof n);
  const edges = graph.edges?.map((e) => compactEntry(e as unknown as Obj) as unknown as typeof e);
  const changed = (a: readonly unknown[] | undefined, b: readonly unknown[] | undefined) => a !== undefined && b !== undefined && a.some((x, i) => x !== b[i]);
  if (!changed(nodes, graph.nodes) && !changed(edges, graph.edges)) return graph;
  return { ...graph, ...(nodes ? { nodes } : {}), ...(edges ? { edges } : {}) };
}
