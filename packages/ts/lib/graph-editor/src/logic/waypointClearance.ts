/**
 * 읽기 전용 보기에서 경유점이 카드 안에 들어가면 렌더 때만 카드 밖 가장 가까운 점으로 밀어낸다(4R.20 결정).
 * 실행 상세의 카드는 편집기보다 커서, 편집기에서 카드 밖이던 사용자 경유점이 카드 안에 들어갈 수 있다.
 * 순수 함수이며 저장 데이터는 바꾸지 않는다(호출 쪽이 화면 모델의 사본에만 쓴다).
 */
import type { Point } from "./ops";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 카드 가장자리에서 띄울 여백(px). 자동 경로 장애물 패딩과 같다. */
export const WAYPOINT_CLEARANCE = 16;

/**
 * 점 `p`가 어느 사각형(여백만큼 부풀림) 안에 있으면 그 사각형 바깥 가장 가까운 면으로 밀어낸다.
 * 밀린 점이 다른 사각형에 들어가면 몇 번 더 반복한다. 안에 있지 않으면 같은 점을 돌려준다.
 */
export function pushOutOfRects(p: Point, rects: readonly Rect[], margin: number = WAYPOINT_CLEARANCE): Point {
  let cur = p;
  for (let round = 0; round < rects.length + 1; round += 1) {
    const hit = rects.find((r) => cur.x > r.x - margin && cur.x < r.x + r.width + margin && cur.y > r.y - margin && cur.y < r.y + r.height + margin);
    if (hit === undefined) return cur;
    const left = cur.x - (hit.x - margin);
    const right = hit.x + hit.width + margin - cur.x;
    const top = cur.y - (hit.y - margin);
    const bottom = hit.y + hit.height + margin - cur.y;
    const m = Math.min(left, right, top, bottom);
    if (m === left) cur = { x: hit.x - margin, y: cur.y };
    else if (m === right) cur = { x: hit.x + hit.width + margin, y: cur.y };
    else if (m === top) cur = { x: cur.x, y: hit.y - margin };
    else cur = { x: cur.x, y: hit.y + hit.height + margin };
  }
  return cur;
}

/** 경유점 목록 전체를 밀어낸다. 바뀐 점이 없으면 같은 배열을 돌려준다. */
export function pushWaypointsOut(wps: readonly Point[], rects: readonly Rect[], margin?: number): readonly Point[] {
  let changed = false;
  const out = wps.map((w) => {
    const n = pushOutOfRects(w, rects, margin);
    if (n.x !== w.x || n.y !== w.y) changed = true;
    return n;
  });
  return changed ? out : wps;
}
