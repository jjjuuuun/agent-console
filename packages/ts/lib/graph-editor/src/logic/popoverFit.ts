/** 사각형(화면 좌표). `DOMRect`의 필요한 부분만 쓴다. */
export interface FitRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface FitShift {
  x: number;
  y: number;
}

/** 여러 경계의 교집합. 빈 목록이면 `null`. 교집합이 비면 폭·높이 0인 사각형을 돌려준다. */
export function intersectRects(rects: readonly FitRect[]): FitRect | null {
  const first = rects[0];
  if (first === undefined) return null;
  const out = { ...first };
  for (const r of rects.slice(1)) {
    out.left = Math.max(out.left, r.left);
    out.top = Math.max(out.top, r.top);
    out.right = Math.min(out.right, r.right);
    out.bottom = Math.min(out.bottom, r.bottom);
  }
  if (out.right < out.left) out.right = out.left;
  if (out.bottom < out.top) out.bottom = out.top;
  return out;
}

function axisShift(start: number, end: number, boundStart: number, boundEnd: number, edge: number): number {
  const lo = boundStart + edge;
  const hi = boundEnd - edge;
  // 경계보다 크면 시작 쪽을 맞춘다(제목·왼쪽이 먼저 보이게)
  if (end - start >= hi - lo) return lo - start;
  if (start < lo) return lo - start;
  if (end > hi) return hi - end;
  return 0;
}

/**
 * 팝오버 사각형을 경계 안으로 넣기 위한 이동량. 경계 안이면 0, 경계보다 크면 왼쪽·위쪽을 맞춘다.
 * @param rect 지금 팝오버 위치
 * @param bounds 보여도 되는 영역(뷰포트와 클리핑 조상의 교집합)
 * @param edge 경계와 띄울 여백(px)
 */
export function fitShift(rect: FitRect, bounds: FitRect, edge = 8): FitShift {
  return {
    x: axisShift(rect.left, rect.right, bounds.left, bounds.right, edge),
    y: axisShift(rect.top, rect.bottom, bounds.top, bounds.bottom, edge),
  };
}
