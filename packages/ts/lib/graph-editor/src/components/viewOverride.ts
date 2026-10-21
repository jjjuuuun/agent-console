/**
 * 실행 상세(읽기 전용)의 [연결선 ▾] 보기 전용 덮어쓰기(graph-edges §7). 그래프 데이터는 건드리지 않고
 * 화면 모델의 엣지에서 모양만 바꾸며, 저장된 경유점·꺾임·라벨 위치는 임시 보기에서 쓰지 않는다.
 */
import type { FlowEdge } from "./flow";
import type { EdgeShapeDescriptor } from "../shapes/types";

/** 모든 엣지의 모양을 `shape`로 바꾼 새 목록. `shape`가 없으면 그대로(같은 배열). */
export function overrideEdgeShape(edges: FlowEdge[], shape: EdgeShapeDescriptor | undefined): FlowEdge[] {
  if (shape === undefined) return edges;
  return edges.map((e) => {
    if (e.data === undefined) return e;
    const { waypoints: _w, radius: _r, bend: _b, labelT: _t, labelOffset: _o, ...rest } = e.data;
    void _w; void _r; void _b; void _t; void _o;
    return { ...e, data: { ...rest, shape } };
  });
}
