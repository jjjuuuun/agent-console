/**
 * 면 `auto`의 파생 계산(graph-edges §4.3). 순수 함수: 노드 상자와 연결 목록에서만 결정되고(같은 입력 → 같은 결과),
 * 결과는 저장하지 않는다. 호출 쪽이 "드롭 시점의 위치"(드래그 중 임시 위치가 아닌 저장된 위치)를 넘기면
 * 드래그 중에는 핸들이 튀지 않는다.
 */
import type { Side } from "../shapes/types";

/** 노드 상자(좌상단 + 크기). */
export interface AutoSideBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 연결 하나의 양 끝(노드 id + 포트 id). */
export interface AutoSideEdge {
  source: { node: string; port: string };
  target: { node: string; port: string };
}

/** 파생 면 조회 키: `<io>:<노드>\u0000<포트>`가 아니라 노드별 Map으로 돌려준다. 키는 `in:<포트>` / `out:<포트>`(node.layout.ports와 같은 형식). */
export type AutoSideMap = ReadonlyMap<string, ReadonlyMap<string, Side>>;

const centerOf = (b: AutoSideBox): { x: number; y: number } => ({ x: b.x + b.width / 2, y: b.y + b.height / 2 });

/**
 * `wanted`(노드 id → 자동으로 풀 포트 키 집합)에 있는 포트마다 면을 계산한다.
 * 포트에 붙은 엣지들의 상대 노드 중심 방향(단위 벡터)을 더해, 가로 성분이 세로 이상이면 좌/우, 아니면 상/하.
 * 상대 노드를 모르거나(숨김 등) 연결이 없거나 방향이 상쇄되면 그 포트는 결과에 넣지 않는다(호출 쪽이 방향 기본값을 쓴다).
 */
export function deriveAutoSides(
  boxes: ReadonlyMap<string, AutoSideBox>,
  edges: readonly AutoSideEdge[],
  wanted: ReadonlyMap<string, ReadonlySet<string>>,
): AutoSideMap {
  const sums = new Map<string, Map<string, { x: number; y: number }>>();
  const add = (self: string, key: string, other: string): void => {
    if (!wanted.get(self)?.has(key)) return;
    const a = boxes.get(self);
    const b = boxes.get(other);
    if (a === undefined || b === undefined || self === other) return;
    const ca = centerOf(a);
    const cb = centerOf(b);
    const dx = cb.x - ca.x;
    const dy = cb.y - ca.y;
    const len = Math.hypot(dx, dy);
    if (len === 0) return;
    const byPort = sums.get(self) ?? new Map<string, { x: number; y: number }>();
    const cur = byPort.get(key) ?? { x: 0, y: 0 };
    byPort.set(key, { x: cur.x + dx / len, y: cur.y + dy / len });
    sums.set(self, byPort);
  };
  for (const e of edges) {
    add(e.source.node, `out:${e.source.port}`, e.target.node);
    add(e.target.node, `in:${e.target.port}`, e.source.node);
  }
  const out = new Map<string, Map<string, Side>>();
  for (const [node, byPort] of sums) {
    const m = new Map<string, Side>();
    for (const [key, v] of byPort) {
      if (Math.abs(v.x) < 1e-9 && Math.abs(v.y) < 1e-9) continue;
      m.set(key, Math.abs(v.x) >= Math.abs(v.y) ? (v.x >= 0 ? "right" : "left") : v.y >= 0 ? "bottom" : "top");
    }
    out.set(node, m);
  }
  return out;
}
