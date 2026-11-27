/** 노드 사각형(흐름 좌표). */
export interface NodeRect {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * 같은 세로 줄(가로로 겹치는 노드)에서 위 노드의 아래 끝과 아래 노드의 위 끝이 `minGap`보다 가까우면 아래 노드를 내려 간격을 맞춘다.
 * 실행 결과 줄이 붙어 노드가 저장된 높이보다 커졌을 때 겹침을 푸는 보기 전용 보정이다(데이터는 바꾸지 않는다).
 * 위에서 아래 순서로 한 번 훑으므로 내린 노드는 그 아래 노드에도 반영된다.
 *
 * @param nodes 크기를 잰 노드 사각형
 * @param minGap 노드 사이 최소 세로 간격(흐름 px). 0 이하이면 아무것도 옮기지 않는다
 * @returns 옮길 노드의 id -> 아래로 내릴 거리(옮길 것이 없으면 빈 맵)
 */
export function separateNodesVertically(nodes: readonly NodeRect[], minGap: number): ReadonlyMap<string, number> {
  const out = new Map<string, number>();
  if (minGap <= 0 || nodes.length < 2) return out;
  const placed: { x: number; right: number; y: number; bottom: number }[] = [];
  for (const n of [...nodes].sort((a, b) => a.y - b.y || a.x - b.x)) {
    if (n.width <= 0 || n.height <= 0) continue;
    let y = n.y;
    for (const p of placed) {
      if (n.x < p.right && p.x < n.x + n.width && y < p.bottom + minGap && y + n.height > p.y) y = p.bottom + minGap;
    }
    if (y !== n.y) out.set(n.id, y - n.y);
    placed.push({ x: n.x, right: n.x + n.width, y, bottom: y + n.height });
  }
  return out;
}
